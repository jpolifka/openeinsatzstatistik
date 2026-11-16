# -*- coding: utf-8 -*-
"""Grenzen der Rollen: Personenrechte, eigene Zuordnung, Änderung bestehender Rollen und fehlendes Namensrecht."""
import pytest

from app import db, rbac, store, tenancy
from conftest import grant, login, make_tenant


@pytest.fixture
def world(make_client):
    vg_a, a1 = make_tenant("wehr-a1", "vg-a")
    make_tenant("wehr-a2", "vg-a")
    grant("lead@example.org", "lead", a1)
    grant("vglead@example.org", "vg_lead", vg_a)
    with db.connection(tenancy.tenant_path("wehr-a1")) as con:
        incident_id = store.create_incident(con, {"number": 1, "started_at": "2025-03-12T10:00:00", "keyword": "B2",
                                                  "place": "Altenau", "unit_leader": "M. Muster"}, source="pdf")
        store.add_attendance(con, incident_id, store.MemberDirectory(con).find_or_create("Muster", "Max"))
    client = make_client(login=True)
    client.incident = f"wehr-a1:{incident_id}"
    client.a1 = a1
    return client


def _as(client, email):
    client.cookies.clear()
    login(client, email)
    client.cookies.set("scope", "t:wehr-a1")
    return client


def _roles(client):
    return {r["key"]: r for r in client.get("/api/admin/roles").json()["roles"]}


def test_vg_only_permissions_cannot_be_added_to_tenant_role_afterwards(world):
    """Reine VG-Rechte (Gesamtansicht …) gibt es nur für VG-Rollen – auch beim Ändern einer Wehr-Rolle."""
    _as(world, "vglead@example.org")
    created = world.post("/api/admin/roles", json={"label": "Auswertung", "scope": "tenant", "vg": "vg-a",
                                                   "permissions": [rbac.STATS]})
    assert created.status_code == 200
    role = _roles(world)["auswertung"]
    response = world.put(f"/api/admin/roles/{role['id']}", json={"label": "Auswertung", "scope": "tenant",
                                                                "permissions": [rbac.STATS, rbac.VG_OVERVIEW]})
    assert response.status_code == 422
    assert rbac.VG_OVERVIEW not in _roles(world)["auswertung"]["permissions"]


def test_nobody_but_superadmin_grants_themselves_a_role(world):
    _as(world, "vglead@example.org")
    response = world.post("/api/admin/memberships", json={"email": "vglead@example.org", "scope": "tenant",
                                                          "slug": "wehr-a2", "role": "lead"})
    assert response.status_code == 403
    with tenancy.central() as con:
        count = con.execute("SELECT COUNT(*) FROM membership WHERE email = 'vglead@example.org'").fetchone()[0]
    assert count == 1


def test_role_without_people_permission_neither_sees_nor_edits_names(world):
    """Wehr-Rolle mit Einsatzrechten, aber ohne people.*: Anwesenheit nur als Zahl, Einheitsführung unveränderlich."""
    _as(world, "vglead@example.org")
    created = world.post("/api/admin/roles", json={"label": "Schreiber", "scope": "tenant", "vg": "vg-a",
                                                   "permissions": [rbac.INCIDENTS, rbac.WRITE]})
    assert created.status_code == 200, created.text
    grant("schreiber@example.org", "schreiber", world.a1)
    _as(world, "schreiber@example.org")
    listed = world.get("/api/incidents?year=2025").json()["incidents"][0]
    assert listed["people"] == [] and listed["people_count"] == 1 and listed["unit_leader"] is None
    assert world.get("/api/members?tenant=wehr-a1").status_code == 403
    attendance = world.put(f"/api/incidents/{world.incident}", json={"revision": listed["revision"],
                                                                     "people": [{"name": "Beispiel, Erika"}]})
    assert attendance.status_code == 403
    changed = world.put(f"/api/incidents/{world.incident}", json={"revision": listed["revision"],
                                                                  "unit_leader": "E. Beispiel", "place": "Neuwied"})
    assert changed.status_code == 200
    with db.connection(tenancy.tenant_path("wehr-a1")) as con:
        saved = store.load_incident(con, int(world.incident.split(":")[1]))
    assert (saved["place"], saved["unit_leader"]) == ("Neuwied", "M. Muster")
    assert len(saved["people"]) == 1
