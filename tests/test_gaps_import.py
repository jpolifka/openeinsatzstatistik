# -*- coding: utf-8 -*-
"""Grenzfälle beim Einlesen: Uploads, ZIP, Weitergabe, Vorschau-Sitzungen, Hintergrund-Jobs, Leseprozess."""
import io
import json
import threading
import time
import zipfile
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app import db, importing, parser_worker, preview_sessions, store, tenancy
from test_records import TEXTS, vg  # noqa: F401  (Fixture vg: drei Wehren einer VG, Texte der Berichte)
from test_xlsx_report import make_workbook


def _zip(entries):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return io.BytesIO(data.getvalue())


def _upload(name, data):
    return SimpleNamespace(filename=name, file=io.BytesIO(data) if isinstance(data, bytes) else data)


# ---------------------------------------------------------------- Budget, Spool, ZIP
def test_budget_refuses_more_than_left():
    budget = importing.Budget(10)
    assert budget.take(6) and not budget.take(5) and budget.take(4)
    assert budget.left == 0


def test_zip_with_too_many_reports_reads_only_the_first(monkeypatch):
    monkeypatch.setattr(importing, "ZIP_MAX_PDFS", 1)
    spool, errors = importing.collect_uploads([_upload("b.zip", _zip({"a.pdf": b"1", "b.pdf": b"2"}).getvalue())])
    with spool:
        assert [n for n, _ in spool.files] == ["a.pdf"]
    assert "Mehr als 1 Berichte" in errors[0]["message"]


def test_zip_entry_exceeding_limit_while_reading_is_reported(monkeypatch):
    """Die Größe im Verzeichnis der ZIP kann lügen: wird beim Lesen die Grenze überschritten, ist der Bericht zu groß."""
    archive = _zip({"a.pdf": b"x" * 5}).getvalue()
    monkeypatch.setattr(importing, "_save", lambda stream, path, limit: None)
    spool, errors = importing.collect_uploads([_upload("b.zip", archive)])
    with spool:
        assert spool.files == []
    assert errors == [{"file": "a.pdf", "message": "Bericht in der ZIP-Datei ist zu groß."}]


def test_zip_entry_declared_too_large_is_reported(monkeypatch):
    monkeypatch.setattr(importing, "ZIP_MAX_BYTES", 10)
    spool, errors = importing.collect_uploads([_upload("b.zip", _zip({"a.pdf": b"x" * 50}).getvalue())])
    spool.close()
    assert errors[0]["message"] == "Bericht in der ZIP-Datei ist zu groß."


def test_unreadable_zip_entry_is_reported_and_others_continue(monkeypatch):
    class Broken(zipfile.ZipFile):
        def open(self, info, *args, **kwargs):
            if getattr(info, "filename", info) == "kaputt.pdf":
                raise RuntimeError("password required")
            return super().open(info, *args, **kwargs)

    archive = _zip({"kaputt.pdf": b"1", "gut.pdf": b"2"}).getvalue()
    monkeypatch.setattr(importing.zipfile, "ZipFile", Broken)
    spool, errors = importing.collect_uploads([_upload("b.zip", archive)])
    with spool:
        assert [n for n, _ in spool.files] == ["gut.pdf"]
    assert "Nicht entpackbar (password required)" in errors[0]["message"]


def test_zip_budget_exhausted_while_unpacking_stops_the_archive():
    spool = importing.Spool()
    errors = []
    importing._unpack_zip(_zip({"a.pdf": b"x" * 100, "b.pdf": b"y"}), "b.zip", errors, importing.Budget(5), spool)
    spool.close()
    assert errors == [{"file": "b.zip", "message": importing.TOO_BIG}]


def test_upload_larger_than_budget_is_refused(monkeypatch):
    monkeypatch.setattr(importing, "UPLOAD_MAX_BYTES", 10)
    spool, errors = importing.collect_uploads([_upload("a.pdf", b"x" * 50), _upload("b.pdf", b"y")])
    spool.close()
    assert errors == [{"file": "a.pdf", "message": importing.TOO_BIG}]
    spool, errors = importing.collect_uploads([_upload("b.zip", _zip({"a.pdf": b"x" * 50}).getvalue())])
    spool.close()
    assert errors == [{"file": "b.zip", "message": importing.TOO_BIG}]


def test_collect_uploads_closes_spool_when_reading_fails():
    class Exploding:
        filename = "a.pdf"

        class file:                                  # noqa: N801
            @staticmethod
            def read(size):
                raise OSError("Platte voll")

    with pytest.raises(OSError):
        importing.collect_uploads([Exploding()])


# ---------------------------------------------------------------- Weitergabe
def _tenant(slug):
    return tenancy.access_for(None, f"t:{slug}").selected


def test_forward_of_already_recorded_report_and_full_queue(vg, monkeypatch):
    target = _tenant("wehr-a2")
    with target.connection() as con:
        store.create_incident(con, {"number": 1, "started_at": "2025-03-12T10:00:00", "bks_report_id": "9000002"},
                              source="pdf")
    head = {"bks_report_id": "9000002", "unit": "FW NR#.BHÖ 01", "unit_name": "Musterstadt"}
    assert "bereits erfasst" in importing.forward(target, head, "x.pdf", b"x", "a@example.org")
    fresh = {"bks_report_id": "9000077", "bks_record_id": "9000001", "unit": "FW NR#.BHÖ 01"}
    monkeypatch.setattr(importing, "PENDING_MAX_REPORTS", 0)
    with pytest.raises(ValueError, match="liegen schon viele Berichte"):
        importing.forward(target, fresh, "x.pdf", b"x", "a@example.org")


def test_report_of_unselected_tenant_is_forwarded_from_overview(vg, tmp_path):
    """Gesamtansicht mit zwei Wehren: der Bericht der dritten gehört keiner von beiden, ihre Wehr nimmt ihn an."""
    path = tmp_path / "a2.pdf"
    path.write_bytes(b"x")
    selected = [_tenant("wehr-a1"), _tenant("wehr-a3")]
    with pytest.raises(importing.Forward) as forwarded:
        importing._read_report(str(path), "a2.pdf", selected)
    assert forwarded.value.tenant.slug == "wehr-a2"


def test_unknown_unit_is_skipped_and_unmatched_report_is_an_error(vg, tmp_path, monkeypatch):
    from app import pdf_report
    path = tmp_path / "fez.pdf"
    path.write_bytes(b"x")
    two = [_tenant("wehr-a1"), _tenant("wehr-a3")]
    with pytest.raises(importing.Skipped, match="gehört zu keiner"):
        importing._read_report(str(path), "fez.pdf", two)
    text, left, right = TEXTS["a1.pdf"]
    monkeypatch.setattr(pdf_report, "extract_text", lambda p: (
        text.replace("Feuerwehrhaus: FW NR#.BHÖ 02 Musterdorf\n", "").replace("FL NR#.BHÖ", "XX"), left, right))
    with pytest.raises(ValueError, match="passt zu keiner"):
        importing._read_report(str(path), "ohne-einheit.pdf", two)


# ---------------------------------------------------------------- Vorschau-Sitzungen und Jobs
def test_claim_that_fails_restores_report_unless_cancelled():
    sessions = preview_sessions.PreviewSessions()
    token = sessions.add([({"filename": "a.pdf", "x": 1}, "slug"), ({"filename": "b.pdf", "x": 2}, "slug")], "owner")
    with pytest.raises(RuntimeError):
        with sessions.claim(token, "a.pdf", "owner"):
            raise RuntimeError("Speichern gescheitert")
    assert sessions.get(token, "a.pdf", "owner")[0]
    with pytest.raises(RuntimeError):
        with sessions.claim(token, "a.pdf", "owner"):
            sessions.cancel(token, "owner")
            raise RuntimeError("abgebrochen")
    assert sessions.get(token, "a.pdf", "owner") == (None, None)


def test_claim_of_unknown_or_foreign_session_yields_nothing():
    sessions = preview_sessions.PreviewSessions()
    token = sessions.add([({"filename": "a.pdf", "x": 1}, "slug")], "owner")
    with sessions.claim(token, "a.pdf", "other") as entry:
        assert entry == (None, None)
    with sessions.claim("gibt-es-nicht", "a.pdf", "owner") as entry:
        assert entry == (None, None)


def test_expired_sessions_are_dropped(monkeypatch):
    sessions = preview_sessions.PreviewSessions()
    token = sessions.add([({"filename": "a.pdf", "x": 1}, "slug")], "owner")
    monkeypatch.setattr(sessions, "TTL", -1)
    sessions.add([({"filename": "b.pdf", "x": 1}, "slug")], "owner")   # räumt Abgelaufene beim Anlegen weg
    assert sessions.get(token, "a.pdf", "owner") == (None, None)


def _wait(jobs, job, owner):
    for _ in range(200):
        status = jobs.status(job, owner)
        if status["done"] or status["error"]:
            return status
        time.sleep(0.01)
    raise AssertionError("Job wurde nicht fertig")


def test_job_errors_are_reported_and_old_jobs_are_dropped(monkeypatch):
    jobs = preview_sessions.ReadJobs()

    def http_error(progress):
        raise HTTPException(409, "Konflikt")

    def crash(progress):
        raise KeyError("x")

    assert _wait(jobs, jobs.start("o", 1, http_error), "o")["error"] == (409, "Konflikt")
    assert _wait(jobs, jobs.start("o", 1, crash), "o")["error"] == (500, "Beim Einlesen ist ein Fehler aufgetreten. Bitte erneut versuchen.")
    old = jobs.start("o", 1, lambda progress: 1)
    for _ in range(200):                                             # fertig, aber (noch) nicht abgeholt
        if jobs._jobs[old]["result"] is not None:
            break
        time.sleep(0.01)
    monkeypatch.setattr(jobs, "TTL", -1)
    jobs.start("o", 1, lambda progress: 1)                         # entfernt abgelaufene Jobs
    assert old not in jobs._jobs


def test_running_jobs_per_owner_are_limited():
    jobs = preview_sessions.ReadJobs()
    release = threading.Event()
    first = [jobs.start("o", 1, lambda progress: release.wait(5)) for _ in range(2)]
    with pytest.raises(HTTPException) as refused:
        jobs.start("o", 1, lambda progress: 1)
    assert refused.value.status_code == 429
    release.set()
    for job in first:
        _wait(jobs, job, "o")


# ---------------------------------------------------------------- Leseprozess
class _Pipe:
    def __init__(self):
        self.sent, self.closed = [], False

    def send_bytes(self, data):
        self.sent.append(json.loads(data))

    def close(self):
        self.closed = True


def test_child_sends_result_or_error_and_sets_limits(tmp_path, monkeypatch):
    path = tmp_path / "a.xlsx"
    path.write_bytes(make_workbook())
    limits = []
    import resource
    monkeypatch.setattr(resource, "setrlimit", lambda kind, values: limits.append(kind))
    monkeypatch.setattr(parser_worker.sys, "platform", "linux")
    ok = _Pipe()
    parser_worker._child(ok, "xlsx", str(path))
    assert ok.sent[0]["ok"] is True and ok.closed and len(limits) == 2
    failed = _Pipe()
    parser_worker._child(failed, "pdf", str(tmp_path / "gibt-es-nicht.pdf"))
    assert failed.sent[0]["ok"] is False and failed.closed


def test_child_skips_limits_off_linux(tmp_path, monkeypatch):
    path = tmp_path / "a.xlsx"
    path.write_bytes(make_workbook())
    monkeypatch.setattr(parser_worker.sys, "platform", "darwin")
    pipe = _Pipe()
    parser_worker._child(pipe, "xlsx", str(path))
    assert pipe.sent[0]["ok"] is True


def test_read_refuses_when_all_slots_are_busy(monkeypatch):
    monkeypatch.setattr(parser_worker, "_slots", threading.Semaphore(0))
    monkeypatch.setattr(parser_worker, "MAX_SECONDS", 0.01)
    with pytest.raises(ValueError, match="gleichzeitig"):
        parser_worker.read("xlsx", "egal")


def test_read_reports_failed_process_start(monkeypatch):
    class FailingProcess:
        pid = None

        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            raise OSError("fork gescheitert")

        def is_alive(self):
            return False

    class Context:
        Process = FailingProcess

        @staticmethod
        def Pipe(duplex=False):                      # noqa: N802
            return _Pipe(), _Pipe()

    monkeypatch.setattr(parser_worker.multiprocessing, "get_context", lambda name: Context)
    with pytest.raises(ValueError, match="Verarbeitungsgrenzen"):
        parser_worker.read("xlsx", "egal")
