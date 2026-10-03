# -*- coding: utf-8 -*-
"""Einsatznummern je Wehr (aus dem Bericht bzw. nach Datum) und Freigabe des Bedarfsplans."""
import dataclasses

import pytest

from app import db, main, store, tenancy
from conftest import CFG, grant, login, make_tenant
from test_report import FULL, LEFT


def _incident(con, number, start):
    return store.create_incident(con, {"number": number, "started_at": start, "keyword": "B1"}, source="pdf")


def test_renumber_by_date(con):
    late = _incident(con, 1, "2025-05-01T10:00:00")
    early = _incident(con, 2, "2025-03-01T10:00:00")
    _incident(con, 7, "2024-12-31T10:00:00")
    fire_watch = _incident(con, 3, "2025-04-01T10:00:00")      # später eingelesene BSW
    store.renumber(con, 2025)
    numbers = {r["id"]: r["number"] for r in con.execute("SELECT id, number FROM incident WHERE year = 2025")}
    assert numbers == {early: 1, fire_watch: 2, late: 3}
    assert store.next_number(con, 2025) == 4 and store.next_number(con, 2026) == 1
    assert con.execute("SELECT number FROM incident WHERE year = 2024").fetchone()[0] == 7


def _read(client, monkeypatch, text, name="bericht.pdf"):
    monkeypatch.setattr(main.pdf_report, "extract_text", lambda path: (text, LEFT if "17/25" in text else "", ""))
    return client.post("/api/reports", files=[("pdfs", (name, b"x", "application/pdf"))]).json()


def _accept(client, data, **fields):
    return client.post("/api/reports/accept", json={"token": data["token"], "filename": data["reports"][0]["filename"],
                                                     "fields": fields}).json()


def test_missing_number_gets_next_free(make_client, monkeypatch):
    make_tenant("wehr-a1")
    client = make_client()
    with db.connection(tenancy.tenant_path("wehr-a1")) as con:
        _incident(con, 16, "2025-01-01T10:00:00")
    without = FULL.replace("Einsatzbericht-Nr.: 17/25\n", "")
    saved = _accept(client, _read(client, monkeypatch, without))
    assert saved["number"] == 17
    assert any("nächste freie Nr. 17" in w for w in saved["warnings"])


def test_numbering_by_date(make_client, monkeypatch):
    make_tenant("wehr-a1", cfg=dataclasses.replace(CFG, numbering="by_date"))
    client = make_client()
    with db.connection(tenancy.tenant_path("wehr-a1")) as con:
        later = _incident(con, 1, "2025-06-01T10:00:00")
    data = _read(client, monkeypatch, FULL)                     # 12.03.2025, Nr. 17 im Bericht
    assert "Einsatzbericht-Nr. nicht erkannt" not in data["reports"][0]["warnings"]
    saved = _accept(client, data, number=99)
    assert saved["number"] == 1                                  # vor dem Einsatz vom Juni
    incidents = {i["id"]: i["number"] for i in client.get("/api/incidents?year=2025").json()["incidents"]}
    assert incidents[f"wehr-a1:{later}"] == 2
    # Bearbeiten ändert die Nr. nicht, ein neuer Beginn verschiebt den Einsatz
    edited = client.put(f"/api/incidents/{saved['id']}", json={"number": 5, "started_at": "2025-07-01T10:00"}).json()
    assert edited["number"] == 2
    client.delete(f"/api/incidents/wehr-a1:{later}")
    assert [i["number"] for i in client.get("/api/incidents?year=2025").json()["incidents"]] == [1]


def test_by_date_moves_incident_to_other_year_and_preview_ignores_report_number(make_client, monkeypatch):
    make_tenant("wehr-a1", cfg=dataclasses.replace(CFG, numbering="by_date"))
    client = make_client()
    with db.connection(tenancy.tenant_path("wehr-a1")) as con:
        first = _incident(con, 1, "2025-02-01T10:00:00")
        _incident(con, 1, "2026-03-01T10:00:00")
        for n in range(2, 18):                                   # Nr. 17/2025 gibt es, gehört aber zu einem anderen Einsatz
            _incident(con, n, f"2025-02-{n:02d}T12:00:00")
    data = _read(client, monkeypatch, FULL)                     # Bericht Nr. 17/25
    assert data["reports"][0]["existing"] is None
    moved = client.put(f"/api/incidents/wehr-a1:{first}", json={"started_at": "2026-02-01T10:00"})
    assert moved.status_code == 200 and (moved.json()["year"], moved.json()["number"]) == (2026, 1)
    assert sorted(i["number"] for i in client.get("/api/incidents?year=2025").json()["incidents"]) == list(range(1, 17))


@pytest.fixture
def roles(make_client):
    _, tenant_id = make_tenant("wehr-a1")
    grant("lead@example.org", "lead", tenant_id)
    grant("viewer@example.org", "viewer", tenant_id)
    with db.connection(tenancy.tenant_path("wehr-a1")) as con:
        _incident(con, 1, "2025-03-12T10:00:00")
    return make_client(login=True)


def test_response_plan_needs_release(roles):
    viewer = login(roles, "viewer@example.org")
    data = viewer.get("/api/evaluation?year=2025").json()
    assert data["response_plan"] is None and data["response_plan_public"] is False
    assert viewer.put("/api/admin/wehr-a1/response-plan", json={"public": True}).status_code == 403
    lead = login(roles, "lead@example.org")
    assert lead.get("/api/evaluation?year=2025").json()["response_plan"] is not None
    assert lead.put("/api/admin/wehr-a1/response-plan", json={"public": True}).status_code == 200
    viewer = login(roles, "viewer@example.org")
    data = viewer.get("/api/evaluation?year=2025").json()
    assert data["response_plan"] is not None and data["response_plan_public"] is True
    assert viewer.get("/api/config").json()["response_plan_public"] is True
