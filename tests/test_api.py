# -*- coding: utf-8 -*-
import io
import zipfile

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


def test_frontend_is_revalidated(client):
    assert client.get("/").headers["cache-control"] == "no-cache"
    response = client.get("/static/app.js")
    assert response.headers["cache-control"] == "no-cache"
    assert client.get("/static/app.js", headers={"if-none-match": response.headers["etag"]}).status_code == 304
    assert "cache-control" not in client.get("/health").headers


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


def _zip(entries):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return data.getvalue()


def test_zip_upload_unpacks_pdfs(client, monkeypatch):
    read = []
    def fake_read_pdf(path, filename):
        read.append(filename)
        raise ValueError("kein Bericht")
    monkeypatch.setattr(main.report, "read_pdf", fake_read_pdf)
    archive = _zip({"a/01-25.pdf": b"x", "b/01-25.pdf": b"x", "liesmich.txt": b"x",
                    "__MACOSX/a/._01-25.pdf": b"x", "02-25.PDF": b"x"})
    response = client.post("/api/reports", files=[("pdfs", ("berichte.zip", archive, "application/zip")),
                                                  ("pdfs", ("03-25.pdf", b"x", "application/pdf"))])
    assert response.status_code == 200
    assert read == ["01-25.pdf", "01-25 (2).pdf", "02-25.PDF", "03-25.pdf"]
    assert [e["file"] for e in response.json()["errors"]] == read


def test_zip_upload_errors(client):
    response = client.post("/api/reports", files=[("pdfs", ("kaputt.zip", b"kein zip", "application/zip")),
                                                  ("pdfs", ("leer.zip", _zip({"a.txt": b"x"}), "application/zip"))])
    assert [e["file"] for e in response.json()["errors"]] == ["kaputt.zip", "leer.zip"]
    assert client.post("/api/reports", files=[("pdfs", ("a.txt", b"x", "text/plain"))]).status_code == 400


def test_export(client):
    _create(client, 1)
    response = client.get("/api/export?year=2025")
    assert response.status_code == 200
    assert client.get("/api/export?year=2020").status_code == 404
