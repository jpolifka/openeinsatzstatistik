# -*- coding: utf-8 -*-
"""Rechtematrix und Trennung der Wehren über alle Endpunkte mit Einsatzdaten.

Aufbau: VG A mit den Wehren A1 und A2, VG B mit der Wehr B1, in jeder ein Einsatz mit einer Person.
"""
import pytest

from app import db, main, report, store, tenancy
from conftest import grant, login, make_tenant
from test_report import read

USERS = {  # Adresse -> (Rolle, Bereich)
    "lead@example.org": ("lead", "A1"),
    "editor@example.org": ("editor", "A1"),
    "viewer@example.org": ("viewer", "A1"),
    "vglead@example.org": ("vg_lead", "VG A"),
    "vgstats@example.org": ("vg_stats", "VG A"),
    "admin@example.org": (None, None),          # Superadmin
}
# Rechtematrix wie in der README: Rolle -> erwarteter Status je Endpunkt (Wehr A1 ausgewählt)
MATRIX = {
    #                          years evaluation incidents export reports  edit  delete-in-B1
    "lead@example.org":       (200,  200,       200,      200,   400,     200,  403),
    "editor@example.org":     (200,  200,       200,      200,   400,     200,  403),
    "viewer@example.org":     (200,  200,       403,      403,   403,     403,  403),
    "vglead@example.org":     (200,  200,       200,      200,   400,     200,  403),
    "vgstats@example.org":    (200,  200,       403,      403,   403,     403,  403),
    "admin@example.org":      (200,  200,       200,      200,   400,     200,  200),
}


def _incident(slug):
    with db.connection(tenancy.tenant_path(slug)) as con:
        incident_id = store.create_incident(con, {"number": 1, "started_at": "2025-03-12T10:00:00", "keyword": "B2",
                                                  "place": "Rheinbrohl", "unit_leader": "M. Muster"}, source="pdf")
        store.add_attendance(con, incident_id, store.MemberDirectory(con).find_or_create("Muster", "Max"))
    return f"{slug}:{incident_id}"


@pytest.fixture
def world(make_client):
    vg_a, a1 = make_tenant("wehr-a1", "vg-a")
    _, a2 = make_tenant("wehr-a2", "vg-a")
    vg_b, b1 = make_tenant("wehr-b1", "vg-b")
    ids = {slug: _incident(slug) for slug in ("wehr-a1", "wehr-a2", "wehr-b1")}
    scopes = {"A1": a1, "VG A": vg_a}
    for email, (role, scope) in USERS.items():
        if role:
            grant(email, role, scopes[scope])
    client = make_client(login=True)
    return client, ids


def _as(client, email, scope="t:wehr-a1"):
    client.cookies.clear()
    login(client, email)
    client.cookies.set("scope", scope)
    return client


@pytest.mark.parametrize("email", list(MATRIX))
def test_permission_matrix(world, email):
    client, ids = world
    _as(client, email)
    statuses = (
        client.get("/api/years").status_code,
        client.get("/api/evaluation?year=2025").status_code,
        client.get("/api/incidents?year=2025").status_code,
        client.get("/api/export?year=2025").status_code,
        client.post("/api/reports", files=[("pdfs", ("a.txt", b"x", "text/plain"))]).status_code,
        client.put(f"/api/incidents/{ids['wehr-a1']}", json={"description": "geändert"}).status_code,
        client.delete(f"/api/incidents/{ids['wehr-b1']}").status_code,
    )
    assert statuses == MATRIX[email]


@pytest.mark.parametrize("email", ["viewer@example.org", "vgstats@example.org"])
def test_statistics_roles_see_no_names(world, email):
    client, _ = world
    response = _as(client, email).get("/api/evaluation?year=2025")
    assert response.json()["attendance"] is None
    assert "Muster" not in response.text
    config = client.get("/api/config").json()
    assert config["permissions"] == ["stats"]


def test_foreign_scope_cookie_falls_back_to_own_tenant(world):
    client, ids = world
    _as(client, "lead@example.org", scope="t:wehr-b1")
    assert client.get("/api/config").json()["tenant"]["slug"] == "wehr-a1"
    assert [i["id"] for i in client.get("/api/incidents?year=2025").json()["incidents"]] == [ids["wehr-a1"]]
    assert client.post("/api/scope", json={"key": "t:wehr-b1"}).status_code == 403
    assert client.post("/api/scope", json={"key": "t:wehr-a1"}).status_code == 200


def test_foreign_incidents_cannot_be_changed(world):
    client, ids = world
    _as(client, "lead@example.org")
    assert client.put(f"/api/incidents/{ids['wehr-b1']}", json={"description": "fremd"}).status_code == 403
    assert client.put(f"/api/incidents/{ids['wehr-a2']}", json={"description": "fremd"}).status_code == 403
    assert client.put("/api/incidents/unbekannt:1", json={}).status_code == 403
    with db.connection(tenancy.tenant_path("wehr-b1")) as con:
        assert store.load_incidents(con)[0]["description"] == ""


def test_vg_roles_see_only_their_vg(world):
    client, ids = world
    config = _as(client, "vglead@example.org", scope="").get("/api/config").json()
    assert [s["key"] for s in config["scopes"]] == ["vg:vg-a", "t:wehr-a1", "t:wehr-a2"]
    assert config["vg"]["slug"] == "vg-a" and config["tenant"] is None      # Standard: Gesamtansicht der VG
    _as(client, "vglead@example.org", scope="t:wehr-a2")
    assert client.put(f"/api/incidents/{ids['wehr-a2']}", json={"description": "VG"}).status_code == 200
    assert client.get("/api/export?year=2025").status_code == 200
    _as(client, "vglead@example.org", scope="vg:vg-b")
    assert client.get("/api/config").json()["vg"]["slug"] == "vg-a"
    assert client.post("/api/scope", json={"key": "vg:vg-b"}).status_code == 403
    assert _as(client, "lead@example.org").post("/api/scope", json={"key": "vg:vg-a"}).status_code == 403


def test_preview_belongs_to_its_user_and_tenant(world):
    client, _ = world
    r = read()
    token = main.previews.add([(r, "wehr-a1")], "lead@example.org")
    body = {"token": token, "filename": r["filename"], "fields": {}}
    assert _as(client, "editor@example.org").post("/api/reports/accept", json=body).status_code == 410
    assert _as(client, "lead@example.org").post("/api/reports/accept", json=body).status_code == 200
    # Vorschau einer fremden Wehr (z. B. nach Entzug der Rolle) wird nicht übernommen
    token = main.previews.add([(read(), "wehr-b1")], "lead@example.org")
    response = client.post("/api/reports/accept", json={**body, "token": token})
    assert response.status_code == 403
    with db.connection(tenancy.tenant_path("wehr-b1")) as con:
        assert len(store.load_incidents(con)) == 1


def test_saved_report_records_author(world):
    client, _ = world
    r = read()
    token = main.previews.add([(r, "wehr-a1")], "editor@example.org")
    saved = _as(client, "editor@example.org").post(
        "/api/reports/accept", json={"token": token, "filename": r["filename"], "fields": {}}).json()
    slug, incident_id = saved["id"].split(":")
    with db.connection(tenancy.tenant_path(slug)) as con:
        row = con.execute("SELECT modified_by FROM incident WHERE id = ?", (incident_id,)).fetchone()
    assert row["modified_by"] == "editor@example.org"
