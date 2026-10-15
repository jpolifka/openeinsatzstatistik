# -*- coding: utf-8 -*-
"""Fehlerwege der API: unbekannte Einsätze, Export ohne Daten, Übernahme-Konflikte, Weitergabe, AVV."""
import pytest

from app import db, report, store, tenancy
from conftest import CFG, grant, login, make_tenant
from test_admin import world as admin_world  # noqa: F401
from test_api import _create, client  # noqa: F401  (Fixture client mit Wehr wehr-a1)
from test_dpa import PDF, _as, _fill, pending  # noqa: F401  (Fixture pending)
from test_xlsx_report import make_workbook

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# ---------------------------------------------------------------- Einsätze
def test_unknown_or_malformed_incident_keys_are_not_found(client):
    assert client.put("/api/incidents/kaputt", json={"revision": 0}).status_code == 404
    assert client.put("/api/incidents/wehr-a1:9999", json={"revision": 0}).status_code == 404
    assert client.delete("/api/incidents/wehr-a1:9999?revision=0").status_code == 404


def test_delete_losing_race_reports_conflict(client, monkeypatch):
    key = _create(client, 1)

    def stale(*args, **kwargs):
        raise store.StaleIncident("inzwischen geändert")

    monkeypatch.setattr(store, "delete_incident", stale)
    assert client.delete(f"/api/incidents/{key}?revision=0").status_code == 409


# ---------------------------------------------------------------- Export und Kosten
def test_overview_export_without_incidents_is_not_found(make_client):
    make_tenant("wehr-a1", "vg-a")
    make_tenant("wehr-a2", "vg-a", name="Wehr A2")
    c = make_client()
    c.cookies.set("scope", "vg:vg-a")
    assert c.get("/api/export?year=2025").status_code == 404


def test_overview_summary_notes_when_all_incidents_have_dispatch_numbers(make_client):
    make_tenant("wehr-a1", "vg-a")
    make_tenant("wehr-a2", "vg-a", name="Wehr A2")
    for slug in ("wehr-a1", "wehr-a2"):
        with db.connection(tenancy.tenant_path(slug)) as con:
            store.create_incident(con, {"number": 1, "started_at": "2025-03-12T10:00:00", "keyword": "B2",
                                        "dispatch_number": "1250000001"}, source="pdf")
    c = make_client()
    c.cookies.set("scope", "vg:vg-a")
    assert c.get("/api/export/summary?year=2025").status_code == 200
    assert c.get("/api/export?year=2025").status_code == 200


def test_fee_request_rejects_vat_out_of_range(make_client):
    vg_id, _ = make_tenant("wehr-a1", "vg-a")
    c = make_client()
    c.cookies.set("scope", "vg:vg-a")
    assert c.post("/api/records/9000001/fees", json={"vat_percent": 150}).status_code == 422
    assert c.post("/api/records/9000001/fees", json={"vat_percent": -1}).status_code == 422


# ---------------------------------------------------------------- Übernahme und Weitergabe
def _preview(client, name="17-25.xlsx"):
    return client.post("/api/reports", files=[("pdfs", (name, make_workbook(), XLSX))]).json()


def test_accepting_report_with_taken_number_conflicts(client):
    first = _preview(client)
    assert client.post("/api/reports/accept", json={"token": first["token"], "filename": "17-25.xlsx",
                                                    "fields": {}}).status_code == 200
    second = _preview(client)
    duplicate = client.post("/api/reports/accept", json={"token": second["token"], "filename": "17-25.xlsx",
                                                         "fields": {}})
    assert duplicate.status_code == 409
    assert len(client.get("/api/incidents?year=2025").json()["incidents"]) == 1


def test_accepting_with_concurrent_change_conflicts(client, monkeypatch):
    preview = _preview(client)
    original = report.save

    def stale(*args, **kwargs):
        raise store.StaleIncident("inzwischen geändert")

    monkeypatch.setattr(report, "save", stale)
    response = client.post("/api/reports/accept", json={"token": preview["token"], "filename": "17-25.xlsx",
                                                        "fields": {}})
    assert response.status_code == 409
    # die Vorschau liegt wieder bereit
    monkeypatch.setattr(report, "save", original)
    assert client.post("/api/reports/accept", json={"token": preview["token"], "filename": "17-25.xlsx",
                                                    "fields": {}}).status_code == 200


def test_pending_reports_can_be_listed_read_and_discarded(client):
    tenant = tenancy.access_for(None, "t:wehr-a1").selected
    head = {"bks_report_id": "9000009", "bks_record_id": "9000000", "number_text": "9/25", "keyword": "B",
            "subcode": "2", "reported_as": "Brand"}
    with tenant.connection() as con:
        pending_id = store.add_pending(con, head, "9-25.xlsx", make_workbook(), "a@example.org")
    listed = client.get("/api/pending").json()
    assert [r["filename"] for r in listed["reports"]] == ["9-25.xlsx"] and listed["postprocessing"] == []
    read = client.post("/api/pending/read", json={"ids": [f"wehr-a1:{pending_id}", f"wehr-a1:{pending_id + 50}"]}).json()
    assert [r["filename"] for r in read["reports"]] == ["9-25.xlsx"]
    assert read["errors"] == [{"file": f"wehr-a1:{pending_id + 50}", "message": "Der Bericht liegt nicht mehr bereit."}]
    assert client.delete(f"/api/pending/wehr-a1:{pending_id}").json() == {"ok": True}
    assert client.get("/api/pending").json()["reports"] == []


def test_closing_unknown_notice_is_not_found(client):
    assert client.post("/api/notices/9999/done").status_code == 404


# ---------------------------------------------------------------- AVV
def test_dpa_rejects_oversized_upload_unknown_status_and_unprepared_signature(pending, data_dir, monkeypatch):
    from app import dpa
    monkeypatch.setattr(dpa, "MAX_PDF_BYTES", 10)
    assert pending.post("/api/dpa/vg-neu/upload", files={"file": ("avv.pdf", PDF + b"x" * 20)}).status_code == 422
    _fill(pending)
    assert pending.get("/api/dpa/vg-neu/file").status_code == 404           # noch kein Vertrag hochgeladen
    _as(pending, "admin@example.org")
    assert pending.post("/api/dpa/vg-neu/status", json={"status": "gibt-es-nicht"}).status_code == 422
    with tenancy.central() as con:
        con.execute("UPDATE dpa SET generated_hash = NULL")
    assert pending.post("/api/dpa/vg-neu/status", json={"status": "signed", "signed_on": "2026-10-01"}).status_code == 422
