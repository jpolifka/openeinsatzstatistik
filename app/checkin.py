# -*- coding: utf-8 -*-
"""Anmeldung zum Übungsdienst per QR-Code, ohne Benutzerkonto.

Der Link `/checkin/<Wehr>.<Signatur>` steht auf einem Aushang und verfällt nie (nur „Neuen Code erzeugen“ macht ihn
ungültig; die Signatur ist ein HMAC über Wehr und Zähler `checkin_rev`). Er allein berechtigt aber zu nichts: Die
Seite verlangt die PIN der Übung (`training.checkin_pin`, gilt bis zum Neuerzeugen, siehe `trainings.check_in`)
und legt keine Übung an. Eingaben landen in einer Warteschlange und werden erst von der Übungsleitung in Personenstamm
und Teilnahme übernommen. Die Seite zeigt nie Namen aus dem Personenstamm und schreibt nur in Wehren, deren VG einen
gültigen AVV hat (wie `tenancy.access_for`).
"""
import datetime as dt
import hmac
import html
import json
import threading
import time

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from app import auth, tenancy, theme, trainings

router = APIRouter()

PATH = "/checkin/"
LIMITS = {"client": (20, 60), "tenant": (120, 60)}     # Anmeldungen je Zeitraum (Anzahl, Sekunden)
_lock = threading.Lock()
_hits = {}      # (Art, Schlüssel) → Zeitpunkte der letzten Anfragen


def _rev(con):
    row = con.execute("SELECT value FROM setting WHERE key = 'checkin_rev'").fetchone()
    return int(json.loads(row[0])) if row else 0


def _signature(slug, rev):
    return auth._mac("checkin", f"{slug}|{rev}")


def token_for(tenant):
    """Aktuelles Token einer Wehr (für den QR-Code in der Verwaltung)."""
    with tenant.connection() as con:
        return f"{tenant.slug}.{_signature(tenant.slug, _rev(con))}"


def rotate(tenant):
    """Alle bisherigen QR-Codes der Wehr ungültig machen."""
    with tenant.connection() as con:
        con.execute("INSERT INTO setting (key, value) VALUES ('checkin_rev', ?) ON CONFLICT(key) DO UPDATE SET "
                    "value = ?", (str(_rev(con) + 1),) * 2)


def link_for(tenant, fallback=""):
    """Vollständiger Link; die Basis kommt aus der Konfiguration (BASE_URL, Subdomain der VG), nie aus der Anfrage.
    Nur ohne BASE_URL (lokale Entwicklung) dient `fallback` (Adresse der Verwaltungsanfrage)."""
    return f"{auth.vg_base(tenant.vg_id) or fallback.rstrip('/')}{PATH}{token_for(tenant)}"


def resolve(token):
    """Wehr zu einem gültigen Token, sonst None (auch für gesperrte VGs ohne AVV und archivierte Wehren)."""
    slug, _, signature = (token or "").rpartition(".")
    if not slug or not signature:
        return None
    with tenancy.central() as con:
        row = con.execute(
            "SELECT t.id, t.slug, t.name, t.vg_id, v.slug AS vg_slug, v.name AS vg_name FROM tenant t "
            "JOIN vg v ON v.id = t.vg_id WHERE t.active AND t.slug = ? AND t.vg_id IN "
            "(SELECT vg_id FROM dpa WHERE status IN ('signed', 'not_required'))", (slug,)).fetchone()
    if not row:
        return None
    tenant = tenancy.Tenant(row["id"], row["slug"], row["name"], row["vg_id"], row["vg_slug"], row["vg_name"],
                            frozenset())
    with tenant.connection() as con:
        expected = _signature(slug, _rev(con))
    return tenant if hmac.compare_digest(signature, expected) else None


def _allowed(kind, key):
    count, seconds = LIMITS[kind]
    now = time.time()
    with _lock:
        recent = [t for t in _hits.get((kind, key), ()) if now - t < seconds]
        if len(recent) >= count:
            _hits[(kind, key)] = recent
            return False
        _hits[(kind, key)] = recent + [now]
        if len(_hits) > 5000:       # alte Schlüssel aufräumen
            for k in [k for k, v in _hits.items() if not v or now - v[-1] > 3600]:
                del _hits[k]
    return True


def _page(tenant, body, status=200):
    e = html.escape
    return HTMLResponse(f"""<!doctype html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex"><title>Übung · {e(tenant.name)}</title><link rel="icon" href="/static/favicon.svg">
<link rel="stylesheet" href="/static/app.css"><style>{theme.css(theme.NEUTRAL)}
.checkin{{max-width:28rem;margin:1.5rem auto}}.checkin label{{display:block;margin-top:.8rem}}
.checkin input{{width:100%;font-size:1.1rem;padding:.6rem}}.checkin button{{margin-top:1.2rem;font-size:1.1rem;
padding:.7rem 1.2rem}}</style></head><body><main class="page"><div class="card checkin">
<p class="topbar-kicker">{e(tenant.name)}</p><h1>Übungsdienst</h1>{body}</div></main></body></html>""",
                        status_code=status, headers={"Cache-Control": "no-store"})


def _form(first="", last="", error="", pin=""):
    e = html.escape
    notice = f'<p role="alert"><strong>{e(error)}</strong></p>' if error else ""
    return (f'{notice}<p>Bitte die PIN der Übung (nennt die Übungsleitung) und deinen Namen eintragen.</p>'
            f'<form method="post"><label>PIN<input name="pin" value="{e(pin)}" maxlength="12" required '
            f'inputmode="numeric" autocomplete="off"></label>'
            f'<label>Vorname<input name="first_name" value="{e(first)}" maxlength="60" '
            f'autocomplete="given-name" autocapitalize="words"></label>'
            f'<label>Nachname<input name="last_name" value="{e(last)}" maxlength="60" required '
            f'autocomplete="family-name" autocapitalize="words"></label>'
            f'<button type="submit" class="primary">Anmelden</button></form>')


def _not_found():
    return HTMLResponse("<!doctype html><meta charset=\"utf-8\"><title>Nicht gefunden</title>"
                        "<p>Dieser Link ist nicht (mehr) gültig.</p>", status_code=404,
                        headers={"Cache-Control": "no-store"})


@router.get(PATH + "{token}", include_in_schema=False)
def show(token: str):
    tenant = resolve(token)
    return _page(tenant, _form()) if tenant else _not_found()


@router.post(PATH + "{token}", include_in_schema=False)
def register(token: str, request: Request, first_name: str = Form(""), last_name: str = Form(""),
             pin: str = Form("")):
    host = request.client.host if request.client else "?"
    if not _allowed("client", host):
        return HTMLResponse("<!doctype html><meta charset=\"utf-8\"><p>Zu viele Anmeldungen. "
                            "Bitte später erneut versuchen.</p>", status_code=429)
    tenant = resolve(token)
    if not tenant:
        return _not_found()
    if not _allowed("tenant", tenant.slug):
        return _page(tenant, "<p>Zu viele Anmeldungen. Bitte später erneut versuchen.</p>", 429)
    now = dt.datetime.now()
    try:
        with tenant.connection() as con:
            found = trainings.check_in(con, pin, last_name, first_name, now)
    except trainings.Locked as e:
        return _page(tenant, f'<p role="alert"><strong>{html.escape(str(e))}</strong></p>', 429)
    except ValueError as e:
        return _page(tenant, _form(first_name, last_name, str(e), pin), 422)
    if found is None:       # absichtlich nicht unterscheiden: falsche PIN, keine Übung heute, abgelaufene PIN
        return _page(tenant, _form(first_name, last_name, "Die PIN ist ungültig "
                                   "", ""), 403)
    name = html.escape(" ".join(f"{first_name} {last_name}".split()))
    return _page(tenant, f"<p>Danke, <strong>{name}</strong>. Deine Anmeldung ist bei der Übungsleitung eingegangen "
                         f"und wird dort bestätigt.</p>"
                         f'<p><a href="{PATH}{html.escape(token)}">Weitere Person anmelden</a></p>')
