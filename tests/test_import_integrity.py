# -*- coding: utf-8 -*-
"""Datenerhalt beim Bearbeiten und Einlesen: konkurrierende Schreiber, Wiederholung der Nachverarbeitung,
Aktualisierung eines erfassten Einsatzes."""
import pytest

from app import db, import_queue, importing, records, store, tenancy
from conftest import make_tenant
from test_xlsx_report import make_workbook

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@pytest.fixture
def client(make_client):
    make_tenant("wehr-a1")
    return make_client()


def _upload_and_accept(client, replace=False, revision=None):
    data = client.post("/api/reports", files=[("pdfs", ("17-25.xlsx", make_workbook(), XLSX))]).json()
    body = {"token": data["token"], "filename": "17-25.xlsx", "fields": {}}
    if replace:
        body.update(replace=True, revision=revision)
    return client.post("/api/reports/accept", json=body)


def _tenant():
    return tenancy.access_for(None).tenant("wehr-a1", "reports.import")


def _incident(client):
    saved = _upload_and_accept(client)
    assert saved.status_code == 200, saved.text
    return saved.json()


# ---------------------------------------------------------------- 1. konkurrierende Schreiber
def test_second_writer_with_stale_revision_cannot_overwrite(client):
    saved = _incident(client)
    key, revision = saved["id"], saved["revision"]
    first = client.put(f"/api/incidents/{key}", json={"revision": revision, "description": "Stand von A"})
    assert first.status_code == 200 and first.json()["revision"] == revision + 1
    second = client.put(f"/api/incidents/{key}", json={"revision": revision, "description": "Stand von B"})
    assert second.status_code == 409
    stored = client.get("/api/incidents?year=2025").json()["incidents"][0]
    assert (stored["description"], stored["revision"]) == ("Stand von A", revision + 1)


def test_stale_delete_keeps_incident_and_current_revision_deletes(client):
    saved = _incident(client)
    key, revision = saved["id"], saved["revision"]
    client.put(f"/api/incidents/{key}", json={"revision": revision, "description": "Geändert"})
    assert client.delete(f"/api/incidents/{key}?revision={revision}").status_code == 409
    assert len(client.get("/api/incidents?year=2025").json()["incidents"]) == 1
    assert client.delete(f"/api/incidents/{key}?revision={revision + 1}").status_code == 200
    assert client.get("/api/incidents?year=2025").json()["incidents"] == []


def test_failed_update_leaves_vehicles_and_people_unchanged(client):
    """Veraltete Revision: weder Felder noch Fahrzeuge oder Anwesenheit werden angefasst."""
    saved = _incident(client)
    before = client.get("/api/incidents?year=2025").json()["incidents"][0]
    response = client.put(f"/api/incidents/{saved['id']}", json={
        "revision": before["revision"] + 5, "description": "X", "vehicles": [], "people": []})
    assert response.status_code == 409
    after = client.get("/api/incidents?year=2025").json()["incidents"][0]
    assert after["people"] == before["people"] and after["vehicles"] == before["vehicles"]
    assert after["description"] == before["description"]


# ---------------------------------------------------------------- 5. Nachverarbeitung (Outbox)
def test_partial_postprocessing_failure_is_repeated_without_duplicates(client, monkeypatch):
    original = records.notify_others
    calls = []

    def flaky(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("Zentrale nach dem Vermerk nicht erreichbar")
        return original(*args, **kwargs)

    monkeypatch.setattr(records, "notify_others", flaky)
    result = _upload_and_accept(client)
    assert result.status_code == 200 and result.json()["postprocessing_pending"] is True
    tenant = _tenant()
    with tenant.connection() as con:
        assert con.execute("SELECT COUNT(*) FROM import_job").fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM incident").fetchone()[0] == 1
    import_queue.retry(tenant, importing.after_import)
    import_queue.retry(tenant, importing.after_import)       # weitere Läufe finden nichts mehr
    with tenant.connection() as con:
        assert con.execute("SELECT COUNT(*) FROM import_job").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM incident").fetchone()[0] == 1
    with tenancy.central() as con:
        assert con.execute("SELECT COUNT(*) FROM record_report WHERE bks_report_id = '9000001'").fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM completed_import").fetchone()[0] == 1
    assert len(calls) == 2


def test_completed_job_is_not_processed_twice_when_row_survives(client):
    """Absturz nach dem zentralen Vermerk, aber vor dem Löschen des Auftrags: der erneute Lauf wirkt nicht mehr
    (der leere Bericht würde sonst am Pflichtfeld scheitern) und entfernt den Auftrag."""
    assert _upload_and_accept(client).status_code == 200
    tenant = _tenant()
    with tenant.connection() as con:
        incident_id = con.execute("SELECT id FROM incident").fetchone()[0]
        con.execute("INSERT INTO import_job (id, incident_id, report, email, is_member, updated) "
                    "VALUES ('wiederholt', ?, '{}', NULL, 1, 0)", (incident_id,))
    with tenancy.central() as con:
        con.execute("INSERT INTO completed_import (id) VALUES ('wiederholt')")
        before = con.execute("SELECT COUNT(*) FROM record_report").fetchone()[0]
    assert import_queue.process(tenant, "wiederholt", importing.after_import) is True
    with tenant.connection() as con:
        assert con.execute("SELECT COUNT(*) FROM import_job").fetchone()[0] == 0
    with tenancy.central() as con:
        assert con.execute("SELECT COUNT(*) FROM record_report").fetchone()[0] == before


# ---------------------------------------------------------------- 6. Aktualisierung eines erfassten Einsatzes
def _attendance(incident_key):
    """(Name, manuell) je Anwesenheitszeile – das Flag steht nur in der Datenbank."""
    incident_id = int(incident_key.split(":")[1])
    with db.connection(tenancy.tenant_path("wehr-a1")) as con:
        return sorted((f"{r['last_name']}, {r['first_name']}", r["manual"]) for r in con.execute(
            "SELECT m.last_name, m.first_name, a.manual FROM attendance a JOIN member m ON m.id = a.member_id "
            "WHERE a.incident_id = ?", (incident_id,)))


def test_replace_keeps_id_and_manual_rows_and_replaces_report_rows(client):
    saved = _incident(client)
    key, revision = saved["id"], saved["revision"]
    imported = _attendance(key)
    assert imported and all(manual == 0 for _, manual in imported)
    people = [{"id": p["id"], "role": p.get("role"), "vehicle": p.get("vehicle")} for p in saved["people"]]
    people.append({"name": "Beispiel, Anna", "role": "Helfer"})
    edited = client.put(f"/api/incidents/{key}", json={"revision": revision, "people": people})
    assert edited.status_code == 200, edited.text
    assert dict(_attendance(key))["Beispiel, Anna"] == 1
    # Dieselbe Datei erneut einlesen und als Aktualisierung übernehmen
    again = _upload_and_accept(client, replace=True, revision=edited.json()["revision"])
    assert again.status_code == 200, again.text
    assert again.json()["id"] == key and again.json()["revision"] > edited.json()["revision"]
    after = _attendance(key)
    assert dict(after)["Beispiel, Anna"] == 1                       # Handeintrag bleibt
    assert [n for n, m in after if m == 0] == [n for n, _ in imported]   # Berichtszeilen ersetzt, nicht verdoppelt
    assert len(client.get("/api/incidents?year=2025").json()["incidents"]) == 1
