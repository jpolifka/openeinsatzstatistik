# -*- coding: utf-8 -*-
"""Berichte einlesen und übernehmen, weitergegebene Berichte, Hinweise.
"""
from typing import List, Optional

from fastapi import Depends, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app import import_queue, records, report, signoff, store, tenancy
from app.rbac import IMPORT, INCIDENTS, PEOPLE, WRITE
from app.timeutil import year_of

from fastapi import APIRouter
from app.api import common
from app.api.common import access, incident_json, incident_key, log, parse_incident_key
from app.api.incidents import IncidentFields
from app import importing
from app.importing import Spool, collect_uploads, forward, is_upload, preview_json, read_files, save_master
router = APIRouter()


def _read_result(files, errors, tenants, a, progress=None):
    """Dateien lesen und als Vorschau ablegen -> Antwort für die Oberfläche."""
    reports, more_errors, notes = read_files(files, tenants, a.email, progress)
    previews_json = [preview_json(r, tenant, a) for r, tenant in reports]
    token = common.previews.add([(r, tenant.slug) for r, tenant in reports], a.email)
    return {"token": token, "reports": previews_json, "errors": errors + more_errors, "notes": notes}


def _signed(con, incident_id):
    """Einsatz mit Stand der Signatur und die Namen der Einheitsführung."""
    return signoff.attach(con, "incident", [store.load_incident(con, incident_id)])[0], store.LeaderNames(con)


@router.post("/api/reports")
def api_read_reports(pdfs: List[UploadFile] = File(...), background: bool = False,
                     a: tenancy.Access = Depends(access)):
    """Berichte lesen – für die ausgewählte Wehr oder, in der Gesamtansicht, verteilt auf die passende
    Wehr der VG (nur Wehren mit Schreibrecht). Mit background=true antwortet die Anfrage sofort mit einem
    Job ({job, total}); Fortschritt und Ergebnis über /api/reports/jobs/{job} – viele Berichte (ZIP)
    brauchen sonst länger, als ein Proxy wartet."""
    tenants = a.selection_with(IMPORT) if a.vg else [a.current(IMPORT)]
    pdfs = [p for p in pdfs if is_upload(p.filename)]
    if not pdfs:
        raise HTTPException(400, "Bitte eine PDF-, Excel- oder ZIP-Datei (Einsatzberichte aus dem BKS-Portal) auswählen.")
    release = common.upload_slots.acquire(a.email)
    try:
        spool, errors = collect_uploads(pdfs)
    except BaseException:
        release()
        raise

    def work(progress=None):
        try:
            return _read_result(spool.files, errors, tenants, a, progress)
        finally:                                  # Arbeitsordner und Platz erst nach dem Lesen freigeben
            spool.close()
            release()

    if not background:
        return work()
    try:
        job = common.read_jobs.start(a.email, len(spool.files), work)
    except BaseException:
        spool.close()
        release()
        raise
    return JSONResponse({"job": job, "total": len(spool.files)}, status_code=202)


@router.get("/api/reports/jobs/{job}")
def api_read_job(job: str, a: tenancy.Access = Depends(access)):
    """Stand eines Lesevorgangs: {read, total, done}; fertig zusätzlich das Ergebnis wie bei /api/reports."""
    status = common.read_jobs.status(job, a.email)
    if status is None:
        raise HTTPException(404, "Der Lesevorgang ist nicht mehr vorhanden. Bitte die Berichte erneut einlesen.")
    if status["error"]:
        code, detail = status["error"]
        raise HTTPException(code, detail)
    return {"read": status["read"], "total": status["total"], "done": status["done"],
            **(status["result"] or {})}


class Acceptance(BaseModel):
    token: str
    filename: str
    fields: IncidentFields
    replace: bool = False
    revision: Optional[int] = Field(default=None, ge=0, strict=True)


class PreviewCancellation(BaseModel):
    token: str


@router.post("/api/reports/cancel")
def api_cancel_reports(cancellation: PreviewCancellation, a: tenancy.Access = Depends(access)):
    common.previews.cancel(cancellation.token, a.email)
    return {"ok": True}


@router.post("/api/reports/accept")
def api_accept_report(acceptance: Acceptance, a: tenancy.Access = Depends(access)):
    with common.previews.claim(acceptance.token, acceptance.filename, a.email) as (r, slug):
        if not r:
            raise HTTPException(410, "Die Vorschau ist abgelaufen oder der Bericht wurde schon übernommen – "
                                     "bitte den Bericht erneut einlesen.")
        return _accept_report(acceptance, a, r, slug)


def _accept_report(acceptance, a, r, slug):
    tenant = a.tenant(slug, IMPORT)
    if r.get("_action") == "master":
        save_master(r, tenant.vg_id, a.email)
        return {"message": "Stammdatensatz gespeichert."}
    if r.get("_action") == "forward":
        target = next((t for t in tenancy.vg_tenants(tenant.vg_id) if t.slug == r["_target"]), None)
        if not target:
            raise HTTPException(409, "Die zuständige Wehr ist nicht mehr verfügbar. Bitte erneut einlesen.")
        try:
            return {"message": forward(target, r, r["filename"], r["_data"], a.email)}
        except ValueError as error:          # bei der Zielwehr liegt schon zu viel bereit
            raise HTTPException(409, str(error))
    if acceptance.replace:
        a.tenant(slug, WRITE)              # erfassten Einsatz überschreiben = bearbeiten
    corrected = acceptance.fields.model_dump(exclude_unset=True)
    if not tenant.can(PEOPLE):
        corrected.pop("unit_leader", None)   # sieht den Einheitsführung nicht, also bleibt der aus dem Bericht
    fields = {**report.to_fields(r), **corrected}
    try:
        store.normalize_fields(fields)
    except ValueError as error:
        raise HTTPException(422, str(error))
    by_date = tenant.config.numbering == "by_date"
    year = year_of(fields.get("started_at"))
    with tenant.connection() as con:
        con.execute("BEGIN IMMEDIATE")    # next_number und Speichern als eine Sperre: keine doppelte Nummer
        update_id = r.get("_existing_id") if acceptance.replace else None
        original = store.load_incident(con, update_id) if update_id else None
        old_year = original["year"] if original else None
        if acceptance.replace:
            if acceptance.revision is None:
                raise HTTPException(428, "Zum Aktualisieren ist die Revision der Vorschau erforderlich.")
            if not original or original["revision"] != acceptance.revision:
                raise HTTPException(409, "Der Einsatz wurde inzwischen geändert. Bitte erneut einlesen und vergleichen.")
        if original:
            fields = report.keep_recorded(fields, original, set(corrected))
            year = year_of(fields.get("started_at") or original["started_at"])
        if by_date:
            # Vorläufig ans Ende, die richtige Stelle ergibt sich nach dem Speichern
            fields["number"] = store.next_number(con, year) if year else None
        elif store.to_int(fields.get("number", original["number"] if original else None)) is None and year:
            fields["number"] = store.next_number(con, year)
            r["warnings"].append(f"Einsatzbericht-Nr. fehlt – nächste freie Nr. {fields['number']} vergeben")
        try:
            incident_id = report.save(con, r, fields, update_id, modified_by=a.email,
                                      revision=acceptance.revision)
        except store.DuplicateIncident as e:
            raise HTTPException(409, str(e))
        except store.StaleIncident as e:
            raise HTTPException(409, str(e))
        if by_date:
            for y in {year, old_year} - {None}:
                store.renumber(con, y)
        store.delete_pending(con, r.get("pending_id"), r.get("bks_report_id"))
        job_id = import_queue.enqueue(con, incident_id, r, a, tenant, bool(update_id))
    processed = import_queue.process(tenant, job_id, importing.after_import)
    if r.get("new_vehicles"):
        tenancy.forget_config(tenant.slug)
        log.info("Fahrzeuge %s in die Liste von %s aufgenommen", ", ".join(r["new_vehicles"]), tenant.slug)
    with tenant.connection() as con:
        result = incident_json(*_signed(con, incident_id), tenant)
        result["postprocessing_pending"] = not processed
        return result


# ---------------------------------------------------------------- Weitergegebene Berichte
@router.get("/api/pending")
def api_pending(a: tenancy.Access = Depends(access)):
    """Berichte, die jemand aus einer anderen Wehr für die ausgewählten Wehren eingelesen hat."""
    result, jobs = [], []
    for tenant in a.selection_with(IMPORT):
        with tenant.connection() as con:
            result += [{**p, "id": incident_key(tenant, p["id"]), "tenant": tenant.slug, "tenant_name": tenant.name}
                       for p in store.pending_reports(con)]
            jobs += [{"tenant_name": tenant.name, "count": con.execute("SELECT COUNT(*) FROM import_job").fetchone()[0]}]
    return {"reports": result, "postprocessing": [job for job in jobs if job["count"]]}


class PendingSelection(BaseModel):
    ids: List[str] = Field(max_length=50)


@router.post("/api/pending/read")
def api_read_pending(selection: PendingSelection, a: tenancy.Access = Depends(access)):
    """Abgelegte Berichte wie hochgeladene Dateien lesen (Vorschau, Übernahme wie bei /api/reports)."""
    release = common.upload_slots.acquire(a.email)      # liest wie ein Upload: Parser und tmpfs sind geteilt
    try:
        reports, errors, notes = [], [], []
        for key in selection.ids:
            slug, pending_id = parse_incident_key(key)
            tenant = a.tenant(slug, IMPORT)
            with tenant.connection() as con:
                filename, data = store.pending_pdf(con, pending_id)
            if not filename:
                errors.append({"file": key, "message": "Der Bericht liegt nicht mehr bereit."})
                continue
            with Spool() as spool:
                spool.add_bytes(filename, data)
                read, more_errors, more_notes = read_files(spool.files, [tenant], a.email)
            for r, _ in read:
                r["pending_id"] = pending_id
            reports += read
            errors += more_errors
            notes += more_notes
    finally:
        release()
    previews_json = [preview_json(r, tenant, a) for r, tenant in reports]
    token = common.previews.add([(r, tenant.slug) for r, tenant in reports], a.email)
    return {"token": token, "reports": previews_json, "errors": errors, "notes": notes}


@router.delete("/api/pending/{key}")
def api_discard_pending(key: str, a: tenancy.Access = Depends(access)):
    slug, pending_id = parse_incident_key(key)
    with a.tenant(slug, IMPORT).connection() as con:
        store.delete_pending(con, pending_id)
    return {"ok": True}


# ---------------------------------------------------------------- Hinweise
@router.get("/api/notices")
def api_notices(a: tenancy.Access = Depends(access)):
    """Offene Hinweise der Wehren, deren Einsätze der Benutzer sehen darf."""
    ids = [t.id for t in a.tenants.values() if t.can(INCIDENTS)]
    with tenancy.central() as con:
        notices = records.open_notices(con, ids)
    writable = {t.slug for t in a.tenants.values() if t.can(WRITE)}
    return {"notices": [{**n, "can_close": n["tenant"] in writable} for n in notices]}


@router.post("/api/notices/{notice_id}/done")
def api_close_notice(notice_id: int, a: tenancy.Access = Depends(access)):
    with tenancy.central() as con:
        row = con.execute("SELECT t.slug FROM notice n JOIN tenant t ON t.id = n.tenant_id WHERE n.id = ?",
                          (notice_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Hinweis nicht gefunden.")
        a.tenant(row["slug"], WRITE)
        records.close_notice(con, notice_id, a.email)
    return {"ok": True}


