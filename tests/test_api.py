# -*- coding: utf-8 -*-
from app import pdf_report
import io
import zipfile

import pytest

from app import db, importing, main, store, tenancy
from app.api import common as api_common
from conftest import CFG, make_tenant
from test_xlsx_report import make_workbook


@pytest.fixture
def client(make_client):
    make_tenant("wehr-a1")
    return make_client()


def _create(client, number, started_at="2025-03-12T10:00:00"):
    with db.connection(tenancy.tenant_path("wehr-a1")) as con:
        incident_id = store.create_incident(con, {"number": number, "started_at": started_at, "keyword": "B2",
                                                  "place": "Altenau"}, source="pdf")
    return f"wehr-a1:{incident_id}"


def test_frontend_is_revalidated(client):
    assert client.get("/").headers["cache-control"] == "no-cache"
    response = client.get("/static/app.js")
    assert response.headers["cache-control"] == "no-cache"
    assert client.get("/static/app.js", headers={"if-none-match": response.headers["etag"]}).status_code == 304
    assert "cache-control" not in client.get("/health").headers


def test_config_comes_from_tenant_config(client):
    assert client.get("/api/config").json()["vehicles"] == list(CFG.vehicles)


def test_evaluation_contains_history(client):
    _create(client, 1, "2024-05-02T10:00:00")
    _create(client, 1, "2025-03-12T10:00:00")
    history = client.get("/api/evaluation?year=2025").json()["history"]
    assert (history[0]["year"], history[0]["month"]) == (2024, 5)
    assert sum(h["count"] for h in history) == 2


def test_evaluation_contains_report_detail_blocks(client):
    key = _create(client, 1)
    with db.connection(tenancy.tenant_path("wehr-a1")) as con:
        incident_id = int(key.split(":")[1])
        con.execute("UPDATE incident SET abort_reason = 'Täuschungsalarm', alarm_system = '301986', building = 'WH Beispiel', "
                    "subcode = '07', rescued = 2, deceased = 0 WHERE id = ?", (incident_id,))
        store.add_vehicle(con, incident_id, "02/45", None, 6, "10:03:00", "10:08:00", alerted="10:00:00", finished="10:40:00",
                          deployed=0, respiratory=2)
        member = store.MemberDirectory(con).find_or_create("Muster", "Erika")
        store.add_attendance(con, incident_id, member, "Maschinist", "02/45", agt=1, agt_min=12)
    e = client.get("/api/evaluation?year=2025").json()
    assert e["aborts"]["aborted"] == 1 and e["aborts"]["kinds"][0]["count"] == 1
    assert e["alarm_systems"]["rows"][0]["system"] == "301986"
    assert e["alarm_systems"]["rows"][0]["false_alarms"] == 1
    usage = e["vehicle_usage"]["rows"][0]
    assert (usage["call_sign"], usage["standby"], usage["hours"]) == ("02/45", 1, 0.7)
    assert (e["respiratory"]["carriers"], e["respiratory"]["minutes"]) == (2, 12)
    assert e["casualties"]["fields"]["rescued"] == {"total": 2, "incidents": 1, "reported": 1}
    assert e["fire_course"]["total"] == 0
    assert e["attendance"]["functions"] == [{"role": "Maschinist", "count": 1, "people": 1}]
    listed = client.get("/api/incidents?year=2025").json()["incidents"][0]
    assert (listed["building"], listed["rescued"], listed["deceased"]) == ("WH Beispiel", 2, 0)
    assert listed["people"][0]["agt_min"] == 12 and listed["vehicles"][0]["deployed"] == 0


def test_report_details_can_be_edited(client):
    key = _create(client, 1)
    revision = client.get("/api/incidents?year=2025").json()["incidents"][0]["revision"]
    changed = client.put(f"/api/incidents/{key}", json={"revision": revision, "building": " WH Beispiel ", "rescued": 3,
                                                       "fire_out_at": "2025-03-12T10:45", "tactic": "Innenangriff"})
    assert changed.status_code == 200
    body = changed.json()
    assert (body["building"], body["rescued"], body["fire_out_at"], body["tactic"]) == ("WH Beispiel", 3, "2025-03-12T10:45:00", "Innenangriff")
    bad = client.put(f"/api/incidents/{key}", json={"revision": body["revision"], "injured": -1})
    assert bad.status_code == 422
    cleared = client.put(f"/api/incidents/{key}", json={"revision": body["revision"], "rescued": None, "building": ""})
    assert cleared.json()["rescued"] is None and cleared.json()["building"] is None


def test_evaluation_rejects_unknown_limit(client):
    assert client.get("/api/evaluation?limit=9").status_code == 400
    assert client.get("/api/evaluation?limit=10").json()["response_plan"]["limit"] == 10


def test_incidents_update_and_conflict(client):
    first, second = _create(client, 1), _create(client, 2)
    incidents = client.get("/api/incidents?year=2025").json()["incidents"]
    assert [i["number"] for i in incidents] == [1, 2]
    assert [v["call_sign"] for v in incidents[0]["vehicles"]] == list(CFG.vehicles)

    changed = client.put(f"/api/incidents/{second}", json={"revision": 0, "unit_leader": "E. Beispiel"}).json()
    assert changed["unit_leader"] == "E. Beispiel"
    assert client.put(f"/api/incidents/{second}", json={"revision": changed["revision"], "number": 1}).status_code == 409
    assert client.put("/api/incidents/wehr-a1:999", json={"revision": 0, }).status_code == 404
    assert client.delete(f"/api/incidents/{first}?revision=0").json() == {"ok": True}


def test_expired_preview(client):
    response = client.post("/api/reports/accept", json={"token": "x", "filename": "a.pdf", "fields": {}})
    assert response.status_code == 410


@pytest.mark.parametrize("changes", [{"started_at": None}, {"station_staff": -1},
    {"station_staff": True}, {"station_staff": 0.5},
    {"vehicles": [{"call_sign": "02/45", "crew": True}]},
    {"ended_at": "2025-03-12T09:00:00"}, {"vehicles": [{"call_sign": "02/45", "crew": -1}]}])
def test_invalid_incident_changes_are_rejected(client, changes):
    key = _create(client, 1)
    assert client.put(f"/api/incidents/{key}", json={"revision": 0, **changes}).status_code == 422
    incident = client.get("/api/incidents?year=2025").json()["incidents"][0]
    assert incident["started_at"] == "2025-03-12T10:00:00"
    assert incident["station_staff"] == 0


def test_stale_incident_revision_is_rejected(client):
    key = _create(client, 1)
    original = client.get("/api/incidents?year=2025").json()["incidents"][0]
    changed = client.put(f"/api/incidents/{key}", json={"revision": original["revision"],
                                                     "description": "Erste Änderung"})
    assert changed.status_code == 200
    assert changed.json()["revision"] == original["revision"] + 1
    stale = client.put(f"/api/incidents/{key}", json={"revision": original["revision"],
                                                   "description": "Veraltete Änderung"})
    assert stale.status_code == 409
    assert client.get("/api/incidents?year=2025").json()["incidents"][0]["description"] == "Erste Änderung"


def test_revision_is_required(client):
    key = _create(client, 1)
    assert client.put(f"/api/incidents/{key}", json={"description": "ohne Revision"}).status_code == 428
    assert client.delete(f"/api/incidents/{key}").status_code == 428
    assert client.put(f"/api/incidents/{key}", json={"revision": 0, "description": "geändert"}).status_code == 200
    assert client.delete(f"/api/incidents/{key}?revision=0").status_code == 409
    assert client.delete(f"/api/incidents/{key}?revision=1").status_code == 200


def test_cancelled_preview_cannot_be_accepted(client):
    data = client.post("/api/reports", files=[("pdfs", ("test.xlsx", make_workbook()))]).json()
    assert client.post("/api/reports/cancel", json={"token": data["token"]}).status_code == 200
    assert client.post("/api/reports/accept", json={"token": data["token"], "filename": "test.xlsx",
                                                   "fields": {}}).status_code == 410
    assert client.get("/api/incidents?year=2025").json()["incidents"] == []


def test_reports_read_in_background(client):
    """Viele Berichte: Upload antwortet sofort, Fortschritt und Ergebnis über den Job (kein Proxy-Timeout)."""
    import time
    files = [("pdfs", (f"test{i}.xlsx", make_workbook())) for i in range(3)]
    started = client.post("/api/reports?background=true", files=files)
    assert started.status_code == 202 and started.json()["total"] == 3
    job = started.json()["job"]
    for _ in range(100):
        status = client.get(f"/api/reports/jobs/{job}").json()
        if status["done"]:
            break
        assert 0 <= status["read"] <= 3
        time.sleep(0.05)
    assert status["read"] == 3 and [r["filename"] for r in status["reports"]] == ["test0.xlsx", "test1.xlsx", "test2.xlsx"]
    assert client.get(f"/api/reports/jobs/{job}").status_code == 404          # abgeholt: nicht noch einmal
    body = {"token": status["token"], "filename": "test1.xlsx", "fields": {}}
    assert client.post("/api/reports/accept", json=body).status_code == 200


def test_import_revision_conflict_keeps_preview(client):
    upload = lambda: client.post("/api/reports", files=[("pdfs", ("test.xlsx", make_workbook()))]).json()
    data = upload()
    body = {"token": data["token"], "filename": "test.xlsx", "fields": {}}
    saved = client.post("/api/reports/accept", json=body).json()
    data = upload()
    assert client.put(f"/api/incidents/{saved['id']}", json={"revision": saved["revision"],
                                                          "description": "Inzwischen bearbeitet"}).status_code == 200
    body.update(token=data["token"], replace=True)
    assert client.post("/api/reports/accept", json=body).status_code == 428
    body["revision"] = data["reports"][0]["existing"]["revision"]
    assert client.post("/api/reports/accept", json=body).status_code == 409
    assert api_common.previews.get(data["token"], "test.xlsx", None)[0]
    assert client.get("/api/incidents?year=2025").json()["incidents"][0]["description"] == "Inzwischen bearbeitet"


def test_saved_import_survives_postprocessing_failure(client, monkeypatch):
    from app import import_queue
    from test_report import FULL, LEFT
    monkeypatch.setattr(pdf_report, "extract_text", lambda _: (FULL, LEFT, ""))
    preview = client.post("/api/reports", files=[("pdfs", ("test.pdf", b"test", "application/pdf"))]).json()
    original = importing.after_import
    def fail(*args, **kwargs):
        raise RuntimeError("simulierter Ausfall der Zentrale")
    monkeypatch.setattr(importing, "after_import", fail)
    payload = {"token": preview["token"], "filename": "test.pdf", "fields": {}}
    result = client.post("/api/reports/accept", json=payload)
    assert result.status_code == 200
    assert result.json()["postprocessing_pending"] is True
    assert client.post("/api/reports/accept", json=payload).status_code == 410
    tenant = tenancy.access_for(None).tenant("wehr-a1", "reports.import")
    with tenant.connection() as con:
        job_id = con.execute("SELECT id FROM import_job").fetchone()[0]
        assert con.execute("SELECT COUNT(*) FROM incident").fetchone()[0] == 1
    assert import_queue.process(tenant, job_id, original) is True
    assert import_queue.process(tenant, job_id, original) is True
    with tenant.connection() as con:
        assert con.execute("SELECT COUNT(*) FROM import_job").fetchone()[0] == 0


def _zip(entries):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return data.getvalue()


def test_zip_upload_unpacks_pdfs(client, monkeypatch):
    read = []
    def fake_extract_text(path):
        read.append(path.rsplit("/", 1)[-1])
        raise ValueError("kein Bericht")
    monkeypatch.setattr(pdf_report, "extract_text", fake_extract_text)
    archive = _zip({"a/01-25.pdf": b"x", "b/01-25.pdf": b"x", "liesmich.txt": b"x",
                    "__MACOSX/a/._01-25.pdf": b"x", "02-25.PDF": b"x"})
    response = client.post("/api/reports", files=[("pdfs", ("berichte.zip", archive, "application/zip")),
                                                  ("pdfs", ("03-25.pdf", b"x", "application/pdf"))])
    assert response.status_code == 200
    expected = ["01-25.pdf", "01-25 (2).pdf", "02-25.PDF", "03-25.pdf"]
    assert sorted(read) == sorted(expected)                    # gelesen wird parallel, die Reihenfolge der Threads ist offen
    assert [e["file"] for e in response.json()["errors"]] == expected     # gemeldet in der Reihenfolge der Dateien


def test_xlsx_upload_preview_and_accept(client):
    """Excel-Export des BKS-Portals: einzeln und aus einer ZIP, Übernahme mit Quelle bks_xlsx."""
    workbook = make_workbook()
    xlsx = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    data = client.post("/api/reports", files=[("pdfs", ("17-25.xlsx", workbook, xlsx))]).json()
    assert data["errors"] == []
    preview = data["reports"][0]
    assert (preview["number"], preview["source"], preview["unit_leader"]) == (17, "bks_xlsx", "M. Muster")
    saved = client.post("/api/reports/accept", json={"token": data["token"], "filename": "17-25.xlsx",
                                                     "fields": {}}).json()
    assert (saved["source"], saved["filename"], len(saved["people"])) == ("bks_xlsx", "17-25.xlsx", 3)
    data = client.post("/api/reports", files=[("pdfs", ("b.zip", _zip({"x/17-25.xlsx": workbook}), "application/zip"))]
                       ).json()
    assert data["reports"][0]["existing"]["source"] == "bks_xlsx"
    assert data["reports"][0]["existing"]["differences"] == []


def test_zip_upload_errors(client):
    response = client.post("/api/reports", files=[("pdfs", ("kaputt.zip", b"kein zip", "application/zip")),
                                                  ("pdfs", ("leer.zip", _zip({"a.txt": b"x"}), "application/zip"))])
    assert [e["file"] for e in response.json()["errors"]] == ["kaputt.zip", "leer.zip"]
    assert client.post("/api/reports", files=[("pdfs", ("a.txt", b"x", "text/plain"))]).status_code == 400


def test_upload_size_is_limited(client, monkeypatch):
    """Upload und entpackte ZIP-Inhalte zusammen begrenzt; je Eintrag wird nur bis zur Grenze entpackt."""
    read = []
    monkeypatch.setattr(pdf_report, "extract_text", lambda path: read.append(path) or (_ for _ in ()).throw(
        ValueError("kein Bericht")))
    monkeypatch.setattr(importing, "UPLOAD_MAX_BYTES", 2500)
    archive = _zip({f"{n}.pdf": b"0" * 1000 for n in range(5)})          # stark komprimierbar
    data = client.post("/api/reports", files=[("pdfs", ("b.zip", archive, "application/zip"))]).json()
    assert len(archive) < 1000 and 1 <= len(read) < 5 and any("Zu groß" in e["message"] for e in data["errors"])
    big = client.post("/api/reports", files=[("pdfs", ("a.pdf", b"0" * 3000, "application/pdf"))]).json()
    assert big["errors"][0]["file"] == "a.pdf" and "Zu groß" in big["errors"][0]["message"]
    monkeypatch.setattr(importing, "ZIP_MAX_BYTES", 500)
    data = client.post("/api/reports", files=[("pdfs", ("b.zip", _zip({"x.pdf": b"0" * 1000}), "application/zip"))])
    assert "zu groß" in data.json()["errors"][0]["message"]


def test_export(client):
    _create(client, 1)
    response = client.get("/api/export?year=2025")
    assert response.status_code == 200
    assert client.get("/api/export?year=2020").status_code == 404
