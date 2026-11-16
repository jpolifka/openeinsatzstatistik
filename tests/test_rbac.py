# -*- coding: utf-8 -*-
"""Rollen und Rechte: Migration, Vererbung, Verteilung, eigene Rollen und Leitplanken.

Aufbau: VG A mit den Wehren A1 und A2, VG B mit der Wehr B1.
"""
import sqlite3

import pytest

from app import db, rbac, tenancy
from conftest import grant, login, make_tenant


@pytest.fixture
def world(make_client):
    vg_a, a1 = make_tenant("wehr-a1", "vg-a")
    make_tenant("wehr-a2", "vg-a")
    vg_b, _ = make_tenant("wehr-b1", "vg-b")
    grant("lead@example.org", "lead", a1)
    grant("vglead@example.org", "vg_lead", vg_a)
    grant("vglead2@example.org", "vg_lead", vg_a)
    grant("other@example.org", "vg_lead", vg_b)
    return make_client(login=True)


def _as(client, email):
    client.cookies.clear()
    return login(client, email)


def _roles(client):
    return {r["key"]: r for r in client.get("/api/admin/roles").json()["roles"]}


def _role(client, **values):
    body = {"label": "Gruppenführer", "scope": "tenant", "vg": "vg-a", "permissions": [], **values}
    return client.post("/api/admin/roles", json=body)


def test_old_memberships_are_migrated(tmp_path):
    con = db.connect(str(tmp_path / "app.db"))
    db.migrate(con, db.CENTRAL_MIGRATIONS[:5])
    con.execute("INSERT INTO vg (slug, name) VALUES ('vg-a', 'VG A')")
    con.execute("INSERT INTO tenant (slug, name, vg_id) VALUES ('wehr-a1', 'A1', 1)")
    con.execute("INSERT INTO account (email) VALUES ('a@example.org'), ('b@example.org')")
    con.execute("INSERT INTO membership (email, scope, scope_id, role) VALUES ('a@example.org', 'tenant', 1, 'lead'), "
                "('b@example.org', 'vg', 1, 'vg_lead')")
    con.commit()
    db.migrate(con, db.CENTRAL_MIGRATIONS)
    rows = con.execute("SELECT m.email, r.key FROM membership m JOIN role r ON r.id = m.role_id ORDER BY m.email")
    assert [tuple(r) for r in rows] == [("a@example.org", "lead"), ("b@example.org", "vg_lead")]
    roles = rbac.Roles(con)
    lead = roles.find("lead", 1)
    assert {rbac.STATS, rbac.PEOPLE, rbac.SETTINGS} <= roles.permissions(lead.id)        # geerbt über Erfasser
    assert {r.key for r in roles if r.id in roles.grants(lead.id)} == {"editor", "viewer", "deputy_lead"}
    assert rbac.PEOPLE in roles.permissions(roles.find("vg_lead", 1).id)
    con.close()


def test_role_log_is_append_only(world):
    with tenancy.central() as con:
        rbac.log(con, "x@example.org", "Test")
    with pytest.raises(sqlite3.DatabaseError, match="nur ergänzt"):
        with tenancy.central() as con:
            con.execute("UPDATE role_event SET action = 'gefälscht'")
    with pytest.raises(sqlite3.DatabaseError):
        with tenancy.central() as con:
            con.execute("DELETE FROM role_event")


def test_vg_lead_creates_inheriting_role(world):
    _as(world, "vglead@example.org")
    roles = _roles(world)
    response = _role(world, parent=roles["editor"]["id"], permissions=[rbac.KEYWORDS],
                     granted_by=[roles["lead"]["id"]])
    assert response.status_code == 200
    group = _roles(world)["gruppenfuehrer"]
    assert group["vg"] == "vg-a" and group["editable"] and group["deletable"]
    assert rbac.PEOPLE in group["effective"] and rbac.KEYWORDS in group["permissions"]
    # Der Wehrführer darf die neue Rolle in seiner Wehr vergeben (Verteilung), aber nicht in einer anderen
    _as(world, "lead@example.org")
    assign = {"email": "gf@example.org", "scope": "tenant", "slug": "wehr-a1", "role": "gruppenfuehrer"}
    assert world.post("/api/admin/memberships", json=assign).status_code == 200
    assert world.post("/api/admin/memberships", json={**assign, "slug": "wehr-a2"}).status_code == 403
    access = tenancy.access_for("gf@example.org")
    assert {rbac.PEOPLE, rbac.KEYWORDS} <= access.tenants["wehr-a1"].permissions
    assert rbac.SETTINGS not in access.tenants["wehr-a1"].permissions
    # Eigene Rolle der VG A gibt es in VG B nicht
    _as(world, "other@example.org")
    assert "gruppenfuehrer" not in _roles(world)
    assert world.post("/api/admin/memberships", json={**assign, "slug": "wehr-b1"}).status_code == 422
    # Benutzte Rolle lässt sich nicht löschen
    _as(world, "vglead@example.org")
    response = world.delete(f"/api/admin/roles/{group['id']}")
    assert response.status_code == 422 and "1 Zuordnung" in response.json()["detail"]


def test_role_changes_apply_immediately(world):
    _as(world, "vglead@example.org")
    _role(world, permissions=[rbac.INCIDENTS], granted_by=[_roles(world)["vg_lead"]["id"]])
    role = _roles(world)["gruppenfuehrer"]
    world.post("/api/admin/memberships", json={"email": "gf@example.org", "scope": "tenant", "slug": "wehr-a2",
                                               "role": "gruppenfuehrer"})
    assert rbac.WRITE not in tenancy.access_for("gf@example.org").tenants["wehr-a2"].permissions
    body = {"label": role["label"], "scope": "tenant", "permissions": [rbac.DELETE], "granted_by": role["granted_by"]}
    assert world.put(f"/api/admin/roles/{role['id']}", json=body).status_code == 200
    permissions = tenancy.access_for("gf@example.org").tenants["wehr-a2"].permissions
    assert {rbac.DELETE, rbac.WRITE, rbac.INCIDENTS, rbac.STATS} <= permissions        # mit Voraussetzungen
    events = world.get("/api/admin/role-events").json()["events"]
    assert [e["action"] for e in events[:3]] == ["Rolle geändert", "Rolle vergeben", "Rolle angelegt"]


def test_guardrails(world):
    _as(world, "vglead@example.org")
    roles = _roles(world)
    # Gesamtansicht nur für VG-Rollen
    assert _role(world, label="Übersicht", permissions=[rbac.VG_OVERVIEW]).status_code == 422
    # Erben nur im selben Bereich
    assert _role(world, label="Mix", parent=roles["vg_stats"]["id"]).status_code == 422
    # Systemrollen und globale Rollen ändert nur der Superadmin, eigene Rollen nicht man selbst
    body = {"label": "Wehrleiter", "scope": "vg", "permissions": [rbac.STATS]}
    assert world.put(f"/api/admin/roles/{roles['vg_lead']['id']}", json=body).status_code == 403
    assert _role(world, vg=None).status_code == 403
    assert _role(world, vg="vg-b").status_code == 403
    _role(world, label="Leitung", scope="vg", permissions=[rbac.STATS])
    leitung = _roles(world)["leitung"]
    with tenancy.central() as con:
        vg_a = con.execute("SELECT id FROM vg WHERE slug = 'vg-a'").fetchone()[0]
    grant("vglead@example.org", "leitung", vg_a)
    _as(world, "vglead@example.org")
    response = world.put(f"/api/admin/roles/{leitung['id']}", json={"label": "Leitung", "scope": "vg",
                                                                   "permissions": [rbac.ROLES_MANAGE]})
    assert response.status_code == 403 and "selbst" in response.json()["detail"]
    # … aber ein anderer Wehrleiter derselben VG
    _as(world, "vglead2@example.org")
    assert world.put(f"/api/admin/roles/{leitung['id']}", json={"label": "Leitung", "scope": "vg",
                                                               "permissions": [rbac.STATS]}).status_code == 200
    # Zyklen in der Vererbung
    _role(world, label="Unten", parent=None)
    unten = _roles(world)["unten"]
    _role(world, label="Oben", parent=unten["id"])
    oben = _roles(world)["oben"]
    response = world.put(f"/api/admin/roles/{unten['id']}", json={"label": "Unten", "scope": "tenant",
                                                                 "parent": oben["id"]})
    assert response.status_code == 422 and "von sich selbst" in response.json()["detail"]
    response = world.delete(f"/api/admin/roles/{unten['id']}")
    assert response.status_code == 422 and "Oben" in response.json()["detail"]


def test_superadmin_creates_global_role(world):
    _as(world, "admin@example.org")
    assert _role(world, label="Kassenprüfer", scope="vg", vg=None, permissions=[rbac.VG_RECORDS]).status_code == 200
    role = _roles(world)["kassenpruefer"]
    assert role["vg"] is None and rbac.VG_OVERVIEW in role["effective"]
    roles = _roles(world)
    body = {"label": "Wehrleiter", "scope": "vg", "parent": roles["vg_stats"]["id"],
            "permissions": roles["vg_lead"]["permissions"], "grants": roles["vg_lead"]["grants"] + [role["id"]]}
    assert world.put(f"/api/admin/roles/{roles['vg_lead']['id']}", json=body).status_code == 200
    # Gilt in allen VGs: der Wehrleiter von VG B vergibt sie
    _as(world, "other@example.org")
    assert world.post("/api/admin/memberships", json={"email": "kp@example.org", "scope": "vg", "slug": "vg-b",
                                                      "role": "kassenpruefer"}).status_code == 200
    access = tenancy.access_for("kp@example.org")
    assert access.vg_can(access.tenants["wehr-b1"].vg_id, rbac.VG_RECORDS)
    assert "wehr-a1" not in access.tenants
    # Systemrollen lassen sich nicht löschen
    _as(world, "admin@example.org")
    assert world.delete(f"/api/admin/roles/{roles['viewer']['id']}").status_code == 422


def test_editing_global_role_keeps_vg_distribution(world):
    """Der Superadmin ändert den Wehrleiter; die Verteilung auf eigene Rollen einer VG bleibt."""
    _as(world, "vglead@example.org")
    roles = _roles(world)
    _role(world, granted_by=[roles["vg_lead"]["id"]])
    own = _roles(world)["gruppenfuehrer"]["id"]
    _as(world, "admin@example.org")
    roles = _roles(world)
    lead = roles["vg_lead"]
    body = {"label": "Wehrleiter", "scope": "vg", "parent": lead["parent"], "permissions": lead["permissions"],
            "grants": [g for g in lead["grants"] if g != own]}
    assert world.put(f"/api/admin/roles/{lead['id']}", json=body).status_code == 200
    _as(world, "vglead2@example.org")
    assert world.post("/api/admin/memberships", json={"email": "gf@example.org", "scope": "tenant",
                                                      "slug": "wehr-a1", "role": "gruppenfuehrer"}).status_code == 200


def test_effective_permissions_show_origin(world):
    _as(world, "vglead@example.org")
    world.post("/api/admin/memberships", json={"email": "lead@example.org", "scope": "vg", "slug": "vg-a",
                                               "role": "vg_stats"})
    areas = world.get("/api/admin/users/effective", params={"email": "lead@example.org"}).json()["areas"]
    a1 = next(a for a in areas if a["name"] == "Wehr wehr-a1")
    stats = next(p for p in a1["permissions"] if p["key"] == rbac.STATS)
    assert stats["from"] == ["Wehrführer/in (Wehr wehr-a1)", "Statistik VG (VG vg-a)"]
    # Der Wehrführer sieht nur seine Wehr, nicht die anderen
    _as(world, "lead@example.org")
    names = [a["name"] for a in world.get("/api/admin/users/effective",
                                          params={"email": "vglead@example.org"}).json()["areas"]]
    assert names == ["Wehr wehr-a1"]


def test_roles_need_user_view(world):
    with tenancy.central() as con:
        a2 = con.execute("SELECT id FROM tenant WHERE slug = 'wehr-a2'").fetchone()[0]
    grant("editor@example.org", "editor", a2)
    _as(world, "editor@example.org")
    assert world.get("/api/admin/roles").status_code == 403
    assert world.get("/api/admin").status_code == 403
    assert not world.get("/api/config").json()["admin"]


def test_own_permissions_exclude_inherited(world):
    """Voraussetzungen, die schon geerbt sind, zählen nicht als eigene Rechte (Rechtematrix ● / ○)."""
    _as(world, "vglead@example.org")
    roles = _roles(world)
    assert rbac.STATS not in roles["lead"]["permissions"] and rbac.STATS in roles["lead"]["effective"]
    assert rbac.INCIDENTS in roles["editor"]["permissions"] and rbac.STATS not in roles["editor"]["permissions"]
    _role(world, parent=roles["viewer"]["id"], permissions=[rbac.WRITE])
    group = _roles(world)["gruppenfuehrer"]
    assert set(group["permissions"]) == {rbac.WRITE, rbac.INCIDENTS}
    assert rbac.DELETE not in group["effective"]


def test_inheriting_role_keeps_prerequisites_when_parent_shrinks(world):
    """Kind setzt people.edit voraus: verliert die Elternrolle Anwesenheit sehen bzw. bearbeiten, bleibt das
    Kind trotzdem vollständig (keine Rechte ohne ihre Voraussetzungen)."""
    _as(world, "vglead@example.org")
    _role(world, label="Basis", permissions=[rbac.PEOPLE, rbac.WRITE])
    base = _roles(world)["basis"]
    _role(world, label="Kind", parent=base["id"], permissions=[rbac.PEOPLE_EDIT, rbac.PEOPLE, rbac.WRITE])
    assert world.put(f"/api/admin/roles/{base['id']}", json={"label": "Basis", "scope": "tenant", "vg": "vg-a",
                                                               "permissions": [rbac.STATS]}).status_code == 200
    child = set(_roles(world)["kind"]["effective"])
    assert {rbac.PEOPLE_EDIT, rbac.PEOPLE, rbac.WRITE, rbac.INCIDENTS, rbac.STATS} <= child
