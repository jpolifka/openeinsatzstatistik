# -*- coding: utf-8 -*-
"""Härtung nach dem Security-Audit: Grenzen für Uploads und Eingaben, Anmeldung, Mail, AVV, Sitzungen."""
import io
import logging
import re
import time
import zipfile

import pytest
from fastapi import HTTPException

from app import auth, bks_common, db, importing, mail, main, store, tenancy
from app.preview_sessions import UploadSlots
from conftest import grant, make_tenant


@pytest.fixture
def client(make_client):
    make_tenant("wehr-a1")
    return make_client()


# ---------------------------------------------------------------- Uploads
def test_upload_slots_are_limited_per_owner_and_in_total():
    slots = UploadSlots()
    first = slots.acquire("a@example.org")
    with pytest.raises(HTTPException) as e:
        slots.acquire("a@example.org")                      # derselbe Benutzer: ein Platz
    assert e.value.status_code == 429
    second = slots.acquire("b@example.org")
    with pytest.raises(HTTPException):
        slots.acquire("c@example.org")                      # insgesamt zwei
    first()
    first()                                                 # doppeltes Freigeben zählt nicht doppelt
    slots.acquire("c@example.org")
    second()


def test_busy_slots_answer_429_and_free_themselves(client):
    from app.api import common
    release = common.upload_slots.acquire(None)             # ohne Anmeldung ist der Besitzer None
    try:
        busy = client.post("/api/reports", files=[("pdfs", ("a.pdf", b"x", "application/pdf"))])
        assert busy.status_code == 429
    finally:
        release()
    ok = client.post("/api/reports", files=[("pdfs", ("a.pdf", b"x", "application/pdf"))])
    assert ok.status_code == 200                            # Platz nach der Anfrage wieder frei
    assert client.post("/api/reports", files=[("pdfs", ("b.pdf", b"x", "application/pdf"))]).status_code == 200


def test_uploads_are_spooled_to_disk_and_removed(client, monkeypatch):
    seen = []
    from app import parser_worker
    original = parser_worker.read_local

    def spy(kind, path):
        import os
        seen.append(os.path.dirname(path[0]) if isinstance(path, tuple) else os.path.dirname(path))
        return original(kind, path)

    monkeypatch.setattr(parser_worker, "read", spy)
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("x/a.pdf", b"kein pdf")
    client.post("/api/reports", files=[("pdfs", ("b.zip", archive.getvalue(), "application/zip"))])
    import os
    assert seen and all(not os.path.exists(d) for d in seen)         # Arbeitsordner ist aufgeräumt


def test_spool_names_are_unique_and_stay_inside(tmp_path):
    with importing.Spool() as spool:
        first = spool.target("../a.pdf")
        spool.add_bytes("a.pdf", b"1")
        spool.add_bytes("a.pdf", b"2")
        names = [name for name, _ in spool.files]
        assert names == ["a.pdf", "a (2).pdf"]
        assert all(path.startswith(spool._dir.name) for _, path in spool.files)
        assert first


# ---------------------------------------------------------------- Eingaben
def test_vehicle_regex_is_linear_on_long_lines():
    line = "A" * 200_000
    started = time.time()
    assert bks_common.PERSON_VEHICLE.findall(line) == []
    assert time.time() - started < 2                       # vorher: Sekunden bis Minuten (quadratisch)
    assert bks_common.PERSON_VEHICLE.findall("FL NR#.ABC 02/45-01")


def test_parse_test_line_is_limited(client):
    assert client.post("/api/admin/parse-test", json={"line": "A" * 6000}).status_code == 422
    assert client.post("/api/admin/parse-test", json={"line": "FL NR#.ABC 02/45-01"}).status_code == 200


def test_incident_text_and_row_counts_are_limited(client):
    with db.connection(tenancy.tenant_path("wehr-a1")) as con:
        incident_id = store.create_incident(con, {"number": 1, "started_at": "2025-03-12T10:00:00",
                                                  "keyword": "B2"}, source="pdf")
    key = f"wehr-a1:{incident_id}"
    assert client.put(f"/api/incidents/{key}", json={"revision": 0, "description": "x" * 501}).status_code == 422
    people = [{"name": f"Muster, Person{i}"} for i in range(301)]
    assert client.put(f"/api/incidents/{key}", json={"revision": 0, "people": people}).status_code == 422
    assert client.put(f"/api/incidents/{key}", json={"revision": 0, "description": "x" * 500}).status_code == 200


def test_large_json_body_is_refused_before_parsing(client):
    big = b'{"description": "' + b"x" * (3 * 1024 * 1024) + b'"}'
    response = client.put("/api/incidents/wehr-a1:1", content=big, headers={"content-type": "application/json"})
    assert response.status_code == 413


def test_fee_request_rejects_non_finite_amounts(client):
    body = '{"expenses": [{"label": "x", "amount": NaN}], "vat_percent": 0}'
    response = client.post("/api/records/9000001/fees", content=body, headers={"content-type": "application/json"})
    assert response.status_code == 422                      # Validierung, nicht 500 beim Serialisieren der Antwort
    assert "NaN" not in response.text and "nan" not in response.text.lower().replace("finance", "")
    from app.api.records import FeeRequest
    with pytest.raises(ValueError):
        FeeRequest.model_validate_json(body)
    with pytest.raises(ValueError):
        FeeRequest.model_validate({"vat_percent": float("inf")})


def test_keyword_import_limits_field_length(client):
    row = "B2.07;" + "N" * 121 + ";x\n"
    response = client.post("/api/admin/wehr-a1/keywords/import?mode=preview",
                           files={"file": ("k.csv", row.encode(), "text/csv")})
    assert response.status_code == 422 and "120" in response.json()["detail"]


# ---------------------------------------------------------------- Anmeldung und Mail
def test_login_link_is_not_logged_for_public_address(monkeypatch, caplog):
    monkeypatch.setattr(tenancy, "ADMIN_EMAILS", {"admin@example.org"})
    monkeypatch.setattr(auth, "_key", None)
    monkeypatch.setattr(mail, "SMTP_HOST", "")
    monkeypatch.setattr(auth, "_last_mail", {})
    monkeypatch.setattr(auth, "BASE_URL", "https://einsatz.example.org")
    with caplog.at_level(logging.INFO):
        auth.send_link("admin@example.org")
    assert "token=" not in caplog.text and "nicht versendet" in caplog.text


def test_login_without_mail_needs_local_address(monkeypatch):
    monkeypatch.setattr(tenancy, "ADMIN_EMAILS", {"admin@example.org"})
    monkeypatch.setattr(mail, "SMTP_HOST", "")
    monkeypatch.setattr(auth, "BASE_URL", "https://einsatz.example.org")
    with pytest.raises(RuntimeError, match="SMTP_HOST"):
        auth.check_config()
    monkeypatch.setattr(auth, "BASE_URL", "http://localhost:8112")
    auth.check_config()


def test_mails_per_address_are_capped(monkeypatch, data_dir):
    monkeypatch.setattr(tenancy, "ADMIN_EMAILS", {"admin@example.org"})
    monkeypatch.setattr(auth, "_key", None)
    monkeypatch.setattr(auth, "_last_mail", {})
    monkeypatch.setattr(auth, "_sent", [])
    monkeypatch.setattr(auth, "MAIL_COOLDOWN", 0)
    monkeypatch.setattr(mail, "SMTP_HOST", "smtp.example.org")
    sent = []
    monkeypatch.setattr(mail, "send", lambda *args, **kwargs: sent.append(args[0]))
    monkeypatch.setattr(auth, "BASE_URL", "https://einsatz.example.org")
    for _ in range(auth.MAIL_PER_ADDRESS + 5):
        auth.send_link("admin@example.org")
    assert len(sent) == auth.MAIL_PER_ADDRESS
    # Die Sperre ist kurz: nach dem Zeitfenster kommen wieder Mails (kein Aussperren über Tage)
    monkeypatch.setattr(auth, "_sent", [(t - auth.MAIL_WINDOW - 1, a) for t, a in auth._sent])
    auth.send_link("admin@example.org")
    assert len(sent) == auth.MAIL_PER_ADDRESS + 1


def test_access_log_masks_login_token():
    record = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d',
                               ("1.2.3.4", "GET", "/auth/verify?token=abc.def&x=1", "1.1", 200), None)
    assert main._MaskLoginToken().filter(record)
    assert "abc.def" not in record.getMessage() and "token=***&x=1" in record.getMessage()


def test_sessions_per_user_are_capped(data_dir):
    make_tenant("wehr-a1")
    grant("m.muster@example.org", "viewer", 1)
    tokens = [auth.create_session("m.muster@example.org") for _ in range(auth.MAX_SESSIONS_PER_USER + 3)]
    with tenancy.central() as con:
        left = con.execute("SELECT COUNT(*) FROM session WHERE email = 'm.muster@example.org'").fetchone()[0]
        alive = {auth._hash(t) for t in tokens} & {r[0] for r in con.execute("SELECT token_hash FROM session")}
    assert left == auth.MAX_SESSIONS_PER_USER
    assert auth._hash(tokens[-1]) in alive and auth._hash(tokens[0]) not in alive    # die ältesten fallen weg


# ---------------------------------------------------------------- AVV und Abhängigkeiten
def test_avv_document_runs_only_its_own_script(make_client):
    make_tenant("wehr-a1")
    client = make_client()
    response = client.get("/api/dpa/vg-a/document")
    assert response.status_code == 200
    csp = response.headers["content-security-policy"]
    nonce = re.search(r"'nonce-([^']+)'", csp).group(1)
    assert "'unsafe-inline'" not in csp.split("script-src")[1].split(";")[0]
    assert f'<script nonce="{nonce}">' in response.text and "onclick" not in response.text
    assert "<script" in response.text and response.text.count("<script") == 1


def test_openpyxl_uses_defusedxml():
    from openpyxl.xml import DEFUSEDXML
    assert DEFUSEDXML is True


def test_pending_reports_are_capped_per_tenant(client, monkeypatch):
    tenant = tenancy.access_for(None).tenants["wehr-a1"]
    head = {"bks_report_id": "1", "bks_record_id": "1", "number_text": "1/25", "first_alarm": None,
            "keyword": "B", "subcode": "2", "reported_as": "x", "unit": "FW NR#.ABC 02", "unit_name": ""}
    monkeypatch.setattr(importing, "PENDING_MAX_REPORTS", 1)
    importing.forward(tenant, head, "a.pdf", b"%PDF-1", "m.muster@example.org")
    with pytest.raises(ValueError, match="schon viele"):
        importing.forward(tenant, {**head, "bks_report_id": "2"}, "b.pdf", b"%PDF-2", "m.muster@example.org")


def test_idle_session_expires(data_dir):
    import time
    from types import SimpleNamespace
    make_tenant("wehr-a1")
    grant("m.muster@example.org", "viewer", 1)
    token = auth.create_session("m.muster@example.org")
    request = SimpleNamespace(cookies={auth.COOKIE: token}, state=SimpleNamespace())
    assert auth._lookup_session(request)
    with tenancy.central() as con:
        con.execute("UPDATE session SET last_seen = ?", (time.time() - auth.SESSION_IDLE - 10,))
    assert auth._lookup_session(request) is None


def test_total_mail_volume_does_not_block_other_addresses(monkeypatch, data_dir):
    monkeypatch.setattr(tenancy, "ADMIN_EMAILS", {"a@example.org", "b@example.org"})
    monkeypatch.setattr(auth, "_key", None)
    monkeypatch.setattr(auth, "_last_mail", {})
    monkeypatch.setattr(auth, "_sent", [(time.time(), f"x{i}@example.org") for i in range(300)])
    monkeypatch.setattr(mail, "SMTP_HOST", "smtp.example.org")
    sent = []
    monkeypatch.setattr(mail, "send", lambda *args, **kwargs: sent.append(args[0]))
    monkeypatch.setattr(auth, "BASE_URL", "https://einsatz.example.org")
    auth.send_link("b@example.org")
    assert sent == ["b@example.org"]


def test_internal_parser_errors_are_not_shown(monkeypatch):
    from app import parser_worker

    class Conn:
        sent = None
        def send_bytes(self, data): Conn.sent = data
        def close(self): pass

    def boom(kind, path): raise RuntimeError("/srv/app/intern.py kaputt")
    monkeypatch.setattr(parser_worker, "read_local", boom)
    parser_worker._child(Conn(), "pdf", "x")
    assert b"intern" not in Conn.sent and parser_worker.GENERIC_ERROR.encode()[:10] in Conn.sent


def test_kept_uploads_need_flag_and_expire(monkeypatch, tmp_path):
    import os
    from app import importing
    monkeypatch.setattr(db, "DATA_DIR", str(tmp_path))
    source = tmp_path / "b.pdf"
    source.write_bytes(b"x")
    importing.keep_for_debug([("b.pdf", str(source))])
    assert not (tmp_path / "debug-reports").exists()
    monkeypatch.setenv("KEEP_UPLOADS", "1")
    folder = tmp_path / "debug-reports"
    folder.mkdir()
    old = folder / "alt.pdf"
    old.write_bytes(b"x")
    os.utime(old, (1, 1))
    importing.keep_for_debug([("b.pdf", str(source))])
    assert not old.exists() and len(list(folder.iterdir())) == 1


@pytest.mark.parametrize("site, status", [("cross-site", 403), ("same-site", 403), ("same-origin", 200), ("none", 200)])
def test_browser_writes_from_other_sites_are_refused(client, site, status):
    response = client.post("/api/scope", json={"key": "nope"}, headers={"Sec-Fetch-Site": site})
    # /api/scope antwortet für einen unbekannten Schlüssel selbst mit 403; entscheidend ist die Meldung der Sperre
    assert ("abgewiesen" in response.json()["detail"]) == (status == 403)
    # lesende Anfragen bleiben unberührt
    assert client.get("/health", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 200


def test_code_failures_are_only_recorded_for_real_addresses(monkeypatch, data_dir):
    monkeypatch.setattr(tenancy, "ADMIN_EMAILS", {"admin@example.org"})
    assert auth._use_code("erfunden@example.org", "12345678") is None
    assert auth._use_code("admin@example.org", "12345678") is None
    with tenancy.central() as con:
        rows = [r[0] for r in con.execute("SELECT email FROM login_failure")]
    assert rows == ["admin@example.org"]
