# -*- coding: utf-8 -*-
"""
Einsatzstatistik – HTTP-Schnittstelle, Anmeldung, Zugriff je Wehr und Auslieferung der Oberfläche.

Jeder Endpunkt mit Einsatzdaten holt sich über access() die Rechte des Benutzers und die
ausgewählte Wehr (tenancy.Access) und arbeitet nur mit deren Datenbank und Fachkonfiguration.

Hier liegen nur Anwendung, Anmeldeprüfung, Oberfläche, Theme, Konfiguration und Auswahl der Wehr. Die Endpunkte
mit Einsatzdaten stehen in app/api/ (evaluation, incidents, reports, records, export), das Einlesen der
Berichte in importing.py. Fachlogik liegt in report.py (PDF -> Einsatz), metrics.py (Auswertungen), store.py
(Datenbank) und excel_export.py; die Fachkonfiguration der Wehr in tenant_config.py.
"""
import asyncio
import contextlib
import logging
import os

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import admin, importing, auth, db, dpa, feedback, import_queue, mail, legacy, rbac, tenancy, theme
from app.rbac import STATS
from app.request_limits import RequestSizeLimit
from app.incident_schema import FORM_FIELDS
from app.api import evaluation, export, incidents, records, reports
from app.api.common import selection_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("pdf2einsatz")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, "static")


@contextlib.asynccontextmanager
async def lifespan(_app):
    # Nicht still ungeschützt starten, wenn noch eine alte Zugangs-Konfiguration gesetzt ist
    if os.environ.get("APP_PASSWORD") and not auth.enabled():
        raise RuntimeError("APP_PASSWORD wird nicht mehr unterstützt – ADMIN_EMAILS setzen (siehe README)")
    if legacy.legacy_emails() and not auth.enabled():
        raise RuntimeError("AUTH_EMAILS wird nicht mehr unterstützt – ADMIN_EMAILS setzen (siehe README)")
    if not db.DATA_DIR:
        raise RuntimeError("DATA_DIR fehlt (siehe README)")
    auth.check_config()
    if legacy.needs_migration(db.DATA_DIR):
        legacy.migrate_single_install(db.DATA_DIR)
    elif legacy.legacy_emails():
        log.warning("AUTH_EMAILS wird ignoriert – Benutzer werden in der Verwaltung den Wehren zugeordnet")
    tenancy.setup()
    def active_tenants():
        from app import tenant_lifecycle
        tenant_lifecycle.retry_archives()
        with tenancy.central() as con:
            vg_ids = [row[0] for row in con.execute("SELECT id FROM vg")]
        return [tenant for vg_id in vg_ids for tenant in tenancy.vg_tenants(vg_id)]
    stop = asyncio.Event()
    worker = asyncio.create_task(import_queue.run_worker(stop, active_tenants, importing.after_import))
    mail.log_check()
    try:
        yield
    finally:
        stop.set()
        await worker


app = FastAPI(title="Einsatzstatistik", lifespan=lifespan)
# JSON der Einsatzliste schrumpft komprimiert auf ca. 1/16
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(RequestSizeLimit)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(dpa.router)
app.include_router(feedback.router)
for _module in (evaluation, incidents, reports, records, export):
    app.include_router(_module.router)

# Ohne Anmeldung erreichbar: Health-Check, Anmeldeseiten und Logos/CSS/JS (keine Einsatzdaten)
PUBLIC_PATHS = ("/health", "/login", "/logout", "/auth/", "/static/")


@app.middleware("http")
async def require_login(request: Request, call_next):
    """Anmeldung per Magic Link, wenn ADMIN_EMAILS gesetzt ist (siehe auth.py)."""
    path = request.scope["path"]
    public = path in ("/health", "/login", "/logout") or path.startswith(("/auth/", "/static/"))
    if auth.enabled() and not public and not auth.current_user(request):
        # Direkt im Browser geöffnete API-Adressen (z. B. Export) auch zur Anmeldeseite
        if path.startswith("/api/") and "text/html" not in request.headers.get("accept", ""):
            return JSONResponse({"detail": "Anmeldung erforderlich"}, status_code=401)
        return RedirectResponse("/login", 303)
    return await call_next(request)


@app.middleware("http")
async def revalidate_frontend(request: Request, call_next):
    """Oberfläche bei jedem Laden beim Server prüfen lassen (ETag), damit nach einem Update
    kein altes app.js aus dem Browser-Cache läuft."""
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


# Schutzheader für alle Antworten. Antworten mit eigener Richtlinie (Logos, AVV-Dokument) behalten sie.
# Die Oberfläche hat keine Inline-Skripte; Inline-Styles werden genutzt (Wehr-Farben, style-Attribute).
SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                               "img-src 'self' data:; font-src 'self'; connect-src 'self'; form-action 'self'; "
                               "frame-ancestors 'none'; base-uri 'none'; object-src 'none'",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}
if auth.BASE_URL.startswith("https://"):
    SECURITY_HEADERS["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    for name, value in SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    return response


@app.exception_handler(tenancy.Forbidden)
async def forbidden(_request, exc):
    return JSONResponse({"detail": str(exc)}, status_code=403)


access = auth.access







# ---------------------------------------------------------------- Seiten
@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/health")
def health():
    return {"status": "ok"}


def _branding(tenant):
    """Adressen der Logos einer Wehr (mit Stand als Cache-Schlüssel); None = neutrales Signet."""
    urls = dict.fromkeys(("logo_light", "logo_dark", "icon"))
    if tenant:
        with tenant.connection() as con:
            for row in con.execute("SELECT name, modified FROM asset"):
                key = row["name"].replace("-", "_")
                if key in urls:
                    urls[key] = f"/api/branding/{tenant.slug}/{row['name']}?v={row['modified'].replace(' ', 'T')}"
    return urls


@app.get("/api/theme.css")
def api_theme(a: tenancy.Access = Depends(access)):
    """Farben der ausgewählten Wehr; in der Gesamtansicht einer VG das neutrale Farbschema."""
    colors = a.selected.config.colors if a.selected else theme.NEUTRAL
    return Response(theme.css(colors), media_type="text/css", headers={"Cache-Control": "no-cache"})


@app.get("/api/branding/{slug}/{name}")
def api_branding(slug: str, name: str, a: tenancy.Access = Depends(access)):
    """Logo einer Wehr, für alle mit Zugriff auf diese Wehr."""
    tenant = a.tenant(slug, STATS)
    with tenant.connection() as con:
        row = con.execute("SELECT content_type, data FROM asset WHERE name = ?", (name,)).fetchone()
    if not row:
        raise HTTPException(404, "Kein Logo hinterlegt.")
    # Eigener Ursprung, aber nie als Dokument mit Skripten ausführen (auch nicht das SVG-Symbol der Übernahme)
    return Response(row["data"], media_type=row["content_type"], headers={
        "X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=86400",
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox"})


@app.get("/api/config")
def api_config(a: tenancy.Access = Depends(access)):
    """Fachkonfiguration der Auswahl, Benutzer, Rechte und Auswahlmöglichkeiten.

    permissions: Rechte, die für mindestens eine Wehr der Auswahl gelten (für das Ein- und
    Ausblenden; geprüft wird je Endpunkt). tenants: die ausgewählten Wehren.
    """
    tenants = a.selection
    cfg = selection_config(tenants, a) if tenants else tenancy.TenantConfig(name="Einsatzstatistik")
    return {**cfg.client_config(), "incident_fields": FORM_FIELDS, "name": cfg.name, "user": a.email, "superadmin": a.superadmin, "roles": a.roles,
            "scope": a.scope_key, "vg": {"slug": a.vg, "name": a.vgs[a.vg]} if a.vg else None,
            "tenant": a.selected.json() if a.selected else None, "tenants": [t.json() for t in tenants],
            "branding": _branding(a.selected), "dpa_blocked": a.blocked,
            "feedback": feedback.enabled() and bool(a.email),
            "vg_permissions": sorted(_vg_permissions(a, tenants)), "admin": admin.has_admin(a),
            "permissions": sorted(set().union(*(t.permissions for t in tenants))), "scopes": a.scopes()}


def _vg_permissions(a, tenants):
    """Rechte auf Ebene der VG für die Gesamtansicht (Prüfprotokoll usw.); bei einer Wehr keine."""
    if not a.vg or not tenants:
        return set()
    return set(rbac.ALL_PERMISSIONS) if a.superadmin else set(a.vg_permissions.get(tenants[0].vg_id, ()))


class Scope(BaseModel):
    key: str


@app.post("/api/scope")
def api_scope(scope: Scope, response: Response, a: tenancy.Access = Depends(access)):
    """Wehr ("t:<slug>") oder Gesamtansicht einer VG ("vg:<slug>") auswählen; nur unter den eigenen."""
    if scope.key not in {s["key"] for s in a.scopes()}:
        raise HTTPException(403, "Keine Berechtigung für diese Auswahl.")
    response.set_cookie(auth.SCOPE_COOKIE, scope.key, max_age=auth.SESSION_TTL, httponly=True, samesite="lax",
                        secure=auth.BASE_URL.startswith("https://"))
    return {"ok": True}


