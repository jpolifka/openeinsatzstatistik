# -*- coding: utf-8 -*-
"""Funktionen des BKS-Portals als Rollen und Art der VG (Aufgabenträger-Ebene)."""
import sqlite3

import pytest

from app import db, rbac, store, tenancy
from conftest import grant, login, make_tenant


@pytest.fixture
def world(make_client):
    vg_a, a1 = make_tenant("wehr-a1", "vg-a")
    make_tenant("wehr-a2", "vg-a")
    vg_d, d1 = make_tenant("kreis-d1", "kreis-d", kind="district")
    vg_l, _ = make_tenant("leit-l1", "leit-l", kind="dispatch")
    with db.connection(tenancy.tenant_path("wehr-a1")) as con:
        incident_id = store.create_incident(con, {"number": 1, "started_at": "2025-03-12T10:00:00", "keyword": "B2",
                                                  "place": "Altenau", "unit_leader": "M. Muster"}, source="pdf")
        store.add_attendance(con, incident_id, store.MemberDirectory(con).find_or_create("Muster", "Max"))
    client = make_client(login=True)
    client.ids = {"vg-a": vg_a, "kreis-d": vg_d, "leit-l": vg_l, "a1": a1, "d1": d1}
    return client


def _as(client, email, scope="t:wehr-a1"):
    client.cookies.clear()
    login(client, email)
    client.cookies.set("scope", scope)
    return client


def test_new_roles_exist_with_expected_rights(world):
    with tenancy.central() as con:
        roles = rbac.Roles(con)
    perms = lambda key: roles.permissions(roles.find(key, world.ids["vg-a"]).id)    # noqa: E731
    assert rbac.PEOPLE in perms("bki") and rbac.INCIDENTS in perms("bki") and rbac.ROLES_MANAGE not in perms("bki")
    assert perms("bki_deputy") == perms("bki")
    assert perms("deputy_lead") == perms("lead")
    assert rbac.PEOPLE in perms("vg_lead") and rbac.PEOPLE in perms("vg_deputy")      # Wehrleiter/in wie im BKS
    assert rbac.PEOPLE not in perms("vg_stats")
    assert roles.find("vg_lead", 1).label == "Wehrleiter/in" and roles.find("editor", 1).label.startswith("Bearbeiter")


def test_tiers_staff_lead_and_vg_admin(world):
    """Sachbearbeitung bearbeitet, Leitung konfiguriert und vergibt, nur die VG-Verwaltung hat AVV, Gebühren, Rollenpflege."""
    with tenancy.central() as con:
        roles = rbac.Roles(con)
    vg = world.ids["vg-a"]
    perms = lambda key: roles.permissions(roles.find(key, vg).id)    # noqa: E731
    admin_only = {rbac.VG_FEES, rbac.DPA_EDIT, rbac.ROLES_MANAGE}
    for key in ("fez", "bki", "bki_deputy", "officer_kats", "officer_fire"):
        assert not perms(key) & admin_only, key
    assert not perms("fez") & {rbac.VG_FEES}
    assert admin_only <= perms("vg_lead")
    staff = perms("officer_kats")
    assert {rbac.INCIDENTS, rbac.WRITE, rbac.DELETE, rbac.PEOPLE, rbac.VG_RECORDS} <= staff
    assert not staff & {rbac.SETTINGS, rbac.KEYWORDS, rbac.USERS_GRANT, rbac.PLAN_RELEASE}
    lead = perms("bki")
    assert {rbac.SETTINGS, rbac.KEYWORDS, rbac.USERS_GRANT, rbac.PLAN_RELEASE, rbac.VG_RECORDS} <= lead
    with tenancy.central() as con:
        roles = rbac.Roles(con)
        leit = roles.find("dispatch_lead", world.ids["leit-l"])
        staff_d = roles.find("dispatch_staff", world.ids["leit-l"])
        assert rbac.VG_RECORDS not in roles.permissions(leit.id) | roles.permissions(staff_d.id)
        assert roles.grants(roles.find("officer_fire", vg).id) == frozenset()
        assert roles.find("officer_fire", vg).parent_id is None


def test_role_fits_only_matching_kinds(world):
    with tenancy.central() as con:
        keys = lambda vg: {r.key for r in rbac.Roles(con).visible(world.ids[vg])}    # noqa: E731
        assert {"bki", "fez", "vg_lead", "officer_fire"} <= keys("vg-a")
        assert "dispatch_lead" not in keys("vg-a") and "dispatch_lead" in keys("leit-l")
        assert "vg_lead" not in keys("kreis-d") and "fez" not in keys("kreis-d") and "bki" in keys("kreis-d")
        with pytest.raises(ValueError):
            tenancy.grant(con, "x@example.org", "dispatch_lead", world.ids["vg-a"])
        tenancy.grant(con, "x@example.org", "dispatch_lead", world.ids["leit-l"])


def test_bki_sees_names_in_all_wehren_of_vg(world):
    grant("bki@example.org", "bki", world.ids["vg-a"])
    incident = _as(world, "bki@example.org").get("/api/incidents?year=2025").json()["incidents"][0]
    assert incident["people_visible"] and incident["people"][0]["name"].startswith("Muster")
    assert _as(world, "bki@example.org", "t:wehr-a2").get("/api/incidents?year=2025").status_code == 200


def test_tenant_role_sees_only_own_wehr(world):
    grant("deputy@example.org", "deputy_lead", world.ids["a1"])
    assert _as(world, "deputy@example.org").get("/api/incidents?year=2025").status_code == 200
    # fremde Wehr: Cookie fällt auf die eigene zurück, nie auf wehr-a2
    other = _as(world, "deputy@example.org", "t:wehr-a2").get("/api/incidents?year=2025")
    assert other.status_code == 200 and other.json()["incidents"][0]["number"] == 1


def test_vg_lead_can_grant_new_roles_but_only_fitting_ones(world):
    grant("vglead@example.org", "vg_lead", world.ids["vg-a"])
    _as(world, "vglead@example.org")
    ok = world.post("/api/admin/memberships", json={"email": "k@example.org", "scope": "vg", "slug": "vg-a",
                                                    "role": "bki"})
    assert ok.status_code == 200
    bad = world.post("/api/admin/memberships", json={"email": "l@example.org", "scope": "vg", "slug": "vg-a",
                                                     "role": "dispatch_lead"})
    assert bad.status_code == 422


def test_kind_change_blocked_by_unfit_membership(world):
    grant("vglead@example.org", "vg_lead", world.ids["vg-a"])
    with tenancy.central() as con:
        with pytest.raises(ValueError, match="Wehrleiter"):
            tenancy.set_vg_kind(con, world.ids["vg-a"], "district")
        tenancy.set_vg_kind(con, world.ids["kreis-d"], "city")
        with pytest.raises(ValueError):
            tenancy.set_vg_kind(con, world.ids["kreis-d"], "nonsense")
    _as(world, "admin@example.org")
    assert world.put("/api/super/vgs/vg-a", json={"slug": "vg-a", "name": "VG A neu"}).status_code == 200


def test_create_vg_with_kind_via_api(world):
    _as(world, "admin@example.org")
    r = world.post("/api/super/vgs", json={"slug": "lk-test", "name": "Landkreis Test", "kind": "district"})
    assert r.status_code == 200 and next(v for v in r.json()["vgs"] if v["slug"] == "lk-test")["kind"] == "district"
    assert world.post("/api/super/vgs", json={"slug": "lk-x", "name": "Landkreis X", "kind": "xx"}).status_code == 422


def test_migration_of_old_database_adds_bks_roles(tmp_path):
    con = sqlite3.connect(tmp_path / "c.db")
    con.row_factory = sqlite3.Row
    db.migrate(con, db.CENTRAL_MIGRATIONS[:-3])
    with_roles = {r["key"] for r in con.execute("SELECT key FROM role")}
    assert "bki" not in with_roles
    db.migrate(con, db.CENTRAL_MIGRATIONS)
    assert {"bki", "deputy_lead", "dispatch_lead"} <= {r["key"] for r in con.execute("SELECT key FROM role")}
    roles = rbac.Roles(con)
    assert rbac.PEOPLE in roles.permissions(roles.find("vg_lead", None).id)
    assert rbac.VG_FEES not in roles.permissions(roles.find("bki", None).id)
    rbac.add_roles(con)                                    # wiederholbar
    assert len([r for r in roles]) == len(list(rbac.Roles(con)))
