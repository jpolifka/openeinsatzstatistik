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

from app import admin, auth, db, domain, dpa, feedback, fees, mail, excel_export, legacy, metrics, pdf_report, rbac, records, report, store, tenancy, tenant_config, theme
from app.rbac import DELETE, EXPORT, IMPORT, INCIDENTS, PEOPLE, PEOPLE_EDIT, PLAN_VIEW, STATS, VG_RECORDS, WRITE
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
app.include_router(feedback.router)

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
        if not session or session["owner"] != owner or filename not in session["reports"] \
                or session["time"] < time.time() - self.TTL:
            return None, None
        return session["reports"][filename]

    @contextlib.contextmanager
    def claim(self, token, filename, owner):
        """Bericht zur Übernahme entnehmen: ein zweiter Aufruf (Doppelklick) findet ihn nicht mehr.
        Scheitert die Übernahme, liegt er wieder bereit."""
        entry = None
        with self._lock:
            session = self._sessions.get(token)
            if session and session["owner"] == owner and session["time"] >= time.time() - self.TTL:
                entry = session["reports"].pop(filename, None)
        try:
            yield entry or (None, None)
        except BaseException:
            if entry:
                with self._lock:
                    session["reports"][filename] = entry
            raise

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


def _names_for(tenant, incidents):
    """Einsätze ohne EHF (Name), wenn der Benutzer in der Wehr keine Namen sehen darf (Recht PEOPLE)."""
    return incidents if tenant.can(PEOPLE) else [{**i, "unit_leader": None} for i in incidents]


def incident_json(incident, leaders, tenant, limit=None, cfg=None):
    """Einsatz mit Kennzahlen für die Oberfläche. leaders: store.LeaderNames für die EHF-Auswahl.
    cfg: abweichende Konfiguration (Vorschau mit neu entdeckten Fahrzeugen), sonst die der Wehr.
    Die Anwesenheit (Namen) nur mit Recht rbac.PEOPLE; sonst nur ihre Anzahl."""
    cfg = cfg or tenant.config
    m = metrics.incident_metrics(incident, cfg, limit)
    vehicles = []
    for call_sign in cfg.vehicles_for(incident):
        v, vm = incident["vehicles"].get(call_sign) or {}, m["vehicles"].get(call_sign) or {}
        vehicles.append({"call_sign": call_sign, "substitute": cfg.substitute_label(v.get("name"), call_sign),
                         "crew": v.get("crew"), "departed": v.get("departed"), "arrived": v.get("arrived"),
                         "alerted": v.get("alerted"), "finished": v.get("finished"),
                         "turnout_min": _rounded(vm.get("turnout_min")),
                         "arrival_min": _rounded(vm.get("arrival_min"))})
    return {
        "id": incident_key(tenant, incident.get("id")),
        "tenant": tenant.slug,
        **{name: incident.get(name) for name in ("year", *store.FIELDS, *store.ID_FIELDS, "source", "filename",
                                                 "warnings")},
        **({} if tenant.can(PEOPLE) else {"unit_leader": None}),     # EHF ist ein Name
        "bks_url": domain.BKS_REPORT_URL.format(incident["bks_report_id"]) if incident.get("bks_report_id") else None,
        "weekend_or_holiday": bool(incident.get("weekend_or_holiday")),
        **{name: _rounded(m[name]) for name in ("daytime", "duration_min", "turnout_min", "arrival_min", "on_time",
                                                 "crew_on_arrival", "crew_within_limit", "crew_within_second",
                                                 "crew_total")},
        "vehicles": vehicles,
        "people": [{"id": p["id"], "name": p["name"], "role": p.get("role"), "vehicle": p.get("vehicle"),
                    "new": p.get("new", False), "leader_name": leaders.spelling(p),
                    "leader": leaders.is_leader(incident.get("unit_leader"), p)} for p in incident["people"]]
        if tenant.can(PEOPLE) else [],
        "people_count": len(incident["people"]),
        "people_visible": tenant.can(PEOPLE),
        "people_editable": tenant.can(PEOPLE_EDIT),
        "can_edit": tenant.can(WRITE),
        "can_delete": tenant.can(DELETE),
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


PLAN_KEYS = ("plan_count", "on_time", "rate", "arrival_min")


def _plan_visible(tenant):
    """Bedarfsplan einer Wehr: freigegeben oder mit Recht PLAN_VIEW."""
    return tenant.config.response_plan_public or tenant.can(PLAN_VIEW)


def _without_plan(row, visible=False):
    """Kennzahlzeile ohne Bedarfsplan-Werte, solange er nicht sichtbar ist."""
    return row if visible else {**row, **dict.fromkeys(PLAN_KEYS)}


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
    # Bedarfsplan nur aus Wehren, für die er sichtbar ist (Freigabe oder Recht PLAN_VIEW)
    plan_parts = [(t, evaluated, prev) for t, evaluated, prev in parts if _plan_visible(t)]
    plan_cfg = _selection_config([t for t, _, _ in plan_parts], a) if plan_parts else None
    plan_current = [e for _, evaluated, _ in plan_parts for e in evaluated]
    plan_previous = [e for t, _, prev in plan_parts for e in metrics.evaluate(prev, t.config, limit)]
    result = {"year": year,
              "history": metrics.monthly_history(months),
              "statistics": metrics.statistics(current, year, cfg, previous or None),
              "response_plan": metrics.response_plan(plan_current, limit, plan_cfg) if plan_parts else None,
              "response_plan_previous": metrics.response_plan(plan_previous, limit, plan_cfg)
              if plan_parts and any(prev for _, _, prev in plan_parts) else None,
              "response_plan_public": all(t.config.response_plan_public for t in selection),
              "response_plan_hidden": [t.name for t in selection if not _plan_visible(t)],
              "attendance": metrics.attendance_overview(current) if single and selection[0].can(PEOPLE) else None,
              "tenants": None}
    if not single:
        unique, without = metrics.unique_incidents([i for i, _ in current])
        result["tenants"] = {
            "participations": len(current), "unique": unique, "without_dispatch_number": without,
            "rows": [_without_plan({"slug": t.slug, "name": t.name, **metrics.summary(evaluated, limit, t.config)},
                                   _plan_visible(t)) for t, evaluated, _ in parts]}
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


class VehicleEdit(BaseModel):
    call_sign: str
    crew: Optional[int] = None
    departed: Optional[str] = None
    arrived: Optional[str] = None


class PersonEdit(BaseModel):
    id: Optional[int] = None          # vorhandener Kamerad
    name: Optional[str] = None        # sonst „Nachname, Vorname“ (wird bei Bedarf angelegt)
    role: Optional[str] = None
    vehicle: Optional[str] = None


# Einsatz bearbeiten: Felder, dazu optional Fahrzeuge und Anwesenheit (fehlen sie, bleiben sie unverändert)
IncidentUpdate = create_model("IncidentUpdate", __base__=IncidentFields,
                              vehicles=(Optional[List[VehicleEdit]], None), people=(Optional[List[PersonEdit]], None))


@app.put("/api/incidents/{key}")
def api_update_incident(key: str, update: IncidentUpdate, a: tenancy.Access = Depends(access)):
    slug, incident_id = parse_incident_key(key)
    tenant = a.tenant(slug, WRITE)
    changes = update.model_dump(exclude_unset=True)
    vehicles, people = changes.pop("vehicles", None), changes.pop("people", None)
    by_date = tenant.config.numbering == "by_date"
    if by_date:
        changes.pop("number", None)          # ergibt sich aus dem Beginn
    if not tenant.can(PEOPLE):
        changes.pop("unit_leader", None)     # sieht den EHF nicht (Name), ändert ihn also auch nicht
    if people is not None and not tenant.can(PEOPLE_EDIT):
        raise tenancy.Forbidden("Keine Berechtigung, die Anwesenheit zu bearbeiten.")
    if vehicles is not None and any(v["call_sign"] not in tenant.config.vehicles for v in vehicles):
        raise HTTPException(422, "Unbekanntes Fahrzeug – Fahrzeuge der Wehr in der Verwaltung pflegen.")
    with tenant.connection() as con:
        try:
            old_year = (store.load_incident(con, incident_id) or {}).get("year")
            new_year = year_of(changes["started_at"]) if changes.get("started_at") else old_year
            if by_date and new_year and new_year != old_year:
                changes["number"] = store.next_number(con, new_year)   # vorläufig ans Ende des neuen Jahres
            store.update_incident(con, incident_id, changes, modified_by=a.email)
            if by_date:
                for y in {old_year, store.load_incident(con, incident_id)["year"]} - {None}:
                    store.renumber(con, y)
            if vehicles is not None:
                store.replace_vehicles(con, incident_id, vehicles)
            if people is not None:
                store.replace_attendance(con, incident_id, people)
        except KeyError:
            raise HTTPException(404, "Einsatz nicht gefunden.")
        except store.DuplicateIncident as e:
            raise HTTPException(409, str(e))
        except ValueError as e:
            raise HTTPException(422, str(e))
        return incident_json(store.load_incident(con, incident_id), store.LeaderNames(con), tenant)


@app.get("/api/members")
def api_members(tenant: str, a: tenancy.Access = Depends(access)):
    """Kameraden einer Wehr für Vorschläge beim Bearbeiten der Anwesenheit."""
    with a.tenant(tenant, PEOPLE).connection() as con:
        return {"members": store.all_members(con)}


@app.delete("/api/incidents/{key}")
def api_delete_incident(key: str, a: tenancy.Access = Depends(access)):
    slug, incident_id = parse_incident_key(key)
    tenant = a.tenant(slug, DELETE)
    with tenant.connection() as con:
        year = (store.load_incident(con, incident_id) or {}).get("year")
        store.delete_incident(con, incident_id)
        if tenant.config.numbering == "by_date":
            store.renumber(con, year)
    log.info("Einsatz %s gelöscht von %s", key, a.email or "lokal")
    return {"ok": True}


# ---------------------------------------------------------------- Berichte einlesen (PDF, Excel-Export)
ZIP_MAX_PDFS = 500
ZIP_MAX_BYTES = 50 * 1024 * 1024     # je entpacktem Bericht
UPLOAD_MAX_BYTES = 200 * 1024 * 1024  # je Upload: hochgeladen bzw. entpackt zusammen (Speicher, Platte)
REPORT_TYPES = (".pdf", ".xlsx")


def _is_upload(filename):
    return (filename or "").lower().endswith((*REPORT_TYPES, ".zip"))


def _unique_filename(filename, taken):
    """Gleichnamige PDFs (z. B. aus Unterordnern einer ZIP) durchnummerieren."""
    stem, ext = os.path.splitext(filename)
    candidate, n = filename, 2
    while candidate in taken:
        candidate, n = f"{stem} ({n}){ext}", n + 1
    taken.add(candidate)
    return candidate


class Budget:
    """Bytes, die ein Upload insgesamt noch belegen darf (hochgeladen und entpackt)."""

    def __init__(self, limit=None):
        self.left = UPLOAD_MAX_BYTES if limit is None else limit

    def take(self, size):
        if size > self.left:
            return False
        self.left -= size
        return True


TOO_BIG = f"Zu groß – je Upload höchstens {UPLOAD_MAX_BYTES // (1024 * 1024)} MB, bitte in Teilen hochladen."


def _unpack_zip(data, zip_name, errors, budget):
    """Berichte (PDF, xlsx) aus einer ZIP-Datei holen -> erzeugt (dateiname, inhalt) einzeln, damit nicht alle
    gleichzeitig im Speicher liegen. Andere Dateien werden übergangen."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        errors.append({"file": zip_name, "message": "Keine gültige ZIP-Datei."})
        return
    entries = [i for i in archive.infolist() if not i.is_dir() and i.filename.lower().endswith(REPORT_TYPES)
               and not i.filename.startswith("__MACOSX/") and not os.path.basename(i.filename).startswith("._")]
    if not entries:
        errors.append({"file": zip_name, "message": "Die ZIP-Datei enthält keinen Bericht (PDF oder Excel-Export)."})
    if len(entries) > ZIP_MAX_PDFS:
        errors.append({"file": zip_name, "message": f"Mehr als {ZIP_MAX_PDFS} Berichte, nur die ersten werden gelesen."})
        entries = entries[:ZIP_MAX_PDFS]
    for info in entries:
        name = _safe_filename(info.filename)
        if info.file_size > ZIP_MAX_BYTES:
            errors.append({"file": name, "message": "Bericht in der ZIP-Datei ist zu groß."})
            continue
        try:
            with archive.open(info) as fh:      # Größe aus dem Verzeichnis nicht trauen: begrenzt lesen
                content = fh.read(ZIP_MAX_BYTES + 1)
        except Exception as e:  # verschlüsselt oder beschädigt
            errors.append({"file": name, "message": f"Nicht entpackbar ({e or type(e).__name__})."})
            continue
        if len(content) > ZIP_MAX_BYTES:
            errors.append({"file": name, "message": "Bericht in der ZIP-Datei ist zu groß."})
            continue
        if not budget.take(len(content)):
            errors.append({"file": zip_name, "message": TOO_BIG})
            return
        yield name, content


class Skipped(Exception):
    """Bericht wird nicht eingelesen (Meldung als Info, nicht als Fehler)."""


class Forward(Exception):
    """Bericht gehört zu einer anderen Wehr der VG: wird ihr zur Übernahme weitergegeben."""

    def __init__(self, tenant, head):
        super().__init__(tenant.name)
        self.tenant, self.head = tenant, head


def _owner(head, tenants):
    """Wehr der VG, deren BKS-Kennung zur berichtenden Einheit passt (auch ohne Rechte des Benutzers)."""
    if not head["unit"] or not tenants:
        return None
    return next((t for t in tenancy.vg_tenants(tenants[0].vg_id) if t.config.unit_marker == head["unit"]), None)


def _read_report(path, filename, tenants):
    """Bericht (PDF oder Excel-Export) lesen -> (bericht, wehr); wehr=None beim Stammdatensatz.

    Bei mehreren Wehren wird die passende über die Einheit bzw. die eigenen Fahrzeuge im Bericht
    gesucht. Berichte anderer Einheiten (z. B. FEZ) werden übersprungen (Skipped)."""
    parse = report.parser(path, filename)
    head = parse("")
    if head["report_kind"] == "master":
        return head, None
    if len(tenants) == 1:
        cfg = tenants[0].config
        if head["unit"] and cfg.unit_marker and head["unit"] != cfg.unit_marker:
            owner = _owner(head, tenants)
            if owner:
                raise Forward(owner, head)
            raise Skipped(f"Bericht der Einheit {report.unit_label(head)} – gehört nicht zu {tenants[0].name}, "
                          "übersprungen.")
        return report.read(parse, cfg), tenants[0]
    by_slug = {t.slug: t for t in tenants}
    slug, how = report.match_tenant(parse, [(t.slug, t.config) for t in tenants])
    if not slug:
        owner = _owner(head, tenants)
        if owner:
            raise Forward(owner, head)
        if head["unit"]:
            raise Skipped(f"Bericht der Einheit {report.unit_label(head)} – gehört zu keiner der ausgewählten "
                          "Wehren, übersprungen.")
        raise ValueError("Der Bericht passt zu keiner der ausgewählten Wehren (Einheit und Fahrzeuge unbekannt).")
    r = report.read(parse, by_slug[slug].config)
    if how == "vehicles":
        r["warnings"].append(f"{by_slug[slug].name} über die Fahrzeuge im Bericht zugeordnet – bitte prüfen")
    return r, by_slug[slug]


def _read_uploads(uploads, tenants, email=None):
    """Hochgeladene Berichte (PDF, xlsx) und ZIP-Dateien lesen -> ([(bericht, wehr)], fehler, hinweise)."""
    errors, budget = [], Budget()

    def files():
        for upload in uploads:
            filename, data = _safe_filename(upload.filename), upload.file.read(budget.left + 1)
            if not budget.take(len(data)):
                errors.append({"file": filename, "message": TOO_BIG})
                return
            if filename.lower().endswith(".zip"):
                yield from _unpack_zip(data, filename, errors, budget)
            else:
                yield filename, data

    reports, more_errors, notes = _read_files(files(), tenants, email)
    return reports, errors + more_errors, notes


def _read_files(files, tenants, email=None):
    """Berichte [(dateiname, inhalt)] lesen -> ([(bericht, wehr)], fehler, hinweise). Stammdatensätze werden
    gleich bei der VG gespeichert, Berichte anderer Wehren der VG an diese weitergegeben."""
    reports, errors, notes = [], [], []
    taken = set()
    with tempfile.TemporaryDirectory() as tmp:
        for filename, data in files:
            filename = _unique_filename(filename, taken)
            path = os.path.join(tmp, filename)
            with open(path, "wb") as fh:
                fh.write(data)
            try:
                r, tenant = _read_report(path, filename, tenants)
            except Skipped as e:
                notes.append({"file": filename, "message": str(e)})
                continue
            except Forward as f:
                notes.append({"file": filename, "message": _forward(f.tenant, f.head, filename, data, email)})
                continue
            except Exception as e:  # defekte oder fremde Datei: melden, Rest weiter lesen
                log.exception("Bericht %s", filename)
                errors.append({"file": filename, "message": str(e) or type(e).__name__})
                continue
            if tenant:
                reports.append((r, tenant))
                continue
            _save_master(r, tenants[0].vg_id, email)
            notes.append({"file": filename, "message": f"Stammdatensatz {r['bks_record_id']} gespeichert."})
    return reports, errors, notes


def _save_master(r, vg_id, email):
    """Stammdatensatz speichern; Wehren mit ausgerückten Fahrzeugen, aber ohne Bericht bekommen einen Hinweis."""
    with tenancy.central() as con:
        records.save_master(con, vg_id, r, email)
        records.notify_others(con, r, r["vehicles"], "Stammdatensatz", tenancy.vg_tenants(vg_id),
                              deviations=False, email=email)


def _forward(tenant, head, filename, data, email):
    """Bericht einer anderen Wehr der VG dort zur Übernahme ablegen -> Meldung für den Hochladenden."""
    with tenant.connection() as con:
        if head["bks_report_id"] and store.find_existing(con, head["bks_report_id"], None, None):
            return f"Bericht der Einheit {report.unit_label(head)} – bei {tenant.name} bereits erfasst, übersprungen."
        store.add_pending(con, head, filename, data, email)
    when = records.format_date(head.get("first_alarm"))
    with tenancy.central() as con:
        records.notify(con, tenant.id, "pending",
                       f"Bericht {head.get('number_text') or filename} vom {when} ({head.get('reported_as') or '–'}) "
                       f"von {email or 'lokal'} eingelesen – liegt zur Übernahme bereit.",
                       head.get("bks_record_id"), email=email)
        records.close_notices(con, tenant.id, head.get("bks_record_id"), ("missing",))
    return f"Bericht der Einheit {report.unit_label(head)} an {tenant.name} zur Übernahme weitergegeben."


def _after_import(a, tenant, r, incident_id, updated):
    """Nach dem Speichern: Bericht im Verzeichnis vermerken, Hinweise an die eigene Wehr (eingelesen
    durch jemanden ohne eigene Rolle dort) und an andere Wehren (Abweichungen, fehlende Berichte)."""
    with tenancy.central() as con:
        records.register_report(con, tenant.id, r, a.email)
        records.close_notices(con, tenant.id, r.get("bks_record_id"), ("missing", "pending"))
        if a.email and not a.is_member(tenant):
            started = records.format_date(r.get("started_at"))
            number = f"{r['number']}/{r['started_at']:%y}" if r.get("number") and r.get("started_at") else "ohne Nr."
            records.notify(con, tenant.id, "import",
                           f"Einsatz {number} vom {started} ({r.get('reported_as') or '–'}) von {a.email} "
                           f"{'aktualisiert' if updated else 'eingelesen'}.",
                           r.get("bks_record_id"), incident_key(tenant, incident_id),
                           r["started_at"].year if r.get("started_at") else None, a.email)
        records.notify_others(con, r, r["vehicles"], f"Bericht von {tenant.name}", tenancy.vg_tenants(tenant.vg_id),
                              exclude=tenant.id, email=a.email)


def _shared_with(r, tenant, a):
    """Andere sichtbare Wehren, die denselben Einsatz schon erfasst haben: gleicher Stammdatensatz im
    BKS-Portal oder gleiche Einsatznummer der Leitstelle."""
    keys = [(name, r[name]) for name in ("bks_record_id", "dispatch_number") if r.get(name)]
    if not keys:
        return []
    where = " OR ".join(f"{name} = ?" for name, _ in keys)
    names = []
    for other in a.tenants.values():
        if other.slug != tenant.slug and other.can(STATS):
            with other.connection() as con:
                if con.execute(f"SELECT 1 FROM incident WHERE {where}", [v for _, v in keys]).fetchone():
                    names.append(other.name)
    return names


def _preview_json(r, tenant, a):
    cfg = tenant.config.with_new_vehicles(report.new_fleet_vehicles(r), r.get("day"))
    with tenant.connection() as con:
        incident, existing = report.preview(con, r, numbered=tenant.config.numbering != "by_date")
        result = incident_json(incident, store.LeaderNames(con), tenant, cfg=cfg)
    result["tenant_name"] = tenant.name
    result["new_vehicles"] = r.get("new_vehicles", [])
    result["reported_as"] = r["reported_as"]
    names = tenant.can(PEOPLE)                  # Einsatzleiter und EHF sind Namen
    result["incident_commander"] = r["incident_commander"] if names else None
    differences = report.differences(existing, incident, tenant.config) if existing else []
    result["existing"] = {"id": incident_key(tenant, existing["id"]), "source": existing["source"],
                          "differences": [d for d in differences if names or d["field"] != "EHF"]} \
        if existing else None
    result["shared_with"] = _shared_with(r, tenant, a)
    return result


@app.post("/api/reports")
def api_read_reports(pdfs: List[UploadFile] = File(...), a: tenancy.Access = Depends(access)):
    """Berichte lesen – für die ausgewählte Wehr oder, in der Gesamtansicht, verteilt auf die passende
    Wehr der VG (nur Wehren mit Schreibrecht)."""
    tenants = a.selection_with(IMPORT) if a.vg else [a.current(IMPORT)]
    pdfs = [p for p in pdfs if _is_upload(p.filename)]
    if not pdfs:
        raise HTTPException(400, "Bitte eine PDF-, Excel- oder ZIP-Datei (Einsatzberichte aus dem BKS-Portal) auswählen.")
    reports, errors, notes = _read_uploads(pdfs, tenants, a.email)
    previews_json = [_preview_json(r, tenant, a) for r, tenant in reports]
    token = previews.add([(r, tenant.slug) for r, tenant in reports], a.email)
    return {"token": token, "reports": previews_json, "errors": errors, "notes": notes}


class Acceptance(BaseModel):
    token: str
    filename: str
    fields: IncidentFields
    replace: bool = False


@app.post("/api/reports/accept")
def api_accept_report(acceptance: Acceptance, a: tenancy.Access = Depends(access)):
    with previews.claim(acceptance.token, acceptance.filename, a.email) as (r, slug):
        if not r:
            raise HTTPException(410, "Die Vorschau ist abgelaufen oder der Bericht wurde schon übernommen – "
                                     "bitte den Bericht erneut einlesen.")
        return _accept_report(acceptance, a, r, slug)


def _accept_report(acceptance, a, r, slug):
    tenant = a.tenant(slug, IMPORT)
    if acceptance.replace:
        a.tenant(slug, WRITE)              # erfassten Einsatz überschreiben = bearbeiten
    corrected = acceptance.fields.model_dump(exclude_unset=True)
    if not tenant.can(PEOPLE):
        corrected.pop("unit_leader", None)   # sieht den EHF nicht, also bleibt der aus dem Bericht
    fields = {**report.to_fields(r), **corrected}
    by_date = tenant.config.numbering == "by_date"
    year = year_of(fields.get("started_at"))
    with tenant.connection() as con:
        update_id = store.find_existing(con, fields.get("bks_report_id"), year,
                                        None if by_date else store.to_int(fields.get("number"))) \
            if acceptance.replace else None
        old_year = store.load_incident(con, update_id)["year"] if update_id else None
        if by_date:
            # Vorläufig ans Ende, die richtige Stelle ergibt sich nach dem Speichern
            fields["number"] = store.next_number(con, year) if year else None
        elif store.to_int(fields.get("number")) is None and year:
            fields["number"] = store.next_number(con, year)
            r["warnings"].append(f"Einsatzbericht-Nr. fehlt – nächste freie Nr. {fields['number']} vergeben")
        try:
            incident_id = report.save(con, r, fields, update_id, modified_by=a.email)
        except store.DuplicateIncident as e:
            raise HTTPException(409, str(e))
        if by_date:
            for y in {year, old_year} - {None}:
                store.renumber(con, y)
        store.delete_pending(con, r.get("pending_id"), r.get("bks_report_id"))
    _after_import(a, tenant, r, incident_id, bool(update_id))
    if r.get("new_vehicles"):
        tenancy.forget_config(tenant.slug)
        log.info("Fahrzeuge %s in die Liste von %s aufgenommen", ", ".join(r["new_vehicles"]), tenant.slug)
    with tenant.connection() as con:
        return incident_json(store.load_incident(con, incident_id), store.LeaderNames(con), tenant)


# ---------------------------------------------------------------- Weitergegebene Berichte
@app.get("/api/pending")
def api_pending(a: tenancy.Access = Depends(access)):
    """Berichte, die jemand aus einer anderen Wehr für die ausgewählten Wehren eingelesen hat."""
    result = []
    for tenant in a.selection_with(IMPORT):
        with tenant.connection() as con:
            result += [{**p, "id": incident_key(tenant, p["id"]), "tenant": tenant.slug, "tenant_name": tenant.name}
                       for p in store.pending_reports(con)]
    return {"reports": result}


class PendingSelection(BaseModel):
    ids: List[str]


@app.post("/api/pending/read")
def api_read_pending(selection: PendingSelection, a: tenancy.Access = Depends(access)):
    """Abgelegte Berichte wie hochgeladene Dateien lesen (Vorschau, Übernahme wie bei /api/reports)."""
    reports, errors, notes = [], [], []
    for key in selection.ids:
        slug, pending_id = parse_incident_key(key)
        tenant = a.tenant(slug, IMPORT)
        with tenant.connection() as con:
            filename, data = store.pending_pdf(con, pending_id)
        if not filename:
            errors.append({"file": key, "message": "Der Bericht liegt nicht mehr bereit."})
            continue
        read, more_errors, more_notes = _read_files([(filename, data)], [tenant], a.email)
        for r, _ in read:
            r["pending_id"] = pending_id
        reports += read
        errors += more_errors
        notes += more_notes
    previews_json = [_preview_json(r, tenant, a) for r, tenant in reports]
    token = previews.add([(r, tenant.slug) for r, tenant in reports], a.email)
    return {"token": token, "reports": previews_json, "errors": errors, "notes": notes}


@app.delete("/api/pending/{key}")
def api_discard_pending(key: str, a: tenancy.Access = Depends(access)):
    slug, pending_id = parse_incident_key(key)
    with a.tenant(slug, IMPORT).connection() as con:
        store.delete_pending(con, pending_id)
    return {"ok": True}


# ---------------------------------------------------------------- Hinweise
@app.get("/api/notices")
def api_notices(a: tenancy.Access = Depends(access)):
    """Offene Hinweise der Wehren, deren Einsätze der Benutzer sehen darf."""
    ids = [t.id for t in a.tenants.values() if t.can(INCIDENTS)]
    with tenancy.central() as con:
        notices = records.open_notices(con, ids)
    writable = {t.slug for t in a.tenants.values() if t.can(WRITE)}
    return {"notices": [{**n, "can_close": n["tenant"] in writable} for n in notices]}


@app.post("/api/notices/{notice_id}/done")
def api_close_notice(notice_id: int, a: tenancy.Access = Depends(access)):
    with tenancy.central() as con:
        row = con.execute("SELECT t.slug FROM notice n JOIN tenant t ON t.id = n.tenant_id WHERE n.id = ?",
                          (notice_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Hinweis nicht gefunden.")
        a.tenant(row["slug"], WRITE)
        records.close_notice(con, notice_id, a.email)
    return {"ok": True}


# ---------------------------------------------------------------- Prüfprotokoll (Recht VG_RECORDS)
def _managed_vg(a):
    """VG der Gesamtansicht mit Recht auf das Prüfprotokoll -> (vg_id, alle Wehren der VG)."""
    tenants = a.selection if a.vg else []
    if not tenants or not a.vg_can(tenants[0].vg_id, VG_RECORDS):
        raise tenancy.Forbidden("Das Prüfprotokoll gibt es in der Gesamtansicht der VG – mit Recht darauf.")
    vg_id = tenants[0].vg_id
    return vg_id, tenancy.vg_tenants(vg_id)


@app.get("/api/records")
def api_records(year: Optional[int] = None, a: tenancy.Access = Depends(access)):
    vg_id, tenants = _managed_vg(a)
    year = year or _latest_year(tenants) or dt.date.today().year
    with tenancy.central() as con:
        return {"year": year, "records": records.protocol(con, vg_id, year, tenants)}


class Review(BaseModel):
    done: bool = True


@app.post("/api/records/{bks_record_id}/review")
def api_review_record(bks_record_id: str, review: Review, a: tenancy.Access = Depends(access)):
    vg_id, tenants = _managed_vg(a)
    with tenancy.central() as con:
        records.review(con, vg_id, bks_record_id, tenants, a.email, review.done)
        entry = records.check(con, vg_id, bks_record_id, tenants)
    return {"ok": True, "findings": len(entry["findings"])}


# ---------------------------------------------------------------- Kostenersatz (Recht VG_RECORDS)
class Expense(BaseModel):
    label: str = ""
    amount: float = 0


class FeeRequest(BaseModel):
    schedule_id: Optional[int] = None
    bma_cap: Optional[bool] = None     # None: bei Stichwort Brandmeldeanlage höchstens die Pauschale
    expenses: List[Expense] = []
    vat_percent: float = 0


@app.post("/api/records/{bks_record_id}/fees")
def api_fees(bks_record_id: str, request: FeeRequest, a: tenancy.Access = Depends(access)):
    """Kostenaufstellung nach der Gebührenordnung der VG – nur berechnet, nicht gespeichert."""
    vg_id, tenants = _managed_vg(a)
    if not 0 <= request.vat_percent <= 100 or any(e.amount < 0 for e in request.expenses):
        raise HTTPException(422, "Auslagen und Umsatzsteuer dürfen nicht negativ sein.")
    with tenancy.central() as con:
        try:
            result = fees.calculate(con, vg_id, bks_record_id, tenants, request.schedule_id, request.bma_cap,
                                    [e.model_dump() for e in request.expenses], request.vat_percent)
        except ValueError as e:
            raise HTTPException(422, str(e))
        result["schedules"] = [{"id": s["id"], "name": s["name"], "valid_from": s["valid_from"]}
                               for s in fees.schedules(con, vg_id)]
    return result


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
    rows = [_without_plan({"name": t.name, **metrics.summary(evaluated, limit, t.config)}, _plan_visible(t))
            for t, evaluated, _ in parts]
    everything = [e for _, evaluated, _ in parts for e in evaluated]
    combined = tenant_config.combine("Summe", [t.config for t in tenants])
    total = {**metrics.summary(everything, limit, combined), "name": "Summe (Beteiligungen)"}
    # Bedarfsplan in der Summe nur über die Wehren, für die er sichtbar ist
    visible = [t for t in tenants if _plan_visible(t)]
    if len(visible) < len(tenants):
        shown = [e for t, evaluated, _ in parts if _plan_visible(t) for e in evaluated]
        plan = metrics.summary(shown, limit, tenant_config.combine("Summe", [t.config for t in visible])) \
            if visible else {}
        total.update({key: plan.get(key) for key in PLAN_KEYS})
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
    tenants = a.selection_with(EXPORT)
    year = year or _latest_year(tenants)
    if len(tenants) == 1 and not a.vg:
        tenant = tenants[0]
        with tenant.connection() as con:
            incidents = _names_for(tenant, store.load_incidents(con, year=year))
            members = store.members_of_year(con, year) if tenant.can(PEOPLE) else None
        if not incidents:
            raise HTTPException(404, "Keine Einsätze für den Export.")
        return _xlsx(lambda target: excel_export.write_workbook(incidents, members, year, target, tenant.config),
                     f"Einsaetze_{tenant.slug}_{year}")
    limit = tenants[0].config.default_limit
    parts, rows, total, notes = _summary(tenants, year, limit)
    workbook_parts = []
    for t, evaluated, _ in parts:
        with t.connection() as con:
            workbook_parts.append((t.config, _names_for(t, [i for i, _ in evaluated]),
                                   store.members_of_year(con, year) if t.can(PEOPLE) else None))
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
