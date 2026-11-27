# -*- coding: utf-8 -*-
"""Rollen einer VG wirken nur in dieser VG – auch nach dem Verschieben einer Wehr."""
import sqlite3

import pytest

from app import db, tenancy
from tests.conftest import make_tenant


def _own_role(con, vg_id):
    return con.execute("INSERT INTO role (key, vg_id, scope, label) VALUES ('custom', ?, 'tenant', 'Eigene Rolle')",
                       (vg_id,)).lastrowid


@pytest.fixture
def setup(data_dir):
    vg_a, tenant = make_tenant("wehr-a1", "vg-a")
    vg_b, _ = make_tenant("wehr-b1", "vg-b")
    with tenancy.central() as con:
        role = _own_role(con, vg_a)
        con.execute("INSERT INTO role_permission (role_id, permission) VALUES (?, 'incidents.view')", (role,))
        tenancy.add_account(con, "x.muster@example.org")
        con.execute("INSERT INTO membership (email, scope, scope_id, role_id) VALUES (?, 'tenant', ?, ?)",
                    ("x.muster@example.org", tenant, role))
    return vg_a, vg_b, tenant, role


def test_trigger_blocks_move_with_foreign_role(setup):
    vg_a, vg_b, tenant, _ = setup
    with tenancy.central() as con, pytest.raises(sqlite3.DatabaseError):
        con.execute("UPDATE tenant SET vg_id = ? WHERE id = ?", (vg_b, tenant))


def test_trigger_blocks_foreign_role_assignment(setup):
    vg_a, vg_b, _, role = setup
    _, other = make_tenant("wehr-b2", "vg-b")
    with tenancy.central() as con, pytest.raises(sqlite3.DatabaseError):
        con.execute("INSERT INTO membership (email, scope, scope_id, role_id) VALUES (?, 'tenant', ?, ?)",
                    ("x.muster@example.org", other, role))


def test_move_endpoint_refuses_and_names_person(setup, make_client):
    client = make_client()
    r = client.put("/api/super/tenants/wehr-a1?confirm=wehr-a1", json={"vg": "vg-b"})
    assert r.status_code == 422
    assert "x.muster@example.org" in r.text
    r = client.put("/api/super/tenants/wehr-a1?confirm=wehr-a1", json={"vg": "vg-a"})   # gleiche VG: nichts zu tun
    assert r.status_code == 200


def test_move_works_after_revoking(setup, make_client):
    _, _, _, role = setup
    with tenancy.central() as con:
        con.execute("DELETE FROM membership WHERE role_id = ?", (role,))
    r = make_client().put("/api/super/tenants/wehr-a1?confirm=wehr-a1", json={"vg": "vg-b"})
    assert r.status_code == 200


def test_access_ignores_stray_foreign_role(setup):
    """Verirrte Zuordnung (Trigger umgangen, z. B. Altbestand) gewährt keine Rechte."""
    _, vg_b, tenant, _ = setup
    with tenancy.central() as con:
        con.execute("DROP TRIGGER tenant_vg_move")
        con.execute("UPDATE tenant SET vg_id = ? WHERE id = ?", (vg_b, tenant))
    a = tenancy.access_for("x.muster@example.org")
    assert "wehr-a1" not in a.tenants


def test_migration_revokes_existing_violations(tmp_path):
    con = db.connect(":memory:")
    db.migrate(con, db.CENTRAL_MIGRATIONS[:-4])
    vg_a = con.execute("INSERT INTO vg (slug, name) VALUES ('vg-a', 'VG A')").lastrowid
    vg_b = con.execute("INSERT INTO vg (slug, name) VALUES ('vg-b', 'VG B')").lastrowid
    t = con.execute("INSERT INTO tenant (slug, name, vg_id) VALUES ('w', 'W', ?)", (vg_b,)).lastrowid
    role = _own_role(con, vg_a)
    tenancy.add_account(con, "x.muster@example.org")
    con.execute("INSERT INTO membership (email, scope, scope_id, role_id) VALUES (?, 'tenant', ?, ?)",
                ("x.muster@example.org", t, role))
    con.commit()
    db.migrate(con, db.CENTRAL_MIGRATIONS)
    assert con.execute("SELECT COUNT(*) FROM membership WHERE role_id = ?", (role,)).fetchone()[0] == 0
    assert con.execute("SELECT 1 FROM role_event WHERE action LIKE 'Zuordnung wegen VG-Wechsel%'").fetchone()
