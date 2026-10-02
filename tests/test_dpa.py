# -*- coding: utf-8 -*-
"""AVV je VG: Sperre bis zur Freigabe, Formular, Dokument, Ablage und Bestätigung."""
import os
import sqlite3

import pytest

from app import db, dpa, tenancy
from conftest import grant, login, make_tenant

PDF = b"%PDF-1.4\n% unterschrieben\n"


@pytest.fixture
def pending(make_client):
    vg_id, tenant_id = make_tenant("wehr-n1", "vg-neu", dpa=None)
    grant("lead@example.org", "lead", tenant_id)
    grant("editor@example.org", "editor", tenant_id)
    client = make_client(login=True)
    return login(client, "lead@example.org")


def _as(client, email):
    client.cookies.clear()
    return login(client, email)


def _fill(client):
    return client.put("/api/dpa/vg-neu", json={"client_data": {
        "client_name": "Verbandsgemeinde Musterstadt <script>alert(1)</script>", "client_address": "Musterweg 1",
        "client_representative": "M. Muster", "client_dpo": "E. Beispiel", "client_contact": "x@example.org"}})


def test_tenant_is_locked_until_dpa(pending):
    config = pending.get("/api/config").json()
    assert config["tenants"] == [] and config["dpa_blocked"] == [{"slug": "vg-neu", "name": "VG vg-neu"}]
    assert pending.get("/api/years").status_code == 403
    assert pending.get("/api/incidents").status_code == 403
    assert pending.get("/api/admin/wehr-n1/settings").status_code == 403
    items = pending.get("/api/dpa").json()["items"]
    assert [(i["slug"], i["status"], i["can_edit"]) for i in items] == [("vg-neu", "pending", True)]
    assert _as(pending, "editor@example.org").get("/api/dpa").json()["items"][0]["can_edit"] is False
    assert _fill(pending).status_code == 403
    # Superadmin ist nicht gesperrt
    assert _as(pending, "admin@example.org").get("/api/admin/wehr-n1/settings").status_code == 200


def test_form_document_upload_and_confirmation(pending, data_dir):
    assert pending.put("/api/dpa/vg-neu", json={"client_data": {"client_name": ""}}).status_code == 422
    filled = _fill(pending).json()
    assert filled["status"] == "draft" and len(filled["generated_hash"]) == 64
    page = pending.get("/api/dpa/vg-neu/document").text
    assert "&lt;script&gt;" in page and "<script>alert" not in page
    assert filled["generated_hash"] in page and "Wehr wehr-n1" in page
    assert "Polifka IT Beratung" in page and dpa.MISSING in page         # Angaben zum Auftragnehmer fehlen im Test

    # Bestätigen geht nur mit unterschriebenem Vertrag und nur für den Superadmin
    _as(pending, "admin@example.org")
    assert pending.post("/api/dpa/vg-neu/status", json={"status": "signed", "signed_on": "2026-10-01"}).status_code == 422
    _as(pending, "lead@example.org")
    assert pending.post("/api/dpa/vg-neu/upload", files={"file": ("avv.pdf", b"kein pdf")}).status_code == 422
    first = pending.post("/api/dpa/vg-neu/upload", files={"file": ("avv.pdf", PDF)}).json()
    second = pending.post("/api/dpa/vg-neu/upload", files={"file": ("avv.pdf", PDF + b"2")}).json()
    assert first["document_hash"] != second["document_hash"]
    assert len(os.listdir(data_dir / "avv" / "vg-neu")) == 2                # nichts überschrieben
    assert pending.put("/api/dpa/vg-neu/link", json={"link": "javascript:alert(1)"}).status_code == 422
    assert pending.put("/api/dpa/vg-neu/link", json={"link": "https://dms.example.org/avv/42"}).json()["document_link"]
    assert pending.get("/api/dpa/vg-neu/file").content == PDF + b"2"
    assert pending.post("/api/dpa/vg-neu/status", json={"status": "signed", "signed_on": "2026-10-01"}).status_code == 403

    _as(pending, "admin@example.org")
    assert pending.post("/api/dpa/vg-neu/status", json={"status": "signed"}).status_code == 422   # Datum fehlt
    signed = pending.post("/api/dpa/vg-neu/status", json={"status": "signed", "signed_on": "2026-10-01"}).json()
    assert signed["status"] == "signed" and signed["confirmed_by"] == "admin@example.org"
    assert [e["action"] for e in signed["events"]][0] == "Status: AVV liegt vor"

    _as(pending, "lead@example.org")
    assert pending.get("/api/years").status_code == 200
    assert _fill(pending).status_code == 409                                 # abgeschlossen
    _as(pending, "admin@example.org").post("/api/dpa/vg-neu/status", json={"status": "revoked", "note": "Kündigung"})
    assert _as(pending, "lead@example.org").get("/api/years").status_code == 403


def test_event_log_is_append_only(pending):
    _fill(pending)
    with pytest.raises(sqlite3.DatabaseError, match="nur ergänzt"):
        with tenancy.central() as con:
            con.execute("UPDATE dpa_event SET action = 'gefälscht'")
    with pytest.raises(sqlite3.DatabaseError):
        with tenancy.central() as con:
            con.execute("DELETE FROM dpa_event")


def test_other_vg_cannot_see_contract(pending):
    _, other = make_tenant("wehr-x1", "vg-x")
    grant("fremd@example.org", "lead", other)
    _as(pending, "fremd@example.org")
    assert [i["slug"] for i in pending.get("/api/dpa").json()["items"]] == ["vg-x"]
    assert pending.get("/api/dpa/vg-neu/document").status_code == 403
    assert _fill(pending).status_code == 403


def test_existing_central_db_marks_legacy_vg_not_required(tmp_path):
    con = db.connect(str(tmp_path / "app.db"))
    db.migrate(con, db.CENTRAL_MIGRATIONS[:1])
    con.execute("INSERT INTO vg (slug, name) VALUES ('bad-hoenningen', 'VG Bad Hönningen'), ('vg-b', 'VG B')")
    con.commit()
    db.migrate(con, db.CENTRAL_MIGRATIONS)
    assert dict(con.execute("SELECT v.slug, d.status FROM vg v LEFT JOIN dpa d ON d.vg_id = v.id").fetchall()) == \
        {"bad-hoenningen": "not_required", "vg-b": None}
    con.close()


def test_document_warns_when_text_changed_after_generation(pending, monkeypatch):
    _fill(pending)
    assert "weicht vom erzeugten Vertrag ab" not in pending.get("/api/dpa/vg-neu/document").text
    monkeypatch.setenv("DPA_PROCESSOR_ADDRESS", "Musterweg 2, 12345 Musterstadt")
    page = pending.get("/api/dpa/vg-neu/document").text
    assert "Musterweg 2" in page and "weicht vom erzeugten Vertrag ab" in page
