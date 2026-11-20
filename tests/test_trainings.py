# -*- coding: utf-8 -*-
"""Übungsdienste: Erfassen, Rechte, Mandantentrennung und – vor allem – keine Wirkung auf die Einsatzauswertungen."""
import io

import openpyxl
import pytest

from app import db, rbac, store, tenancy
from conftest import grant, login, make_tenant

BODY = {"topic": "Knoten und Stiche", "started_at": "2025-03-12T19:00", "ended_at": "2025-03-12T21:30",
        "member_ids": [], "new_members": []}


def _incident(slug="wehr-a1"):
    with db.connection(tenancy.tenant_path(slug)) as con:
        incident_id = store.create_incident(con, {"number": 1, "started_at": "2025-03-12T10:00:00", "keyword": "B2",
                                                  "place": "Altenau"}, source="pdf")
        store.add_attendance(con, incident_id, store.MemberDirectory(con).find_or_create("Muster", "Max"))


@pytest.fixture
def client(make_client):
    make_tenant("wehr-a1")
    _incident()
    return make_client()


def _member_ids(client):
    return {m["name"]: m["id"] for m in client.get("/api/trainings?year=2025").json()["members"]}


def test_create_with_existing_and_new_members(client):
    ids = _member_ids(client)
    body = {**BODY, "member_ids": [ids["Muster, Max"]], "new_members": [{"last_name": "Beispiel", "first_name": "Erika"}]}
    response = client.post("/api/trainings", json=body)
    assert response.status_code == 200, response.text
    training = response.json()
    assert training["duration_min"] == 150 and training["year"] == 2025
    assert {p["name"] for p in training["participants"]} == {"Muster, Max", "Beispiel, Erika"}
    assert "Beispiel, Erika" in _member_ids(client)          # in den Personenstamm übernommen


def test_new_member_matching_existing_is_not_duplicated(client):
    response = client.post("/api/trainings", json={**BODY, "new_members": [{"last_name": "Muster", "first_name": "Max"}]})
    assert [p["name"] for p in response.json()["participants"]] == ["Muster, Max"]
    assert len(client.get("/api/trainings").json()["members"]) == 1


def test_validation(client):
    assert client.post("/api/trainings", json={**BODY, "topic": " "}).status_code == 422
    assert client.post("/api/trainings", json={**BODY, "ended_at": "2025-03-12T19:00"}).status_code == 422
    assert client.post("/api/trainings", json={**BODY, "ended_at": "2025-04-12T19:00"}).status_code == 422
    assert client.post("/api/trainings", json={**BODY, "member_ids": [999]}).status_code == 422
    assert client.post("/api/trainings", json={**BODY, "started_at": "kaputt"}).status_code == 422
    # mehrtägig mit Enddatum ist erlaubt
    assert client.post("/api/trainings", json={**BODY, "ended_at": "2025-03-14T12:00"}).status_code == 200


def test_update_and_delete_need_current_revision(client):
    training = client.post("/api/trainings", json=BODY).json()
    url = f"/api/trainings/{training['id']}"
    assert client.put(url, json=BODY).status_code == 428
    changed = {**BODY, "topic": "Funk", "revision": training["revision"]}
    assert client.put(url, json=changed).json()["revision"] == 1
    assert client.put(url, json=changed).status_code == 409                    # veraltet
    assert client.delete(url).status_code == 428
    assert client.delete(url + "?revision=0").status_code == 409
    assert client.delete(url + "?revision=1").status_code == 200
    assert client.delete(url + "?revision=1").status_code == 404


def test_member_inactive_and_summary(client):
    ids = _member_ids(client)
    client.post("/api/trainings", json={**BODY, "member_ids": [ids["Muster, Max"]]})
    result = client.put(f"/api/trainings/members/{ids['Muster, Max']}", json={"active": False}).json()
    assert result["members"][0]["active"] is False
    data = client.get("/api/trainings?year=2025").json()
    assert data["summary"]["count"] == 1
    person = data["summary"]["members"][0]
    assert person["trainings"] == 1 and person["hours"] == 2.5 and person["rate"] == 1
    # eine ausgeschiedene Person wird bei erneuter Eingabe wieder aktiv
    client.post("/api/trainings", json={**BODY, "new_members": [{"last_name": "Muster", "first_name": "Max"}]})
    assert client.get("/api/trainings").json()["members"][0]["active"] is True


def test_trainings_never_enter_evaluations(client):
    """Übungen mit Teilnehmern ändern weder Auswertung noch Einsatzliste, Personal, Export noch Kennzahlen."""
    ids = _member_ids(client)
    before = [client.get(u).json() for u in ("/api/evaluation?year=2025", "/api/incidents?year=2025")]
    xlsx_before = client.get("/api/export?year=2025")
    client.post("/api/trainings", json={**BODY, "member_ids": [ids["Muster, Max"]],
                                        "new_members": [{"last_name": "Nur", "first_name": "Uebung"}]})
    after = [client.get(u).json() for u in ("/api/evaluation?year=2025", "/api/incidents?year=2025")]
    assert before == after
    attendance = after[0]["attendance"]
    assert [m["name"] for m in attendance["members"]] == ["Muster, Max"]         # „Nur, Uebung“ fehlt
    assert attendance["members"][0]["incidents"] == 1
    with db.connection(tenancy.tenant_path("wehr-a1")) as con:
        assert [m["name"] for m in store.members_of_year(con, 2025)] == ["Muster, Max"]
        assert con.execute("SELECT COUNT(*) FROM incident").fetchone()[0] == 1
    book = openpyxl.load_workbook(io.BytesIO(client.get("/api/export?year=2025").content))
    assert "Übungen" in book.sheetnames and "Übungen" not in openpyxl.load_workbook(io.BytesIO(xlsx_before.content)).sheetnames
    sheet = book["Übungen"]
    assert "Knoten und Stiche" in [c.value for row in sheet.iter_rows() for c in row]
    # und der Einsatz-Blattbestand bleibt: Übungen stehen nicht in der Einsatzübersicht
    assert all("Knoten" not in str(c.value) for row in book["Einsatzübersicht_Import"].iter_rows() for c in row)


def test_other_tenant_is_separate(make_client):
    make_tenant("wehr-a1"), make_tenant("wehr-a2")
    client = make_client()
    client.cookies.set("scope", "t:wehr-a1")
    client.post("/api/trainings", json=BODY)
    client.cookies.set("scope", "t:wehr-a2")
    assert client.get("/api/trainings?year=2025").json()["trainings"] == []


def test_rights(make_client):
    vg, a1 = make_tenant("wehr-a1")
    for email, role in (("trainer@example.org", "trainer"), ("editor@example.org", "editor"),
                        ("lead@example.org", "lead"), ("viewer@example.org", "viewer")):
        grant(email, role, a1)
    client = make_client(login=True)

    def status(email):
        client.cookies.clear()
        login(client, email)
        client.cookies.set("scope", "t:wehr-a1")
        return client.get("/api/trainings").status_code, client.post("/api/trainings", json=BODY).status_code

    assert status("trainer@example.org") == (200, 200)
    assert status("editor@example.org") == (200, 200)
    assert status("lead@example.org") == (200, 200)
    assert status("viewer@example.org") == (403, 403)


def test_trainer_role_is_minimal(data_dir):
    with tenancy.central() as con:
        roles = rbac.Roles(con)
        permissions = roles.permissions(roles.find("trainer", None).id)
    assert permissions == {rbac.STATS, rbac.TRAININGS, rbac.TRAININGS_EDIT}
    assert rbac.TRAININGS in rbac.close({rbac.TRAININGS_EDIT})          # Ändern setzt Sehen voraus
