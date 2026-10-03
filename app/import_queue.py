"""Dauerhafte Nachverarbeitung gespeicherter Berichte; Wiederholung nach Neustart."""
import datetime as dt
import json
import logging
import uuid
from types import SimpleNamespace

log = logging.getLogger("pdf2einsatz")


def _encode(value):
    for kind in (dt.datetime, dt.date, dt.time):
        if isinstance(value, kind):
            return {"__report_time__": kind.__name__, "value": value.isoformat()}
    raise TypeError(f"Nicht serialisierbarer Berichtswert: {type(value).__name__}")


def _decode(value):
    kinds = {"datetime": dt.datetime, "date": dt.date, "time": dt.time}
    if set(value) == {"__report_time__", "value"} and value["__report_time__"] in kinds:
        return kinds[value["__report_time__"]].fromisoformat(value["value"])
    return value


def enqueue(con, incident_id, report, access, tenant, updated):
    """Auftrag in derselben Transaktion wie den Einsatz speichern."""
    job_id = uuid.uuid4().hex
    con.execute("INSERT INTO import_job (id, incident_id, report, email, is_member, updated) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (job_id, incident_id, json.dumps(report, default=_encode, ensure_ascii=False),
                 access.email, int(access.is_member(tenant)), int(updated)))
    return job_id


def process(tenant, job_id, after_import):
    """Fehler behalten den Auftrag; bereits gespeicherte Einsätze bleiben erfolgreich übernommen."""
    with tenant.connection() as con:
        job = con.execute("SELECT * FROM import_job WHERE id = ?", (job_id,)).fetchone()
    if not job:
        return True
    try:
        report = json.loads(job["report"], object_hook=_decode)
        access = SimpleNamespace(email=job["email"], is_member=lambda _: bool(job["is_member"]))
        after_import(access, tenant, report, job["incident_id"], bool(job["updated"]), job_id=job_id)
        with tenant.connection() as con:
            con.execute("DELETE FROM import_job WHERE id = ?", (job_id,))
        return True
    except Exception:
        log.exception("Nachverarbeitung für Wehr %s, Auftrag %s bleibt offen", tenant.slug, job_id)
        return False


def retry(tenant, after_import):
    with tenant.connection() as con:
        jobs = [row[0] for row in con.execute("SELECT id FROM import_job")]
    for job_id in jobs:
        process(tenant, job_id, after_import)
