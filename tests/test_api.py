# -*- coding: utf-8 -*-
import pytest
from fastapi.testclient import TestClient

from app import db, domain, main, store


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(main, "IMPORT_DIR", str(tmp_path / "kein-import"))
    with TestClient(main.app) as c:
        yield c


def _create(client, number, started_at="2025-03-12T10:00:00"):
    with db.connection() as con:
        return store.create_incident(con, {"number": number, "started_at": started_at, "keyword": "B2",
                                           "place": "Rheinbrohl"}, source="pdf")


def test_config_comes_from_domain(client):
    assert client.get("/api/config").json()["vehicles"] == list(domain.VEHICLES)


def test_evaluation_rejects_unknown_limit(client):
    assert client.get("/api/evaluation?limit=9").status_code == 400
    assert client.get("/api/evaluation?limit=10").json()["response_plan"]["limit"] == 10


def test_incidents_update_and_conflict(client):
    first, second = _create(client, 1), _create(client, 2)
    incidents = client.get("/api/incidents?year=2025").json()["incidents"]
    assert [i["number"] for i in incidents] == [1, 2]
    assert [v["call_sign"] for v in incidents[0]["vehicles"]] == list(domain.VEHICLES)

    changed = client.put(f"/api/incidents/{second}", json={"unit_leader": "E. Beispiel"}).json()
    assert changed["unit_leader"] == "E. Beispiel"
    assert client.put(f"/api/incidents/{second}", json={"number": 1}).status_code == 409
    assert client.put("/api/incidents/999", json={}).status_code == 404
    assert client.delete(f"/api/incidents/{first}").json() == {"ok": True}


def test_expired_preview(client):
    response = client.post("/api/reports/accept", json={"token": "x", "filename": "a.pdf", "fields": {}})
    assert response.status_code == 410


def test_export(client):
    _create(client, 1)
    response = client.get("/api/export?year=2025")
    assert response.status_code == 200
    assert client.get("/api/export?year=2020").status_code == 404
