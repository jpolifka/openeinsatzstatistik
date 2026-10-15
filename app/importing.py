# -*- coding: utf-8 -*-
"""Berichte einlesen (PDF, Excel-Export, ZIP): Lesen, Zuordnen zur Wehr, Weitergeben, Nachbearbeitung.
Kein HTTP außer den Fehlerklassen der Anfrage.
"""
import concurrent.futures
import os
import tempfile
import zipfile


from app import parser_worker
from app import records, report, store, tenancy
from app.rbac import PEOPLE, STATS
from app.api.common import incident_json, incident_key, log, safe_filename


# ---------------------------------------------------------------- Berichte einlesen (PDF, Excel-Export)
ZIP_MAX_PDFS = 500
ZIP_MAX_BYTES = 50 * 1024 * 1024     # je entpacktem Bericht
UPLOAD_MAX_BYTES = 100 * 1024 * 1024  # je Upload: hochgeladen bzw. entpackt zusammen (Platte, tmpfs des Containers)
REPORT_TYPES = (".pdf", ".xlsx")
PENDING_MAX_REPORTS = 200            # weitergegebene Berichte, die je Wehr zur Übernahme bereitliegen
PENDING_MAX_BYTES = 200 * 1024 * 1024
CHUNK = 1024 * 1024


def is_upload(filename):
    return (filename or "").lower().endswith((*REPORT_TYPES, ".zip"))


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


class Spool:
    """Berichte eines Uploads als Dateien in einem Arbeitsordner, nicht im Speicher: ein Upload belegt so
    höchstens seinen Anteil am tmpfs, nicht zusätzlich den Arbeitsspeicher des einzigen Workers.
    files: [(Anzeigename, Pfad)] in der Reihenfolge des Uploads."""

    def __init__(self):
        self._dir = tempfile.TemporaryDirectory(prefix="upload-")
        self.files, self._names = [], set()

    def target(self, filename):
        """Pfad für eine neue Datei; gleichnamige Berichte (z. B. aus Unterordnern einer ZIP) werden durchnummeriert."""
        stem, ext = os.path.splitext(filename)
        shown, n = filename, 2
        while shown in self._names:
            shown, n = f"{stem} ({n}){ext}", n + 1
        self._names.add(shown)
        return shown, os.path.join(self._dir.name, shown)

    def add_bytes(self, filename, data):
        shown, path = self.target(filename)
        with open(path, "wb") as fh:
            fh.write(data)
        self.files.append((shown, path))

    def close(self):
        self._dir.cleanup()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def _save(stream, path, limit):
    """Stream höchstens bis limit Bytes in die Datei kopieren -> Größe, bei Überschreitung None (Datei entfernt)."""
    size = 0
    with open(path, "wb") as out:
        while True:
            chunk = stream.read(min(CHUNK, limit + 1 - size))
            if not chunk:
                break
            size += len(chunk)
            if size > limit:
                break
            out.write(chunk)
    if size > limit:
        os.remove(path)
        return None
    return size


def _unpack_zip(stream, zip_name, errors, budget, spool):
    """Berichte (PDF, xlsx) aus einer ZIP-Datei in den Arbeitsordner entpacken, einzeln und in Stücken. Andere
    Dateien werden übergangen."""
    try:
        archive = zipfile.ZipFile(stream)
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
        name = safe_filename(info.filename)
        if info.file_size > ZIP_MAX_BYTES:
            errors.append({"file": name, "message": "Bericht in der ZIP-Datei ist zu groß."})
            continue
        shown, path = spool.target(name)
        try:
            with archive.open(info) as fh:      # Größe aus dem Verzeichnis nicht trauen: begrenzt lesen
                size = _save(fh, path, min(ZIP_MAX_BYTES, budget.left))
        except Exception as e:  # verschlüsselt oder beschädigt
            errors.append({"file": name, "message": f"Nicht entpackbar ({e or type(e).__name__})."})
            continue
        if size is None:
            # an der Bericht-Grenze: Bericht zu groß; sonst ist das Budget des Uploads aufgebraucht
            if budget.left >= ZIP_MAX_BYTES:
                errors.append({"file": name, "message": "Bericht in der ZIP-Datei ist zu groß."})
                continue
            errors.append({"file": zip_name, "message": TOO_BIG})
            return
        budget.take(size)
        spool.files.append((shown, path))


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


def collect_uploads(uploads):
    """Hochgeladene Dateien und den Inhalt von ZIP-Dateien in einen Arbeitsordner holen -> (Spool, fehler).
    Den Spool schließt der Aufrufer (close), sobald gelesen ist."""
    errors, budget, spool = [], Budget(), Spool()
    try:
        for upload in uploads:
            filename = safe_filename(upload.filename)
            if filename.lower().endswith(".zip"):
                stream = upload.file
                stream.seek(0, os.SEEK_END)
                size = stream.tell()
                stream.seek(0)
                if not budget.take(size):
                    errors.append({"file": filename, "message": TOO_BIG})
                    break
                _unpack_zip(stream, filename, errors, budget, spool)
            else:
                shown, path = spool.target(filename)
                size = _save(upload.file, path, budget.left)
                if size is None:
                    errors.append({"file": filename, "message": TOO_BIG})
                    break
                budget.take(size)
                spool.files.append((shown, path))
    except BaseException:
        spool.close()
        raise
    return spool, errors


def read_files(files, tenants, email=None, progress=None):
    """Alle Berichtsarten ausschließlich lesen; Schreiben erfolgt erst nach Bestätigung. files: [(Anzeigename,
    Pfad)] (Spool.files). Mehrere Dateien gleichzeitig (parser_worker.WORKERS), Ergebnisse in der Reihenfolge der
    Dateien; progress() je Datei."""
    reports, errors, notes = [], [], []

    def read(job):
        filename, path = job
        try:
            return _read_report(path, filename, tenants), None
        except Exception as e:
            return None, e
        finally:
            if progress:
                progress()

    with concurrent.futures.ThreadPoolExecutor(max_workers=parser_worker.WORKERS) as pool:
        results = list(pool.map(read, files))
    for (filename, path), (result, failure) in zip(files, results):
        try:
            if failure:
                raise failure
            r, tenant = result
        except Skipped as e:
            notes.append({"file": filename, "message": str(e)})
            continue
        except Forward as f:
            with open(path, "rb") as fh:         # nur Berichte zur Weitergabe werden ganz geladen
                f.head.update(filename=filename, _action="forward", _target=f.tenant.slug, _data=fh.read())
            reports.append((f.head, tenants[0]))
            continue
        except Exception as e:  # defekte oder fremde Datei: melden, Rest weiter lesen
            log.exception("Bericht %s", filename)
            errors.append({"file": filename, "message": str(e) or type(e).__name__})
            continue
        if tenant:
            reports.append((r, tenant))
            continue
        r.update(filename=filename, _action="master")
        reports.append((r, tenants[0]))
    return reports, errors, notes


def save_master(r, vg_id, email):
    """Stammdatensatz speichern; Wehren mit ausgerückten Fahrzeugen, aber ohne Bericht bekommen einen Hinweis."""
    log.info("Stammdatensatz %s der VG %s gespeichert durch %s", r.get("bks_record_id"), vg_id, email or "lokal")
    with tenancy.central() as con:
        records.save_master(con, vg_id, r, email)
        records.notify_others(con, r, r["vehicles"], "Stammdatensatz", tenancy.vg_tenants(vg_id),
                              deviations=False, email=email)


def forward(tenant, head, filename, data, email):
    """Bericht einer anderen Wehr der VG dort zur Übernahme ablegen -> Meldung für den Hochladenden."""
    with tenant.connection() as con:
        if head["bks_report_id"] and store.find_existing(con, head["bks_report_id"], None, None):
            return f"Bericht der Einheit {report.unit_label(head)} – bei {tenant.name} bereits erfasst, übersprungen."
        count, size = store.pending_usage(con)
        if count >= PENDING_MAX_REPORTS or size + len(data) > PENDING_MAX_BYTES:
            raise ValueError(f"Bei {tenant.name} liegen schon viele Berichte zur Übernahme bereit. Bitte dort erst "
                             "übernehmen oder verwerfen, dann erneut weitergeben.")
        store.add_pending(con, head, filename, data, email)
    when = records.format_date(head.get("first_alarm"))
    with tenancy.central() as con:
        records.notify(con, tenant.id, "pending",
                       f"Bericht {head.get('number_text') or filename} vom {when} ({head.get('reported_as') or '–'}) "
                       f"von {email or 'lokal'} eingelesen – liegt zur Übernahme bereit.",
                       head.get("bks_record_id"), email=email)
        records.close_notices(con, tenant.id, head.get("bks_record_id"), ("missing",))
    return f"Bericht der Einheit {report.unit_label(head)} an {tenant.name} zur Übernahme weitergegeben."


def after_import(a, tenant, r, incident_id, updated, job_id=None):
    """Nach dem Speichern: Bericht im Verzeichnis vermerken, Hinweise an die eigene Wehr (eingelesen
    durch jemanden ohne eigene Rolle dort) und an andere Wehren (Abweichungen, fehlende Berichte)."""
    with tenancy.central() as con:
        if job_id and con.execute("SELECT 1 FROM completed_import WHERE id = ?", (job_id,)).fetchone():
            return
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
        if job_id:
            con.execute("INSERT INTO completed_import (id) VALUES (?)", (job_id,))


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


def preview_json(r, tenant, a):
    if r.get("_action"):
        action = r["_action"]
        target = next((t for t in tenancy.vg_tenants(tenant.vg_id) if t.slug == r.get("_target")), None)
        return {"filename": r["filename"], "action": action,
                "title": f"Stammdatensatz {r.get('bks_record_id') or 'ohne Kennung'}" if action == "master"
                else f"Bericht für {target.name if target else 'andere Wehr'}",
                "message": "Nach Bestätigung zentral speichern und beteiligte Wehren informieren."
                if action == "master" else "Nach Bestätigung zur Übernahme an die zuständige Wehr weitergeben."}
    cfg = tenant.config.with_new_vehicles(report.new_fleet_vehicles(r), r.get("day"))
    with tenant.connection() as con:
        incident, existing = report.preview(con, r, numbered=tenant.config.numbering != "by_date")
        result = incident_json(incident, store.LeaderNames(con), tenant, cfg=cfg)
    r["_existing_id"] = existing["id"] if existing else None
    result["tenant_name"] = tenant.name
    result["new_vehicles"] = r.get("new_vehicles", [])
    result["reported_as"] = r["reported_as"]
    names = tenant.can(PEOPLE)                  # Einsatzleiter und Einheitsführung sind Namen
    result["incident_commander"] = r["incident_commander"] if names else None
    differences = report.differences(existing, incident, tenant.config) if existing else []
    result["existing"] = {"id": incident_key(tenant, existing["id"]), "source": existing["source"],
                          "revision": existing["revision"],
                          "differences": [d for d in differences if names or d["field"] != "Einheitsführung"]} \
        if existing else None
    result["shared_with"] = _shared_with(r, tenant, a)
    return result

