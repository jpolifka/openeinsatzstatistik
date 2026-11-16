# -*- coding: utf-8 -*-
"""
Anmeldung per Magic Link.

Aktiv, sobald ADMIN_EMAILS gesetzt ist. Berechtigt sind die Superadmins aus ADMIN_EMAILS und
alle Adressen mit einer Zuordnung zu einer aktiven Wehr bzw. VG (tenancy.is_allowed). Wer sich
anmelden will, gibt seine Adresse ein und bekommt per Mail (mail.py, SMTP der eigenen Domain) einen Link, der 15 Minuten gilt
und nur einmal benutzt werden kann. Danach hält ein signiertes Cookie die Sitzung (30 Tage).
Wird die letzte Zuordnung einer Adresse entfernt, verliert sie beim nächsten Aufruf den Zugang.

Links sind mit HMAC signiert (Schlüssel aus SECRET_KEY oder session.key im Datenordner). Sitzungen
liegen serverseitig (Tabelle session, nur der SHA-256 des Cookie-Werts): Abmelden und das Beenden
durch einen Superadmin machen ein kopiertes Cookie sofort wertlos.
"""
import base64
import hashlib
import hmac
import html
import logging
import os
import secrets
import smtplib
import threading
import time
from urllib.parse import urlsplit

from fastapi import APIRouter, BackgroundTasks, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app import db, mail, tenancy, theme

log = logging.getLogger("openeinsatzstatistik")

BASE_URL = os.environ.get("BASE_URL", "").rstrip("/")
SECRET_KEY = os.environ.get("SECRET_KEY", "")
# Ohne Anmeldung ist jeder Zugriff Superadmin: nur auf ausdrückliche Anweisung (lokale Entwicklung)
AUTH_DISABLED = os.environ.get("AUTH_DISABLED", "").strip().lower() in ("1", "true", "yes", "ja")

COOKIE = "session"
SCOPE_COOKIE = "scope"     # ausgewählte Wehr, wird bei jeder Anfrage gegen die Zuordnungen geprüft
LINK_TTL = 15 * 60
SESSION_TTL = 30 * 24 * 60 * 60
# Wer sich so lange nicht gemeldet hat, muss sich neu anmelden (ein gestohlenes Cookie veraltet damit früher)
SESSION_IDLE = 7 * 24 * 60 * 60
# Mindestabstand zwischen zwei Mails an dieselbe Adresse
MAIL_COOLDOWN = 60
# Obergrenze je Adresse. Die Gesamtzahl pro Stunde sperrt nichts (sonst könnte jemand mit ein paar bekannten Adressen
# allen den Zugang blockieren), sie warnt nur im Log.
MAIL_PER_ADDRESS_PER_DAY = 10
MAIL_TOTAL_ALERT_PER_HOUR = 200
MAX_SESSIONS_PER_USER = 10

router = APIRouter()
_lock = threading.Lock()
_last_mail = {}     # Adresse → Zeitpunkt der letzten Mail
_sent = []          # (Zeitpunkt, Adresse) der Mails der letzten 24 Stunden
_key = None


def enabled():
    return tenancy.auth_enabled()


def _is_local():
    return urlsplit(BASE_URL).hostname in ("localhost", "127.0.0.1", "::1")


def check_config():
    """Bricht den Start ab, wenn die Anmeldung so nicht funktionieren kann."""
    if enabled() and not BASE_URL:
        raise RuntimeError("ADMIN_EMAILS ist gesetzt, BASE_URL fehlt (siehe README)")
    if not enabled() and BASE_URL and not _is_local():
        raise RuntimeError("Für eine nicht lokale BASE_URL muss ADMIN_EMAILS gesetzt sein.")
    if enabled() and not mail.enabled() and not _is_local():
        # Sonst stünde der Anmeldelink im Log und jeder mit Log-Zugriff könnte sich als beliebiger Benutzer anmelden
        raise RuntimeError("Anmeldung ohne Mailversand (SMTP_HOST) gibt es nur mit lokaler BASE_URL (siehe README)")
    if os.environ.get("RESEND_API_KEY"):
        # Nicht still ohne Mails starten, wenn noch die alte Konfiguration gesetzt ist
        raise RuntimeError("RESEND_API_KEY wird nicht mehr unterstützt – Versand per SMTP_* (siehe README)")
    if enabled() and AUTH_DISABLED:
        raise RuntimeError("AUTH_DISABLED und ADMIN_EMAILS widersprechen sich – eines von beiden entfernen")
    if not enabled() and not AUTH_DISABLED:
        raise RuntimeError("ADMIN_EMAILS fehlt: ohne Anmeldung wäre jeder Zugriff Superadmin. Superadmins "
                           "eintragen – oder nur für die lokale Entwicklung AUTH_DISABLED=1 setzen (siehe README)")
    if not enabled():
        log.warning("Anmeldung AUS (AUTH_DISABLED=1): jeder Zugriff gilt als Superadmin. Nur lokal verwenden.")
    mail.check_config()


def _secret():
    global _key
    if _key is None:
        if SECRET_KEY:
            _key = SECRET_KEY.encode()
        else:
            path = os.path.join(os.path.abspath(db.DATA_DIR), "session.key")
            if not os.path.exists(path):
                with open(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as f:
                    f.write(secrets.token_hex(32))
            with open(path) as f:
                _key = f.read().strip().encode()
    return _key


# ---------------------------------------------------------------- Signierte Token
def _mac(purpose, payload):
    return hmac.new(_secret(), f"{purpose}:{payload}".encode(), hashlib.sha256).hexdigest()


def _sign(purpose, email, ttl):
    payload = base64.urlsafe_b64encode(f"{email}|{int(time.time() + ttl)}".encode()).decode().rstrip("=")
    return f"{payload}.{_mac(purpose, payload)}"


def _verify(purpose, token):
    """Adresse aus einem gültigen Token, sonst None."""
    payload, _, mac = (token or "").partition(".")
    if not mac or not hmac.compare_digest(mac, _mac(purpose, payload)):
        return None
    try:
        email, _, expires = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)).decode().rpartition("|")
        expires = int(expires)
    except ValueError:
        return None
    return email if expires > time.time() and tenancy.is_allowed(email) else None


# ---------------------------------------------------------------- Sitzungen
SEEN_INTERVAL = 300      # „zuletzt aktiv“ höchstens alle 5 Minuten schreiben


def _hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(email, user_agent=""):
    """Neue Sitzung für eine Adresse -> Wert für das Cookie. Räumt abgelaufene Sitzungen auf."""
    token = secrets.token_urlsafe(32)
    now = time.time()
    with tenancy.central() as con:
        con.execute("DELETE FROM session WHERE expires < ? OR last_seen < ?", (now, now - SESSION_IDLE))
        # Älteste Sitzungen dieser Adresse beenden, damit es nie mehr als MAX_SESSIONS_PER_USER gibt
        con.execute("DELETE FROM session WHERE email = ? AND id NOT IN (SELECT id FROM session WHERE email = ? "
                    "ORDER BY last_seen DESC, id DESC LIMIT ?)",
                    (tenancy.normalize_email(email), tenancy.normalize_email(email), MAX_SESSIONS_PER_USER - 1))
        con.execute("INSERT INTO session (token_hash, email, created, last_seen, expires, user_agent) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (_hash(token), tenancy.normalize_email(email), now, now, now + SESSION_TTL, (user_agent or "")[:200]))
    return token


def _session(request: Request):
    """Gültige Sitzung des Cookies (Zeile) oder None; die Adresse muss noch berechtigt sein."""
    if hasattr(request.state, "session_row"):      # Middleware und access() fragen dieselbe Anfrage
        return request.state.session_row
    request.state.session_row = _lookup_session(request)
    return request.state.session_row


def _lookup_session(request):
    token = request.cookies.get(COOKIE)
    if not token or len(token) > 100:
        return None
    now = time.time()
    with tenancy.central() as con:
        row = con.execute("SELECT id, email, expires, last_seen FROM session WHERE token_hash = ?",
                          (_hash(token),)).fetchone()
        if not row or row["expires"] <= now or now - row["last_seen"] > SESSION_IDLE:
            return None
        if now - row["last_seen"] > SEEN_INTERVAL:
            con.execute("UPDATE session SET last_seen = ? WHERE id = ?", (now, row["id"]))
    return row if tenancy.is_allowed(row["email"]) else None


def current_user(request: Request):
    row = _session(request)
    return row["email"] if row else None


def current_session_id(request: Request):
    row = _session(request)
    return row["id"] if row else None


def end_session(request: Request):
    """Sitzung des Cookies beenden (Abmelden)."""
    token = request.cookies.get(COOKIE)
    if token:
        with tenancy.central() as con:
            con.execute("DELETE FROM session WHERE token_hash = ?", (_hash(token),))


def access(request: Request) -> tenancy.Access:
    """Rechte des angemeldeten Benutzers und ausgewählte Wehr bzw. VG (ohne Anmeldung: Superadmin).
    Als FastAPI-Dependency für alle Endpunkte mit Einsatzdaten oder Verwaltung."""
    email = current_user(request) if enabled() else None
    if enabled() and email is None:
        raise HTTPException(401, "Anmeldung erforderlich")
    return tenancy.access_for(email, request.cookies.get(SCOPE_COOKIE))


def _use_link(token):
    """Prüft den Link und entwertet ihn. Liefert die Adresse oder None."""
    email = _verify("link", token)
    if not email:
        return None
    # Atomar in SQLite entwerten: gilt auch nach Neustart und in anderen Prozessen.
    now = time.time()
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with tenancy.central() as con:
        con.execute("DELETE FROM consumed_magic_link WHERE expires < ?", (now,))
        used = con.execute("INSERT OR IGNORE INTO consumed_magic_link VALUES (?, ?)",
                           (token_hash, now + LINK_TTL)).rowcount
    if not used:
        return None
    return email


# ---------------------------------------------------------------- Mailversand
def send_link(email):
    """Schickt den Anmeldelink – still nichts, wenn die Adresse nicht berechtigt ist."""
    email = tenancy.normalize_email(email)
    if not tenancy.is_allowed(email):
        log.info("Anmeldung mit nicht berechtigter Adresse abgelehnt")
        return
    with _lock:
        now = time.time()
        if now - _last_mail.get(email, 0) < MAIL_COOLDOWN:
            return
        _sent[:] = [(t, a) for t, a in _sent if now - t < 24 * 3600]
        if sum(a == email for _, a in _sent) >= MAIL_PER_ADDRESS_PER_DAY:
            log.warning("Anmeldelink für %s nicht versendet: Obergrenze für Mails erreicht", email)
            return
        if sum(now - t < 3600 for t, _ in _sent) == MAIL_TOTAL_ALERT_PER_HOUR:
            log.warning("Auffällig viele Anmeldelinks in der letzten Stunde (%s) – mögliche Mail-Flut", MAIL_TOTAL_ALERT_PER_HOUR)
        _last_mail[email] = now
        _sent.append((now, email))
    link = f"{BASE_URL}/auth/verify?token={_sign('link', email, LINK_TTL)}"
    if not mail.enabled():
        if _is_local():          # lokale Entwicklung ohne Mailversand: Link im Log
            log.warning("SMTP_HOST fehlt – Anmeldelink für %s: %s", email, link)
        else:
            log.error("SMTP_HOST fehlt – Anmeldelink für %s nicht versendet", email)
        return
    text = (f"Hallo,\n\nmit diesem Link meldest du dich bei der Einsatzstatistik an:\n{link}\n\n"
                "Der Link gilt 15 Minuten und nur einmal. Wenn du keine Anmeldung angefordert hast, "
                "kannst du diese Mail ignorieren.")
    body = (f"<p>Hallo,</p><p>mit diesem Link meldest du dich bei der Einsatzstatistik an:</p>"
                f"<p><a href=\"{html.escape(link)}\">Jetzt anmelden</a></p>"
                "<p>Der Link gilt 15 Minuten und nur einmal. Wenn du keine Anmeldung angefordert hast, "
                "kannst du diese Mail ignorieren.</p>")
    try:
        mail.send(email, "Anmeldung Einsatzstatistik", text, body)
    except (smtplib.SMTPException, OSError) as e:
        log.error("Mailversand über %s fehlgeschlagen: %s", mail.SMTP_HOST, e)
        # Gleich wieder anfordern lassen statt 60 Sekunden ohne Mail
        with _lock:
            _last_mail.pop(email, None)


# ---------------------------------------------------------------- Seiten
def _page(content, status_code=200):
    return HTMLResponse(f"""<!doctype html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Anmeldung · Einsatzstatistik</title><link rel="icon" href="/static/favicon.svg"><link rel="icon" href="/static/favicon.ico" sizes="48x48"><link rel="apple-touch-icon" href="/static/apple-touch-icon.png">
<link rel="stylesheet" href="/static/app.css">
<style>{theme.css(theme.NEUTRAL)}</style></head>
<body><header class="topbar"><div class="topbar-inner">
<img class="topbar-logo" src="/static/img/app-icon-light.svg" alt="">
<div class="topbar-title"><span class="topbar-kicker">Einsatzstatistik</span><h1>Anmeldung</h1></div>
</div></header>
<main class="page"><div class="card login-card">{content}</div></main></body></html>""", status_code)


def _login_form(note=""):
    return _page(f"""{note}<form method="post" action="/login" class="login-form">
<label class="field"><span>E-Mail-Adresse</span><input type="email" name="email" required autofocus autocomplete="email"></label>
<button type="submit" class="btn btn-primary">Anmeldelink anfordern</button></form>""")


@router.get("/login")
def login_page(request: Request):
    if current_user(request):
        return RedirectResponse("/", 303)
    return _login_form()


@router.post("/login")
def login_request(background: BackgroundTasks, email: str = Form(...)):
    # Erst nach der Antwort senden: sonst verriete die Antwortzeit, ob die Adresse berechtigt ist
    background.add_task(send_link, email)
    return _page("<p>Wenn die Adresse berechtigt ist, ist jetzt ein Anmeldelink unterwegs. "
                 "Er gilt 15 Minuten.</p><p><a href=\"/login\">Zurück</a></p>")


@router.get("/auth/verify")
def verify_page(token: str = ""):
    # Erst nach Klick anmelden: Virenscanner in Mailprogrammen rufen Links vorab auf
    # und würden den Einmal-Link sonst verbrauchen.
    if not _verify("link", token):
        return _login_form('<p class="message message-error">Der Link ist abgelaufen oder ungültig. '
                           'Bitte einen neuen anfordern.</p>')
    return _page(f"""<form method="post" action="/auth/verify" class="login-form">
<input type="hidden" name="token" value="{html.escape(token)}">
<button type="submit" class="btn btn-primary">Jetzt anmelden</button></form>""")


@router.post("/auth/verify")
def verify(request: Request, token: str = Form("")):
    email = _use_link(token)
    if not email:
        return _login_form('<p class="message message-error">Der Link ist abgelaufen oder wurde schon benutzt. '
                           'Bitte einen neuen anfordern.</p>')
    log.info("Anmeldung: %s", email)
    tenancy.record_login(email)
    response = RedirectResponse("/", 303)
    response.set_cookie(COOKIE, create_session(email, request.headers.get("user-agent", "")), max_age=SESSION_TTL, httponly=True,
                        samesite="lax", secure=BASE_URL.startswith("https://"))
    return response


@router.post("/logout")
def logout(request: Request):
    end_session(request)
    response = RedirectResponse("/login", 303)
    response.delete_cookie(COOKIE)
    response.delete_cookie(SCOPE_COOKIE)
    return response
