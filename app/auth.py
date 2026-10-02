# -*- coding: utf-8 -*-
"""
Anmeldung per Magic Link.

Aktiv, sobald ADMIN_EMAILS gesetzt ist. Berechtigt sind die Superadmins aus ADMIN_EMAILS und
alle Adressen mit einer Zuordnung zu einer aktiven Wehr bzw. VG (tenancy.is_allowed). Wer sich
anmelden will, gibt seine Adresse ein und bekommt über Resend einen Link, der 15 Minuten gilt
und nur einmal benutzt werden kann. Danach hält ein signiertes Cookie die Sitzung (30 Tage).
Wird die letzte Zuordnung einer Adresse entfernt, verliert sie beim nächsten Aufruf den Zugang.

Links und Cookies sind mit HMAC signiert. Der Schlüssel kommt aus SECRET_KEY oder wird
beim ersten Start im Datenordner als session.key angelegt.
"""
import base64
import hashlib
import hmac
import html
import json
import logging
import os
import secrets
import threading
import time
import urllib.error
import urllib.request

from fastapi import APIRouter, BackgroundTasks, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app import db, tenancy, theme

log = logging.getLogger("pdf2einsatz")

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
MAIL_FROM = os.environ.get("MAIL_FROM", "")
BASE_URL = os.environ.get("BASE_URL", "").rstrip("/")
SECRET_KEY = os.environ.get("SECRET_KEY", "")

COOKIE = "session"
SCOPE_COOKIE = "scope"     # ausgewählte Wehr, wird bei jeder Anfrage gegen die Zuordnungen geprüft
LINK_TTL = 15 * 60
SESSION_TTL = 30 * 24 * 60 * 60
# Mindestabstand zwischen zwei Mails an dieselbe Adresse
RESEND_COOLDOWN = 60

router = APIRouter()
_lock = threading.Lock()
_used_links = {}    # Token → Ablaufzeit; verhindert die zweite Benutzung eines Links
_last_mail = {}     # Adresse → Zeitpunkt der letzten Mail
_key = None


def enabled():
    return tenancy.auth_enabled()


def check_config():
    """Bricht den Start ab, wenn die Anmeldung so nicht funktionieren kann."""
    if enabled() and not BASE_URL:
        raise RuntimeError("ADMIN_EMAILS ist gesetzt, BASE_URL fehlt (siehe README)")
    if RESEND_API_KEY and not MAIL_FROM:
        raise RuntimeError("RESEND_API_KEY ist gesetzt, MAIL_FROM fehlt (siehe README)")


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


def current_user(request: Request):
    return _verify("session", request.cookies.get(COOKIE))


def access(request: Request) -> tenancy.Access:
    """Rechte des angemeldeten Benutzers und ausgewählte Wehr bzw. VG (ohne Anmeldung: Superadmin).
    Als FastAPI-Dependency für alle Endpunkte mit Einsatzdaten oder Verwaltung."""
    email = current_user(request) if enabled() else None
    return tenancy.access_for(email, request.cookies.get(SCOPE_COOKIE))


def _use_link(token):
    """Prüft den Link und entwertet ihn. Liefert die Adresse oder None."""
    email = _verify("link", token)
    with _lock:
        now = time.time()
        for t in [t for t, exp in _used_links.items() if exp < now]:
            del _used_links[t]
        if not email or token in _used_links:
            return None
        _used_links[token] = now + LINK_TTL
    return email


# ---------------------------------------------------------------- Mailversand
def send_link(email):
    """Schickt den Anmeldelink – still nichts, wenn die Adresse nicht berechtigt ist."""
    email = tenancy.normalize_email(email)
    if not tenancy.is_allowed(email):
        log.info("Anmeldung mit nicht berechtigter Adresse abgelehnt")
        return
    with _lock:
        if time.time() - _last_mail.get(email, 0) < RESEND_COOLDOWN:
            return
        _last_mail[email] = time.time()
    link = f"{BASE_URL}/auth/verify?token={_sign('link', email, LINK_TTL)}"
    if not RESEND_API_KEY:
        log.warning("RESEND_API_KEY fehlt – Anmeldelink für %s: %s", email, link)
        return
    body = {
        "from": MAIL_FROM, "to": [email], "subject": "Anmeldung Einsatzstatistik",
        "text": f"Hallo,\n\nmit diesem Link meldest du dich bei der Einsatzstatistik an:\n{link}\n\n"
                "Der Link gilt 15 Minuten und nur einmal. Wenn du keine Anmeldung angefordert hast, "
                "kannst du diese Mail ignorieren.",
        "html": f"<p>Hallo,</p><p>mit diesem Link meldest du dich bei der Einsatzstatistik an:</p>"
                f"<p><a href=\"{html.escape(link)}\">Jetzt anmelden</a></p>"
                "<p>Der Link gilt 15 Minuten und nur einmal. Wenn du keine Anmeldung angefordert hast, "
                "kannst du diese Mail ignorieren.</p>",
    }
    req = urllib.request.Request("https://api.resend.com/emails", data=json.dumps(body).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {RESEND_API_KEY}",
                                          "Content-Type": "application/json", "User-Agent": "pdf2einsatz"})
    try:
        urllib.request.urlopen(req, timeout=10).close()
    except (urllib.error.URLError, OSError) as e:
        detail = e.read().decode(errors="replace") if isinstance(e, urllib.error.HTTPError) else e
        log.error("Mailversand über Resend fehlgeschlagen: %s", detail)
        # Gleich wieder anfordern lassen statt 60 Sekunden ohne Mail
        with _lock:
            _last_mail.pop(email, None)


# ---------------------------------------------------------------- Seiten
def _page(content, status_code=200):
    return HTMLResponse(f"""<!doctype html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Anmeldung · Einsatzstatistik</title><link rel="icon" href="/static/img/app-icon.svg">
<link rel="stylesheet" href="/static/fonts/sansation.css"><link rel="stylesheet" href="/static/app.css">
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
def verify(token: str = Form("")):
    email = _use_link(token)
    if not email:
        return _login_form('<p class="message message-error">Der Link ist abgelaufen oder wurde schon benutzt. '
                           'Bitte einen neuen anfordern.</p>')
    log.info("Anmeldung: %s", email)
    tenancy.record_login(email)
    response = RedirectResponse("/", 303)
    response.set_cookie(COOKIE, _sign("session", email, SESSION_TTL), max_age=SESSION_TTL, httponly=True,
                        samesite="lax", secure=BASE_URL.startswith("https://"))
    return response


@router.post("/logout")
def logout():
    response = RedirectResponse("/login", 303)
    response.delete_cookie(COOKIE)
    response.delete_cookie(SCOPE_COOKIE)
    return response
