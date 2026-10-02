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

from app import admin, auth, db, dpa, mail, excel_export, legacy, metrics, pdf_report, report, store, tenancy, tenant_config, theme
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
    mail.log_check()
    yield


app = FastAPI(title="Einsatzstatistik", lifespan=lifespan)
# JSON der Einsatzliste schrumpft komprimiert auf ca. 1/16
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(dpa.router)

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


access = auth.access


# ---------------------------------------------------------------- PDF-Vorschau im Speicher
class PreviewSessions:
    """Gelesene Berichte bis zur Übernahme. Liegt im Prozess – daher nur ein uvicorn-Worker.

    Eine Vorschau gehört dem Benutzer, der sie angelegt hat, und der Wehr, für die gelesen wurde."""
    TTL = 60 * 60

    def __init__(self):
        self._sessions = {}
        self._lock = threading.Lock()

    def add(self, reports, owner):
        """reports: [(bericht, slug der Wehr, für die er gelesen wurde)]."""
        token = uuid.uuid4().hex
        with self._lock:
            self._expire()
            self._sessions[token] = {"time": time.time(), "owner": owner,
                                     "reports": {r["filename"]: (r, slug) for r, slug in reports}}
        return token

    def get(self, token, filename, owner):
        """(bericht, slug) oder (None, None), auch wenn die Vorschau einem anderen Benutzer gehört."""
        with self._lock:
            session = self._sessions.get(token)
        if not session or session["owner"] != owner or filename not in session["reports"]:
            return None, None
        return session["reports"][filename]

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


def incident_key(tenant, incident_id):
    """Eindeutige Einsatz-ID über alle Wehren: "<slug>:<id>"."""
    return f"{tenant.slug}:{incident_id}" if incident_id is not None else None


def parse_incident_key(key):
    slug, _, number = key.partition(":")
    if not number.isdigit():
        raise HTTPException(404, "Einsatz nicht gefunden.")
    return slug, int(number)


def incident_json(incident, leaders, tenant, limit=None, cfg=None):
    """Einsatz mit Kennzahlen für die Oberfläche. leaders: store.LeaderNames für die EHF-Auswahl.
    cfg: abweichende Konfiguration (Vorschau mit neu entdeckten Fahrzeugen), sonst die der Wehr."""
    cfg = cfg or tenant.config
    m = metrics.incident_metrics(incident, cfg, limit)
    vehicles = []
    for call_sign in cfg.vehicles_for(incident):
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


def _selection_config(tenants, a):
    """Konfiguration der Auswahl: die der einen Wehr oder die vereinigte der VG-Gesamtansicht."""
    if len(tenants) == 1 and not a.vg:
        return tenants[0].config
    return tenant_config.combine(a.vgs.get(a.vg, "Alle Wehren"), [t.config for t in tenants])


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
    cfg = _selection_config(tenants, a) if tenants else tenancy.TenantConfig(name="Einsatzstatistik")
    return {**cfg.client_config(), "name": cfg.name, "user": a.email, "superadmin": a.superadmin, "roles": a.roles,
            "scope": a.scope_key, "vg": {"slug": a.vg, "name": a.vgs[a.vg]} if a.vg else None,
            "tenant": a.selected.json() if a.selected else None, "tenants": [t.json() for t in tenants],
            "branding": _branding(a.selected), "dpa_blocked": a.blocked,
            "permissions": sorted(set().union(*(t.permissions for t in tenants))), "scopes": a.scopes()}


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


def _filtered(tenants, only):
    """Wehr-Filter der Gesamtansicht (?tenants=a,b); ohne Filter alle."""
    if not only:
        return tenants
    wanted = set(only.split(","))
    chosen = [t for t in tenants if t.slug in wanted]
    if not chosen:
        raise HTTPException(400, "Keine der gewählten Wehren ist in der Auswahl.")
    return chosen


def _latest_year(tenants):
    years = []
    for t in tenants:
        with t.connection() as con:
            years.append(store.latest_year(con))
    return max((y for y in years if y), default=dt.date.today().year)


# ---------------------------------------------------------------- Auswertung
@app.get("/api/years")
def api_years(a: tenancy.Access = Depends(access)):
    counts = {}
    for t in a.selection_with(STATS):
        with t.connection() as con:
            for row in store.years(con):
                entry = counts.setdefault(row["year"], {"year": row["year"], "count": 0, "last_number": None})
                entry["count"] += row["count"]
                entry["last_number"] = row["last_number"] if len(a.selection) == 1 else None
    return {"years": [counts[y] for y in sorted(counts)], "today": dt.date.today().isoformat()}


def _evaluate(tenants, year, limit):
    """Einsätze des Jahres und des Vorjahres je Wehr, jeweils mit der eigenen Konfiguration ausgewertet."""
    parts, months = [], {}
    for t in tenants:
        cfg = t.config
        with t.connection() as con:
            current = metrics.evaluate(store.load_incidents(con, year=year), cfg, limit)
            previous = store.load_incidents(con, year=year - 1)
            for month, count in store.incident_months(con).items():
                months[month] = months.get(month, 0) + count
        parts.append((t, current, previous))
    return parts, months


@app.get("/api/evaluation")
def api_evaluation(year: Optional[int] = None, limit: Optional[int] = None, tenants: Optional[str] = None,
                   a: tenancy.Access = Depends(access)):
    """Auswertung der Auswahl – einer Wehr oder (summiert) mehrerer Wehren einer VG.

    Ohne Recht auf Einsätze/Personal kommt die Anwesenheit (Namen) nicht mit; in der
    Gesamtansicht gibt es sie nie (Kameraden gehören zu einer Wehr).
    """
    selection = _filtered(a.selection_with(STATS), tenants)
    cfg = _selection_config(selection, a)
    limit = limit or cfg.default_limit
    if limit not in cfg.response_limits:
        allowed = " oder ".join(str(x) for x in cfg.response_limits)
        raise HTTPException(400, f"Die Zeitgrenze muss {allowed} Minuten sein.")
    year = year or _latest_year(selection)
    parts, months = _evaluate(selection, year, limit)
    current = [e for _, evaluated, _ in parts for e in evaluated]
    previous = [i for _, _, prev in parts for i in prev]
    previous_evaluated = [e for t, _, prev in parts for e in metrics.evaluate(prev, t.config, limit)]
    single = len(selection) == 1 and not a.vg
    result = {"year": year,
              "history": metrics.monthly_history(months),
              "statistics": metrics.statistics(current, year, cfg, previous or None),
              "response_plan": metrics.response_plan(current, limit, cfg),
              "response_plan_previous": metrics.response_plan(previous_evaluated, limit, cfg) if previous else None,
              "attendance": metrics.attendance_overview(current) if single and selection[0].can(INCIDENTS) else None,
              "tenants": None}
    if not single:
        unique, without = metrics.unique_incidents([i for i, _ in current])
        result["tenants"] = {
            "participations": len(current), "unique": unique, "without_dispatch_number": without,
            "rows": [{"slug": t.slug, "name": t.name, **metrics.summary(evaluated, limit, t.config)}
                     for t, evaluated, _ in parts]}
    return result


# ---------------------------------------------------------------- Einsätze
IncidentFields = create_model(
    "IncidentFields",
    **{name: (Optional[int] if name in store.INT_FIELDS else Optional[str], None) for name in store.FIELDS})


@app.get("/api/incidents")
def api_incidents(year: Optional[int] = None, a: tenancy.Access = Depends(access)):
    """Einsätze der Auswahl; in der Gesamtansicht nur aus Wehren mit Recht auf Einsätze, nach Beginn sortiert."""
    tenants = a.selection_with(INCIDENTS)
    year = year or _latest_year(tenants)
    incidents = []
    for tenant in tenants:
        with tenant.connection() as con:
            leaders = store.LeaderNames(con)
            incidents += [incident_json(i, leaders, tenant) for i in store.load_incidents(con, year=year)]
    if len(tenants) > 1:
        incidents.sort(key=lambda i: (i["started_at"] or "", i["tenant"]))
    return {"year": year, "incidents": incidents}


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


def _read_pdf(path, filename, tenants):
    """Bericht lesen -> (bericht, wehr). Bei mehreren Wehren wird die passende über die Einheit bzw.
    die eigenen Fahrzeuge im Bericht gesucht; passt keine, ValueError."""
    if len(tenants) == 1:
        return report.read_pdf(path, filename, tenants[0].config), tenants[0]
    texts = pdf_report.extract_text(path)
    by_slug = {t.slug: t for t in tenants}
    slug = report.match_tenant(texts, filename, [(t.slug, t.config) for t in tenants])
    if not slug:
        raise ValueError("Der Bericht passt zu keiner der ausgewählten Wehren (Einheit und Fahrzeuge unbekannt).")
    return report.read_text(texts, filename, by_slug[slug].config), by_slug[slug]


def _read_uploads(uploads, tenants):
    """Hochgeladene PDFs und ZIP-Dateien lesen -> ([(bericht, wehr)], fehler)."""
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
                reports.append(_read_pdf(path, filename, tenants))
            except Exception as e:  # defekte oder fremde PDF: melden, Rest weiter lesen
                log.exception("PDF %s", filename)
                errors.append({"file": filename, "message": str(e) or type(e).__name__})
    return reports, errors


def _shared_with(r, tenant, a):
    """Andere sichtbare Wehren, die denselben Einsatz (Einsatznummer der Leitstelle) schon erfasst haben."""
    if not r.get("dispatch_number"):
        return []
    names = []
    for other in a.tenants.values():
        if other.slug != tenant.slug and other.can(STATS):
            with other.connection() as con:
                if con.execute("SELECT 1 FROM incident WHERE dispatch_number = ?", (r["dispatch_number"],)).fetchone():
                    names.append(other.name)
    return names


def _preview_json(r, tenant, a):
    cfg = tenant.config.with_new_vehicles(r.get("new_vehicles", ()), r.get("day"))
    with tenant.connection() as con:
        incident, existing = report.preview(con, r)
        result = incident_json(incident, store.LeaderNames(con), tenant, cfg=cfg)
    result["tenant_name"] = tenant.name
    result["new_vehicles"] = r.get("new_vehicles", [])
    result["reported_as"] = r["reported_as"]
    result["incident_commander"] = r["incident_commander"]
    result["existing"] = {"id": incident_key(tenant, existing["id"]), "source": existing["source"],
                          "differences": report.differences(existing, incident, tenant.config)} if existing else None
    result["shared_with"] = _shared_with(r, tenant, a)
    return result


@app.post("/api/reports")
def api_read_reports(pdfs: List[UploadFile] = File(...), a: tenancy.Access = Depends(access)):
    """Berichte lesen – für die ausgewählte Wehr oder, in der Gesamtansicht, verteilt auf die passende
    Wehr der VG (nur Wehren mit Schreibrecht)."""
    tenants = a.selection_with(WRITE) if a.vg else [a.current(WRITE)]
    pdfs = [p for p in pdfs if _is_upload(p.filename)]
    if not pdfs:
        raise HTTPException(400, "Bitte eine PDF- oder ZIP-Datei (Einsatzberichte aus dem BKS-Portal) auswählen.")
    reports, errors = _read_uploads(pdfs, tenants)
    previews_json = [_preview_json(r, tenant, a) for r, tenant in reports]
    token = previews.add([(r, tenant.slug) for r, tenant in reports], a.email)
    return {"token": token, "reports": previews_json, "errors": errors}


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
    if r.get("new_vehicles"):
        tenancy.forget_config(tenant.slug)
        log.info("Fahrzeuge %s in die Liste von %s aufgenommen", ", ".join(r["new_vehicles"]), tenant.slug)
    with tenant.connection() as con:
        return incident_json(store.load_incident(con, incident_id), store.LeaderNames(con), tenant)


# ---------------------------------------------------------------- Export
def _xlsx(write, name):
    buffer = io.BytesIO()
    write(buffer)
    buffer.seek(0)
    name = f"{name}_{dt.datetime.now():%Y-%m-%d_%H%M}.xlsx"
    return StreamingResponse(buffer, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{name}"'})


def _summary(tenants, year, limit):
    """Kennzahlzeilen je Wehr, Summenzeile und Hinweise für die Excel-Übersicht."""
    parts, _ = _evaluate(tenants, year, limit)
    rows = [{"name": t.name, **metrics.summary(evaluated, limit, t.config)} for t, evaluated, _ in parts]
    everything = [e for _, evaluated, _ in parts for e in evaluated]
    combined = tenant_config.combine("Summe", [t.config for t in tenants])
    total = {**metrics.summary(everything, limit, combined), "name": "Summe (Beteiligungen)"}
    notes = []
    if len(tenants) > 1:
        unique, without = metrics.unique_incidents([i for i, _ in everything])
        notes.append(f"Einsätze ohne Doppelte (gleiche Einsatznummer der Leitstelle = ein Einsatz): {unique}")
        if without:
            notes.append(f"{without} Einsätze ohne Einsatznummer der Leitstelle zählen einzeln.")
    return parts, rows, total, notes


@app.get("/api/export")
def api_export(year: Optional[int] = None, a: tenancy.Access = Depends(access)):
    """Excel im Format der Einsatzübersicht (Spalten je Fahrzeug + Anwesenheit). In der Gesamtansicht
    eine Mappe mit Übersicht und je Wehr Einsatzübersicht und Anwesenheit."""
    tenants = a.selection_with(INCIDENTS)
    year = year or _latest_year(tenants)
    if len(tenants) == 1 and not a.vg:
        tenant = tenants[0]
        with tenant.connection() as con:
            incidents = store.load_incidents(con, year=year)
            members = store.members_of_year(con, year)
        if not incidents:
            raise HTTPException(404, "Keine Einsätze für den Export.")
        return _xlsx(lambda target: excel_export.write_workbook(incidents, members, year, target, tenant.config),
                     f"Einsaetze_{tenant.slug}_{year}")
    limit = tenants[0].config.default_limit
    parts, rows, total, notes = _summary(tenants, year, limit)
    workbook_parts = []
    for t, evaluated, _ in parts:
        with t.connection() as con:
            workbook_parts.append((t.config, [i for i, _ in evaluated], store.members_of_year(con, year)))
    if not any(incidents for _, incidents, _ in workbook_parts):
        raise HTTPException(404, "Keine Einsätze für den Export.")
    return _xlsx(lambda target: excel_export.write_combined_workbook(workbook_parts, rows, total, year, limit, target,
                                                                     notes), f"Einsaetze_{a.vg}_{year}")


@app.get("/api/export/summary")
def api_export_summary(year: Optional[int] = None, a: tenancy.Access = Depends(access)):
    """Kennzahlen je Wehr als Excel – ohne Namen, daher auch für Rollen nur mit Statistik."""
    tenants = a.selection_with(STATS)
    year = year or _latest_year(tenants)
    limit = tenants[0].config.default_limit
    _, rows, total, notes = _summary(tenants, year, limit)
    return _xlsx(lambda target: excel_export.write_summary_workbook(rows, total, year, limit, target, notes),
                 f"Kennzahlen_{a.vg or tenants[0].slug}_{year}")
