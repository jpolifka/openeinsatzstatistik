# -*- coding: utf-8 -*-
"""Mehrfachberichte über Wehren hinweg: Weitergabe, Hinweise an andere Wehren und Prüfprotokoll."""
import dataclasses

import pytest

from app import db, main, records, store, tenancy
from app.tenant_config import Vehicle
from conftest import CFG, grant, login, make_tenant
from test_report import FULL, LEFT

# Drei Wehren einer VG: A1 = 02/.., A2 = 01/.., A3 = 03/.. (alle Fahrzeuge der VG heißen FL NR#.BHÖ …)
OTHER = dataclasses.replace(CFG, fleet=(Vehicle("01/46"),), own_prefix="01/", unit_marker="FW NR#.BHÖ 01")
THIRD = dataclasses.replace(CFG, fleet=(Vehicle("03/41"),), own_prefix="03/", unit_marker="FW NR#.BHÖ 03")
LINE_0341 = "FL NR#.BHÖ 03/41-01 0 / 0 / 2 / 2 / 0 12.03.25 10:20:00 12.03.25 10:25:00 12.03.25 10:35:00 Ja " \
            "12.03.25 10:50:00 12.03.25 10:55:00\n"
MASTER = "EINSATZBERICHT\nStammdatensatz 9000001\nEinsatznummer Leitstelle: 1250000009\n" + \
    FULL.split("Anwesenheitsliste")[0].replace("FL NR#.LIN", LINE_0341 + "FL NR#.LIN")


def _bks(kind, report_id, unit, text=FULL):
    return f"EINSATZBERICHT\n{kind} {report_id}\nDatensatz: 9000001\nFeuerwehrhaus: {unit}\n" + text


TEXTS = {
    "stamm.pdf": (MASTER, LEFT, ""),
    # A2 schreibt für 02/45 eine andere Stärke (3 statt 2) als A1 in ihrem eigenen Bericht
    "a2.pdf": (_bks("Hauptbericht", "9000002", "FW NR#.BHÖ 01 Musterstadt",
                    FULL.replace("02/45-01 0 / 1 / 1 / 2 / 0", "02/45-01 0 / 1 / 2 / 3 / 0")), LEFT, ""),
    "a1.pdf": (_bks("Nebenbericht", "9000003", "FW NR#.BHÖ 02 Musterdorf"), LEFT, ""),
    "fez.pdf": (_bks("Nebenbericht", "9000004", "FW NR#.BHÖ 00 FEZ VG"), LEFT, ""),
}


@pytest.fixture
def vg(make_client, monkeypatch):
    vg_id, a1 = make_tenant("wehr-a1")
    _, a2 = make_tenant("wehr-a2", cfg=OTHER)
    make_tenant("wehr-a3", cfg=THIRD)
    grant("lead1@example.org", "lead", a1)
    grant("lead2@example.org", "lead", a2)
    grant("vglead@example.org", "vg_lead", vg_id)
    monkeypatch.setattr(main.pdf_report, "extract_text", lambda path: TEXTS[path.rsplit("/", 1)[-1]])
    return make_client(login=True)


def _as(client, email, scope="t:wehr-a1"):
    client.cookies.clear()
    login(client, email)
    client.cookies.set("scope", scope)
    return client


def _upload(client, *names):
    return client.post("/api/reports", files=[("pdfs", (n, b"x", "application/pdf")) for n in names]).json()


def _accept(client, data, filename, **body):
    return client.post("/api/reports/accept", json={"token": data["token"], "filename": filename, "fields": {},
                                                     **body}).json()


def _notices(client):
    return client.get("/api/notices").json()["notices"]


def test_report_of_other_tenant_is_forwarded_and_notices_follow(vg):
    client = _as(vg, "lead1@example.org")
    data = _upload(client, "stamm.pdf", "a2.pdf", "a1.pdf", "fez.pdf")
    assert [r["filename"] for r in data["reports"]] == ["a1.pdf"]
    notes = {n["file"]: n["message"] for n in data["notes"]}
    assert "Stammdatensatz 9000001" in notes["stamm.pdf"]
    assert "an Wehr wehr-a2 zur Übernahme weitergegeben" in notes["a2.pdf"]
    assert "übersprungen" in notes["fez.pdf"]
    # A1 hat den eigenen Bericht noch nicht übernommen: Hinweis aus dem Stammdatensatz
    assert [n["kind"] for n in _notices(client)] == ["missing"]
    _accept(client, data, "a1.pdf")
    assert _notices(client) == []                         # mit eigenem Bericht erledigt

    # A2 sieht beim nächsten Anmelden den weitergegebenen Bericht; A3 fehlt der Bericht zu 03/41
    client = _as(vg, "lead2@example.org", "t:wehr-a2")
    assert [(n["kind"], n["tenant"]) for n in _notices(client)] == [("pending", "wehr-a2")]
    assert "lead1@example.org" in _notices(client)[0]["text"]
    pending = client.get("/api/pending").json()["reports"]
    assert [(p["tenant"], p["bks_report_id"]) for p in pending] == [("wehr-a2", "9000002")]
    data = client.post("/api/pending/read", json={"ids": [pending[0]["id"]]}).json()
    assert data["reports"][0]["shared_with"] == []      # A1 ist für den Wehrführer von A2 nicht sichtbar
    _accept(client, data, "a2.pdf")
    assert client.get("/api/pending").json()["reports"] == []
    with tenancy.central() as con:
        a3 = [n for n in records.open_notices(con, [3])]
    assert [n["kind"] for n in a3] == ["missing"] and "03/41" in a3[0]["text"]

    # A2 schreibt für 02/45 eine andere Stärke: A1 bekommt einen Hinweis und kann ihn erledigen
    client = _as(vg, "lead1@example.org")
    deviation = _notices(client)[0]
    assert deviation["kind"] == "deviation"
    assert "Bericht von Wehr wehr-a2" in deviation["text"] and "02/45 Stärke 3 (erfasst: 2)" in deviation["text"]
    assert deviation["incident_key"].startswith("wehr-a1:")
    assert _as(vg, "lead2@example.org", "t:wehr-a2").post(f"/api/notices/{deviation['id']}/done").status_code == 403
    client = _as(vg, "lead1@example.org")
    assert client.post(f"/api/notices/{deviation['id']}/done").status_code == 200
    assert _notices(client) == []


def test_import_by_vg_lead_is_shown_to_the_tenant(vg):
    client = _as(vg, "vglead@example.org", "vg:vg-a")
    data = _upload(client, "a2.pdf")
    _accept(client, data, "a2.pdf")
    client = _as(vg, "lead2@example.org", "t:wehr-a2")
    notice = _notices(client)[0]
    assert notice["kind"] == "import" and "von vglead@example.org eingelesen" in notice["text"]
    # Wer selbst zur Wehr gehört, erzeugt keinen Hinweis für sie
    _accept(client, _upload(client, "a2.pdf"), "a2.pdf", replace=True)
    assert [n["kind"] for n in _notices(client)] == ["import"]


def test_protocol_for_vg_lead(vg):
    client = _as(vg, "vglead@example.org", "vg:vg-a")
    data = _upload(client, "stamm.pdf", "a1.pdf", "a2.pdf")
    _accept(client, data, "a1.pdf")
    _accept(client, data, "a2.pdf")
    entries = client.get("/api/records?year=2025").json()["records"]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["record"]["dispatch_number"] == "1250000009"
    assert [i["tenant"] for i in entry["incidents"]] == ["wehr-a1", "wehr-a2"]
    assert [(f["tenant"], f["kind"], f["vehicle"]) for f in entry["findings"]] == [("wehr-a3", "missing", "03/41")]
    assert entry["reviewed"] is None

    assert client.post("/api/records/9000001/review", json={"done": True}).status_code == 200
    assert client.get("/api/records?year=2025").json()["records"][0]["reviewed"]["by"] == "vglead@example.org"
    # Neuer Befund (Stärke im Bericht von A1 geändert): wieder offen
    with db.connection(tenancy.tenant_path("wehr-a1")) as con:
        con.execute("UPDATE vehicle SET crew = 7 WHERE call_sign = '02/45'")
    entry = client.get("/api/records?year=2025").json()["records"][0]
    assert entry["reviewed"] is None
    assert ("wehr-a1", "vehicle", "02/45", "Stärke", 2, 7) in \
        [(f["tenant"], f["kind"], f["vehicle"], f["field"], f["source"], f["stored"]) for f in entry["findings"]]

    for email, scope in (("lead1@example.org", "t:wehr-a1"), ("lead1@example.org", "vg:vg-a")):
        assert _as(vg, email, scope).get("/api/records?year=2025").status_code == 403
    assert _as(vg, "vglead@example.org", "t:wehr-a1").get("/api/records").status_code == 403


def test_vehicle_differences_compare_minutes_and_skip_unknown_old_times():
    incident = {"vehicles": {"02/45": {"name": "FL NR#.BHÖ 02/45-01", "crew": 5, "alerted": None,
                                       "departed": "10:12:59", "arrived": "10:16:00", "finished": None}}}
    source = [{"name": "FL NR#.BHÖ 02/45-01", "crew": 4, "alerted": "2025-03-12T10:09:41",
               "departed": "2025-03-12T10:12:04", "arrived": None, "finished": "2025-03-12T10:48:00"},
              {"name": "FL NR#.BHÖ 02/24-01", "crew": 0, "departed": "2025-03-12T10:13:00", "arrived": None},
              {"name": "FL NR#.BHÖ 02/19-01", "crew": 1, "departed": None, "arrived": None},   # nicht ausgerückt
              {"name": "FL NR#.BHÖ 01/46-01", "crew": 6, "departed": "2025-03-12T10:07:00"}]   # andere Wehr
    assert records.vehicle_differences(source, incident, CFG) == [
        {"vehicle": "02/45", "field": "Stärke", "source": 4, "stored": 5},
        {"vehicle": "02/45", "field": "Eintreffen", "source": None, "stored": "10:16"},
        {"vehicle": "02/24", "field": "Fahrzeug", "source": "ausgerückt", "stored": None}]


def test_edit_vehicles_and_people_survive_reimport(vg):
    client = _as(vg, "lead1@example.org")
    data = _upload(client, "a1.pdf")
    saved = _accept(client, data, "a1.pdf")
    members = {m["name"]: m["id"] for m in client.get("/api/members?tenant=wehr-a1").json()["members"]}
    body = {"vehicles": [{"call_sign": "02/45", "crew": 4, "departed": "10:12", "arrived": "10:16"},
                         {"call_sign": "02/71", "crew": 3, "departed": "10:20", "arrived": None}],
            "people": [{"id": members["Muster, Max"], "role": "Einheitsführer", "vehicle": "02/45"},
                       {"name": "Neu, Nora", "role": "Maschinist", "vehicle": "02/71"}]}
    edited = client.put(f"/api/incidents/{saved['id']}", json=body).json()
    vehicles = {v["call_sign"]: v for v in edited["vehicles"] if v["crew"] is not None}
    assert {cs: (v["crew"], v["departed"]) for cs, v in vehicles.items()} == \
        {"02/45": (4, "10:12:00"), "02/71": (3, "10:20:00")}           # 02/24 entfernt
    assert sorted(p["name"] for p in edited["people"]) == ["Muster, Max", "Neu, Nora"]
    assert "Neu, Nora" in [m["name"] for m in client.get("/api/members?tenant=wehr-a1").json()["members"]]

    # Erneut eingelesen: Werte aus der PDF ersetzen die importierten Zeilen, manuelle bleiben
    data = _upload(client, "a1.pdf")
    updated = _accept(client, data, "a1.pdf", replace=True)
    vehicles = {v["call_sign"]: v["crew"] for v in updated["vehicles"] if v["crew"] is not None}
    assert vehicles == {"02/45": 2, "02/24": 0, "02/71": 3}
    assert "Neu, Nora" in [p["name"] for p in updated["people"]]


def test_edit_rejects_invalid_values(vg):
    client = _as(vg, "lead1@example.org")
    saved = _accept(client, _upload(client, "a1.pdf"), "a1.pdf")
    url = f"/api/incidents/{saved['id']}"
    assert client.put(url, json={"vehicles": [{"call_sign": "09/99"}]}).status_code == 422
    assert client.put(url, json={"vehicles": [{"call_sign": "02/45", "departed": "25:00"}]}).status_code == 422
    response = client.put(url, json={"description": "geändert", "vehicles": [{"call_sign": "02/45", "crew": 120}]})
    assert response.status_code == 422
    # Nichts halb gespeichert
    incident = [i for i in client.get("/api/incidents?year=2025").json()["incidents"] if i["id"] == saved["id"]][0]
    assert incident["description"] != "geändert"
    assert client.get("/api/members?tenant=wehr-a2").status_code == 403
