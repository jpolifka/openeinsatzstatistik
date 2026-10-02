# -*- coding: utf-8 -*-
"""
Einsatzstatistik – HTTP-Schnittstelle, Anmeldung, Zugriff je Wehr und Auslieferung der Oberfläche.

Jeder Endpunkt mit Einsatzdaten holt sich über access() die Rechte des Benutzers und die
ausgewählte Wehr (tenancy.Access) und arbeitet nur mit deren Datenbank und Fachkonfiguration.

Fachlogik liegt in report.py (PDF -> Einsatz), metrics.py (Auswertungen), store.py
(Datenbank) und excel_export.py; die Fachkonfiguration der Wehr in tenant_config.py.
"""
import contextlib
import datetime as dt
import io
import logging
import os
import re
import tempfile
import threading
import time
import unicodedata
import uuid
import zipfile
from typing import List, Optional

from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, create_model

from app import auth, db, excel_export, legacy, metrics, report, store, tenancy
from app.tenancy import INCIDENTS, STATS, WRITE
from app.timeutil import year_of

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("pdf2einsatz")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, "static")
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


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
    yield


app = FastAPI(title="Einsatzstatistik", lifespan=lifespan)
# JSON der Einsatzliste schrumpft komprimiert auf ca. 1/16
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


app.include_router(auth.router)

# Ohne Anmeldung erreichbar: Health-Check, Anmeldeseiten und Logos/CSS/JS (keine Einsatzdaten)
PUBLIC_PATHS = ("/health", "/login", "/logout", "/auth/", "/static/")


@app.middleware("http")
async def require_login(request: Request, call_next):
    """Anmeldung per Magic Link, wenn ADMIN_EMAILS gesetzt ist (siehe auth.py)."""
    path = request.url.path
    if auth.enabled() and not path.startswith(PUBLIC_PATHS) and not auth.current_user(request):
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


@app.exception_handler(tenancy.Forbidden)
async def forbidden(_request, exc):
    return JSONResponse({"detail": str(exc)}, status_code=403)


def access(request: Request) -> tenancy.Access:
    """Rechte des angemeldeten Benutzers und ausgewählte Wehr (ohne Anmeldung: Superadmin)."""
    email = auth.current_user(request) if auth.enabled() else None
    return tenancy.access_for(email, request.cookies.get(auth.SCOPE_COOKIE))


# ---------------------------------------------------------------- PDF-Vorschau im Speicher
class PreviewSessions:
    """Gelesene Berichte bis zur Übernahme. Liegt im Prozess – daher nur ein uvicorn-Worker.

    Eine Vorschau gehört dem Benutzer, der sie angelegt hat, und der Wehr, für die gelesen wurde."""
    TTL = 60 * 60

    def __init__(self):
        self._sessions = {}
        self._lock = threading.Lock()

    def add(self, reports, owner, slug):
        token = uuid.uuid4().hex
        with self._lock:
            self._expire()
            self._sessions[token] = {"time": time.time(), "owner": owner, "slug": slug,
                                     "reports": {r["filename"]: r for r in reports}}
        return token

    def get(self, token, filename, owner):
        """(bericht, slug) oder (None, None), auch wenn die Vorschau einem anderen Benutzer gehört."""
        with self._lock:
            session = self._sessions.get(token)
        if not session or session["owner"] != owner or filename not in session["reports"]:
            return None, None
        return session["reports"][filename], session["slug"]

    def _expire(self):
        cutoff = time.time() - self.TTL
        for token in [t for t, s in self._sessions.items() if s["time"] < cutoff]:
            del self._sessions[token]


previews = PreviewSessions()


# ---------------------------------------------------------------- Hilfsfunktionen
def _safe_filename(name):
    name = unicodedata.normalize("NFC", name or "").replace("\\", "/").split("/")[-1]
    return re.sub(r"[^\w.\- äöüÄÖÜß()]", "_", name) or "datei"


def _rounded(value):
    return round(value, 1) if isinstance(value, float) else value


def _resolve_year(con, year):
    return year or store.latest_year(con) or dt.date.today().year


def incident_key(tenant, incident_id):
    """Eindeutige Einsatz-ID über alle Wehren: "<slug>:<id>"."""
    return f"{tenant.slug}:{incident_id}" if incident_id is not None else None


def parse_incident_key(key):
    slug, _, number = key.partition(":")
    if not number.isdigit():
        raise HTTPException(404, "Einsatz nicht gefunden.")
    return slug, int(number)


def incident_json(incident, leaders, tenant, limit=None):
    """Einsatz mit Kennzahlen für die Oberfläche. leaders: store.LeaderNames für die EHF-Auswahl."""
    cfg = tenant.config
    m = metrics.incident_metrics(incident, cfg, limit)
    vehicles = []
    for call_sign in cfg.vehicles:
        v, vm = incident["vehicles"].get(call_sign) or {}, m["vehicles"].get(call_sign) or {}
        vehicles.append({"call_sign": call_sign, "substitute": cfg.substitute_label(v.get("name"), call_sign),
                         "crew": v.get("crew"), "departed": v.get("departed"), "arrived": v.get("arrived"),
                         "turnout_min": _rounded(vm.get("turnout_min")),
                         "arrival_min": _rounded(vm.get("arrival_min"))})
    return {
        "id": incident_key(tenant, incident.get("id")),
        "tenant": tenant.slug,
        **{name: incident.get(name) for name in ("year", *store.FIELDS, "source", "filename", "warnings")},
        "weekend_or_holiday": bool(incident.get("weekend_or_holiday")),
        **{name: _rounded(m[name]) for name in ("daytime", "duration_min", "turnout_min", "arrival_min", "on_time",
                                                 "crew_on_arrival", "crew_within_limit", "crew_within_second",
                                                 "crew_total")},
        "vehicles": vehicles,
        "people": [{"id": p["id"], "name": p["name"], "role": p.get("role"), "vehicle": p.get("vehicle"),
                    "new": p.get("new", False), "leader_name": leaders.spelling(p),
                    "leader": leaders.is_leader(incident.get("unit_leader"), p)} for p in incident["people"]],
    }


# ---------------------------------------------------------------- Seiten
@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/config")
def api_config(a: tenancy.Access = Depends(access)):
    """Fachkonfiguration der ausgewählten Wehr, Benutzer, Rechte und Auswahl der Wehren."""
    tenant = a.selected
    cfg = tenant.config if tenant else tenancy.TenantConfig(name="Einsatzstatistik")
    return {**cfg.client_config(), "user": a.email, "superadmin": a.superadmin, "roles": a.roles,
            "tenant": tenant.json() if tenant else None,
            "permissions": sorted(tenant.permissions) if tenant else [], "scopes": a.scopes()}


class Scope(BaseModel):
    key: str


@app.post("/api/scope")
def api_scope(scope: Scope, response: Response, a: tenancy.Access = Depends(access)):
    """Wehr auswählen ("t:<slug>"); nur unter den eigenen Wehren."""
    if scope.key not in {s["key"] for s in a.scopes()}:
        raise HTTPException(403, "Keine Berechtigung für diese Wehr.")
    response.set_cookie(auth.SCOPE_COOKIE, scope.key, max_age=auth.SESSION_TTL, httponly=True, samesite="lax",
                        secure=auth.BASE_URL.startswith("https://"))
    return {"ok": True}


# ---------------------------------------------------------------- Auswertung
@app.get("/api/years")
def api_years(a: tenancy.Access = Depends(access)):
    with a.current(STATS).connection() as con:
        return {"years": store.years(con), "today": dt.date.today().isoformat()}


@app.get("/api/evaluation")
def api_evaluation(year: Optional[int] = None, limit: Optional[int] = None, a: tenancy.Access = Depends(access)):
    """Auswertung der ausgewählten Wehr. Ohne Recht auf Einsätze/Personal ohne Anwesenheit (Namen)."""
    tenant = a.current(STATS)
    cfg = tenant.config
    limit = limit or cfg.default_limit
    if limit not in cfg.response_limits:
        allowed = " oder ".join(str(x) for x in cfg.response_limits)
        raise HTTPException(400, f"Die Zeitgrenze muss {allowed} Minuten sein.")
    with tenant.connection() as con:
        year = _resolve_year(con, year)
        current = metrics.evaluate(store.load_incidents(con, year=year), cfg, limit)
        previous = store.load_incidents(con, year=year - 1) or None
        history = metrics.monthly_history(store.incident_months(con))
    return {"year": year,
            "history": history,
            "statistics": metrics.statistics(current, year, cfg, previous),
            "response_plan": metrics.response_plan(current, limit, cfg),
            "response_plan_previous": metrics.response_plan(metrics.evaluate(previous, cfg, limit), limit, cfg)
            if previous else None,
            "attendance": metrics.attendance_overview(current) if tenant.can(INCIDENTS) else None}


# ---------------------------------------------------------------- Einsätze
IncidentFields = create_model(
    "IncidentFields",
    **{name: (Optional[int] if name in store.INT_FIELDS else Optional[str], None) for name in store.FIELDS})


@app.get("/api/incidents")
def api_incidents(year: Optional[int] = None, a: tenancy.Access = Depends(access)):
    tenant = a.current(INCIDENTS)
    with tenant.connection() as con:
        year = _resolve_year(con, year)
        leaders = store.LeaderNames(con)
        return {"year": year,
                "incidents": [incident_json(i, leaders, tenant) for i in store.load_incidents(con, year=year)]}


@app.put("/api/incidents/{key}")
def api_update_incident(key: str, fields: IncidentFields, a: tenancy.Access = Depends(access)):
    slug, incident_id = parse_incident_key(key)
    tenant = a.tenant(slug, WRITE)
    with tenant.connection() as con:
        try:
            store.update_incident(con, incident_id, fields.model_dump(exclude_unset=True), modified_by=a.email)
        except KeyError:
            raise HTTPException(404, "Einsatz nicht gefunden.")
        except store.DuplicateIncident as e:
            raise HTTPException(409, str(e))
        return incident_json(store.load_incident(con, incident_id), store.LeaderNames(con), tenant)


@app.delete("/api/incidents/{key}")
def api_delete_incident(key: str, a: tenancy.Access = Depends(access)):
    slug, incident_id = parse_incident_key(key)
    with a.tenant(slug, WRITE).connection() as con:
        store.delete_incident(con, incident_id)
    log.info("Einsatz %s gelöscht von %s", key, a.email or "lokal")
    return {"ok": True}


# ---------------------------------------------------------------- PDF einlesen
ZIP_MAX_PDFS = 500
ZIP_MAX_BYTES = 50 * 1024 * 1024  # je entpackter PDF


def _is_upload(filename):
    return (filename or "").lower().endswith((".pdf", ".zip"))


def _unique_filename(filename, taken):
    """Gleichnamige PDFs (z. B. aus Unterordnern einer ZIP) durchnummerieren."""
    stem, ext = os.path.splitext(filename)
    candidate, n = filename, 2
    while candidate in taken:
        candidate, n = f"{stem} ({n}){ext}", n + 1
    taken.add(candidate)
    return candidate


def _unpack_zip(data, zip_name, errors):
    """PDFs aus einer ZIP-Datei holen -> [(dateiname, inhalt)]. Andere Dateien werden übergangen."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        errors.append({"file": zip_name, "message": "Keine gültige ZIP-Datei."})
        return []
    entries = [i for i in archive.infolist() if not i.is_dir() and i.filename.lower().endswith(".pdf")
               and not i.filename.startswith("__MACOSX/") and not os.path.basename(i.filename).startswith("._")]
    if not entries:
        errors.append({"file": zip_name, "message": "Die ZIP-Datei enthält keine PDF."})
    if len(entries) > ZIP_MAX_PDFS:
        errors.append({"file": zip_name, "message": f"Mehr als {ZIP_MAX_PDFS} PDFs, nur die ersten werden gelesen."})
        entries = entries[:ZIP_MAX_PDFS]
    files = []
    for info in entries:
        name = _safe_filename(info.filename)
        if info.file_size > ZIP_MAX_BYTES:
            errors.append({"file": name, "message": "PDF in der ZIP-Datei ist zu groß."})
            continue
        try:
            files.append((name, archive.read(info)))
        except Exception as e:  # verschlüsselt oder beschädigt
            errors.append({"file": name, "message": f"Nicht entpackbar ({e or type(e).__name__})."})
    return files


def _read_uploads(uploads, cfg):
    """Hochgeladene PDFs und ZIP-Dateien lesen -> (berichte, fehler)."""
    reports, errors, files = [], [], []
    for upload in uploads:
        filename, data = _safe_filename(upload.filename), upload.file.read()
        files += _unpack_zip(data, filename, errors) if filename.lower().endswith(".zip") else [(filename, data)]
    taken = set()
    with tempfile.TemporaryDirectory() as tmp:
        for filename, data in files:
            filename = _unique_filename(filename, taken)
            path = os.path.join(tmp, filename)
            with open(path, "wb") as fh:
                fh.write(data)
            try:
                reports.append(report.read_pdf(path, filename, cfg))
            except Exception as e:  # defekte oder fremde PDF: melden, Rest weiter lesen
                log.exception("PDF %s", filename)
                errors.append({"file": filename, "message": str(e) or type(e).__name__})
    return reports, errors


def _preview_json(con, r, leaders, tenant):
    incident, existing = report.preview(con, r)
    result = incident_json(incident, leaders, tenant)
    result["reported_as"] = r["reported_as"]
    result["incident_commander"] = r["incident_commander"]
    result["existing"] = {"id": incident_key(tenant, existing["id"]), "source": existing["source"],
                          "differences": report.differences(existing, incident, tenant.config)} if existing else None
    return result


@app.post("/api/reports")
def api_read_reports(pdfs: List[UploadFile] = File(...), a: tenancy.Access = Depends(access)):
    tenant = a.current(WRITE)
    pdfs = [p for p in pdfs if _is_upload(p.filename)]
    if not pdfs:
        raise HTTPException(400, "Bitte eine PDF- oder ZIP-Datei (Einsatzberichte aus dem BKS-Portal) auswählen.")
    reports, errors = _read_uploads(pdfs, tenant.config)
    with tenant.connection() as con:
        leaders = store.LeaderNames(con)
        previews_json = [_preview_json(con, r, leaders, tenant) for r in reports]
    return {"token": previews.add(reports, a.email, tenant.slug), "reports": previews_json, "errors": errors}


class Acceptance(BaseModel):
    token: str
    filename: str
    fields: IncidentFields
    replace: bool = False


@app.post("/api/reports/accept")
def api_accept_report(acceptance: Acceptance, a: tenancy.Access = Depends(access)):
    r, slug = previews.get(acceptance.token, acceptance.filename, a.email)
    if not r:
        raise HTTPException(410, "Die Vorschau ist abgelaufen – bitte die PDF erneut einlesen.")
    tenant = a.tenant(slug, WRITE)
    fields = {**report.to_fields(r), **acceptance.fields.model_dump(exclude_unset=True)}
    with tenant.connection() as con:
        replace_id = store.find_incident(con, year_of(fields.get("started_at")),
                                         store.to_int(fields.get("number"))) if acceptance.replace else None
        try:
            incident_id = report.save(con, r, fields, replace_id, modified_by=a.email)
        except store.DuplicateIncident as e:
            raise HTTPException(409, str(e))
        return incident_json(store.load_incident(con, incident_id), store.LeaderNames(con), tenant)


# ---------------------------------------------------------------- Export
@app.get("/api/export")
def api_export(year: Optional[int] = None, a: tenancy.Access = Depends(access)):
    """Excel im Format der Einsatzübersicht (Spalten A:AV + Anwesenheit)."""
    tenant = a.current(INCIDENTS)
    with tenant.connection() as con:
        year = _resolve_year(con, year)
        incidents = store.load_incidents(con, year=year)
        members = store.members_of_year(con, year)
    if not incidents:
        raise HTTPException(404, "Keine Einsätze für den Export.")
    buffer = io.BytesIO()
    excel_export.write_workbook(incidents, members, year, buffer, tenant.config)
    buffer.seek(0)
    stamp = f"{dt.datetime.now():%Y-%m-%d_%H%M}"
    name = f"Einsaetze_{tenant.slug}_{year}_{stamp}.xlsx"
    return StreamingResponse(buffer, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{name}"'})
