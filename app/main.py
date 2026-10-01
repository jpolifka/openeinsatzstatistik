# -*- coding: utf-8 -*-
"""
Einsatzstatistik – HTTP-Schnittstelle, Passwortschutz und Auslieferung der Oberfläche.

Fachlogik liegt in report.py (PDF -> Einsatz), metrics.py (Auswertungen), store.py
(Datenbank) sowie excel_import.py / excel_export.py.
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

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, create_model

from app import auth, db, domain, excel_export, excel_import, metrics, report, store
from app.timeutil import year_of

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("pdf2einsatz")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, "static")
IMPORT_DIR = os.environ.get("IMPORT_DIR", "")
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@contextlib.asynccontextmanager
async def lifespan(_app):
    if os.environ.get("APP_PASSWORD") and not auth.enabled():
        # Nicht still ungeschützt starten, wenn noch die alte Passwort-Konfiguration gesetzt ist
        raise RuntimeError("APP_PASSWORD wird nicht mehr unterstützt – AUTH_EMAILS setzen (siehe README)")
    if not db.PATH:
        raise RuntimeError("DB_PATH fehlt (siehe README)")
    auth.check_config()
    db.setup()
    if IMPORT_DIR and os.path.isdir(IMPORT_DIR):
        with db.connection() as con:
            for result in excel_import.initial_import(con, IMPORT_DIR):
                log.info("Erstimport: %s", result)
    yield


app = FastAPI(title="Einsatzstatistik – FF Rheinbrohl", lifespan=lifespan)
# JSON der Einsatzliste schrumpft komprimiert auf ca. 1/16
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


app.include_router(auth.router)

# Ohne Anmeldung erreichbar: Health-Check, Anmeldeseiten und Logos/CSS/JS (keine Einsatzdaten)
PUBLIC_PATHS = ("/health", "/login", "/logout", "/auth/", "/static/")


@app.middleware("http")
async def require_login(request: Request, call_next):
    """Anmeldung per Magic Link, wenn AUTH_EMAILS gesetzt ist (siehe auth.py)."""
    path = request.url.path
    if auth.enabled() and not path.startswith(PUBLIC_PATHS) and not auth.current_user(request):
        # Direkt im Browser geöffnete API-Adressen (z. B. Export) auch zur Anmeldeseite
        if path.startswith("/api/") and "text/html" not in request.headers.get("accept", ""):
            return JSONResponse({"detail": "Anmeldung erforderlich"}, status_code=401)
        return RedirectResponse("/login", 303)
    return await call_next(request)


# ---------------------------------------------------------------- PDF-Vorschau im Speicher
class PreviewSessions:
    """Gelesene Berichte bis zur Übernahme. Liegt im Prozess – daher nur ein uvicorn-Worker."""
    TTL = 60 * 60

    def __init__(self):
        self._sessions = {}
        self._lock = threading.Lock()

    def add(self, reports):
        token = uuid.uuid4().hex
        with self._lock:
            self._expire()
            self._sessions[token] = {"time": time.time(), "reports": {r["filename"]: r for r in reports}}
        return token

    def get(self, token, filename):
        with self._lock:
            session = self._sessions.get(token)
        return session and session["reports"].get(filename)

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


def incident_json(incident, limit=domain.DEFAULT_LIMIT):
    """Einsatz mit Kennzahlen für die Oberfläche."""
    m = metrics.incident_metrics(incident, limit)
    vehicles = []
    for call_sign in domain.VEHICLES:
        v, vm = incident["vehicles"].get(call_sign) or {}, m["vehicles"].get(call_sign) or {}
        vehicles.append({"call_sign": call_sign, "substitute": domain.substitute_label(v.get("name"), call_sign),
                         "crew": v.get("crew"), "departed": v.get("departed"), "arrived": v.get("arrived"),
                         "turnout_min": _rounded(vm.get("turnout_min")),
                         "arrival_min": _rounded(vm.get("arrival_min"))})
    return {
        **{name: incident.get(name) for name in ("id", "year", *store.FIELDS, "source", "filename", "warnings")},
        "weekend_or_holiday": bool(incident.get("weekend_or_holiday")),
        **{name: _rounded(m[name]) for name in ("daytime", "duration_min", "turnout_min", "arrival_min", "on_time",
                                                 "crew_on_arrival", "crew_within_limit", "crew_within_second",
                                                 "crew_total")},
        "vehicles": vehicles,
        "people": [{"id": p["id"], "name": p["name"], "role": p.get("role"), "vehicle": p.get("vehicle"),
                    "new": p.get("new", False)} for p in incident["people"]],
    }


# ---------------------------------------------------------------- Seiten
@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/config")
def api_config(request: Request):
    return {**domain.client_config(), "user": auth.current_user(request)}


# ---------------------------------------------------------------- Auswertung
@app.get("/api/years")
def api_years():
    with db.connection() as con:
        return {"years": store.years(con), "today": dt.date.today().isoformat()}


@app.get("/api/evaluation")
def api_evaluation(year: Optional[int] = None, limit: int = domain.DEFAULT_LIMIT):
    if limit not in domain.RESPONSE_LIMITS:
        allowed = " oder ".join(str(x) for x in domain.RESPONSE_LIMITS)
        raise HTTPException(400, f"Die Zeitgrenze muss {allowed} Minuten sein.")
    with db.connection() as con:
        year = _resolve_year(con, year)
        current = metrics.evaluate(store.load_incidents(con, year=year), limit)
        previous = store.load_incidents(con, year=year - 1) or None
    return {"year": year,
            "statistics": metrics.statistics(current, year, previous),
            "response_plan": metrics.response_plan(current, limit),
            "response_plan_previous": metrics.response_plan(metrics.evaluate(previous, limit), limit)
            if previous else None,
            "attendance": metrics.attendance_overview(current)}


# ---------------------------------------------------------------- Einsätze
IncidentFields = create_model(
    "IncidentFields",
    **{name: (Optional[int] if name in store.INT_FIELDS else Optional[str], None) for name in store.FIELDS})


@app.get("/api/incidents")
def api_incidents(year: Optional[int] = None):
    with db.connection() as con:
        year = _resolve_year(con, year)
        return {"year": year, "incidents": [incident_json(i) for i in store.load_incidents(con, year=year)]}


@app.put("/api/incidents/{incident_id}")
def api_update_incident(incident_id: int, fields: IncidentFields):
    with db.connection() as con:
        try:
            store.update_incident(con, incident_id, fields.model_dump(exclude_unset=True))
        except KeyError:
            raise HTTPException(404, "Einsatz nicht gefunden.")
        except store.DuplicateIncident as e:
            raise HTTPException(409, str(e))
        return incident_json(store.load_incident(con, incident_id))


@app.delete("/api/incidents/{incident_id}")
def api_delete_incident(incident_id: int):
    with db.connection() as con:
        store.delete_incident(con, incident_id)
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


def _read_uploads(uploads):
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
                reports.append(report.read_pdf(path, filename))
            except Exception as e:  # defekte oder fremde PDF: melden, Rest weiter lesen
                log.exception("PDF %s", filename)
                errors.append({"file": filename, "message": str(e) or type(e).__name__})
    return reports, errors


def _preview_json(con, r):
    incident, existing = report.preview(con, r)
    result = incident_json(incident)
    result["reported_as"] = r["reported_as"]
    result["incident_commander"] = r["incident_commander"]
    result["existing"] = {"id": existing["id"], "source": existing["source"],
                          "differences": report.differences(existing, incident)} if existing else None
    return result


@app.post("/api/reports")
def api_read_reports(pdfs: List[UploadFile] = File(...)):
    pdfs = [p for p in pdfs if _is_upload(p.filename)]
    if not pdfs:
        raise HTTPException(400, "Bitte eine PDF- oder ZIP-Datei (Einsatzberichte aus dem BKS-Portal) auswählen.")
    reports, errors = _read_uploads(pdfs)
    with db.connection() as con:
        previews_json = [_preview_json(con, r) for r in reports]
    return {"token": previews.add(reports), "reports": previews_json, "errors": errors}


class Acceptance(BaseModel):
    token: str
    filename: str
    fields: IncidentFields
    replace: bool = False


@app.post("/api/reports/accept")
def api_accept_report(a: Acceptance):
    r = previews.get(a.token, a.filename)
    if not r:
        raise HTTPException(410, "Die Vorschau ist abgelaufen – bitte die PDF erneut einlesen.")
    fields = {**report.to_fields(r), **a.fields.model_dump(exclude_unset=True)}
    with db.connection() as con:
        replace_id = store.find_incident(con, year_of(fields.get("started_at")),
                                         store.to_int(fields.get("number"))) if a.replace else None
        try:
            incident_id = report.save(con, r, fields, replace_id)
        except store.DuplicateIncident as e:
            raise HTTPException(409, str(e))
        return incident_json(store.load_incident(con, incident_id))


# ---------------------------------------------------------------- Export
@app.get("/api/export")
def api_export(year: Optional[int] = None, ids: Optional[str] = None):
    """Excel im Format der Einsatzübersicht (Spalten A:AV + Anwesenheit)."""
    with db.connection() as con:
        year = _resolve_year(con, year)
        incidents = store.load_incidents(con, year=year)
        if ids:
            selected = {int(i) for i in ids.split(",") if i.strip().isdigit()}
            incidents = [i for i in incidents if i["id"] in selected]
        members = store.members_of_year(con, year)
    if not incidents:
        raise HTTPException(404, "Keine Einsätze für den Export.")
    buffer = io.BytesIO()
    excel_export.write_workbook(incidents, members, year, buffer)
    buffer.seek(0)
    stamp = f"{dt.datetime.now():%Y-%m-%d_%H%M}"
    name = f"Import_Einsatzberichte_{stamp}.xlsx" if ids else f"Einsaetze_{year}_{stamp}.xlsx"
    return StreamingResponse(buffer, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{name}"'})
