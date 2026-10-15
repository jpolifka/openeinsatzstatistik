# -*- coding: utf-8 -*-
"""Übernahme der Einzel-Installation (DATA_DIR/einsaetze.db) in die mandantenfähige Ablage."""
import os

import pytest

from app import db, legacy, store, tenancy


@pytest.fixture
def old_install(tmp_path, monkeypatch):
    """Datenordner wie vor der Mandantenfähigkeit: nur einsaetze.db (Schema-Stand 2)."""
    monkeypatch.setattr(db, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(tenancy, "ADMIN_EMAILS", {"admin@example.org"})
    monkeypatch.setenv("AUTH_EMAILS", "M.Muster@example.org, e.beispiel@example.org")
    con = db.connect(str(tmp_path / "einsaetze.db"))
    db.migrate(con, db.TENANT_MIGRATIONS[:2])
    for number in (1, 2):
        con.execute("INSERT INTO incident (year, number, started_at, keyword, source) "
                    "VALUES (2025, ?, '2025-01-05T10:00:00', 'H2', 'excel')", (number,))
    con.commit()
    con.close()
    return tmp_path


def test_single_install_becomes_tenant(old_install):
    assert legacy.needs_migration(str(old_install))
    legacy.migrate_single_install(str(old_install))

    assert not legacy.needs_migration(str(old_install))
    assert (old_install / "einsaetze-vor-mandanten.db").exists() and not (old_install / "einsaetze.db").exists()
    with tenancy.central() as con:
        tenant = con.execute("SELECT t.slug, t.name, v.name AS vg FROM tenant t JOIN vg v ON v.id = t.vg_id").fetchone()
        roles = con.execute("SELECT m.email, r.key FROM membership m JOIN role r ON r.id = m.role_id "
                            "ORDER BY m.email").fetchall()
    assert tuple(tenant) == ("rheinbrohl", "Feuerwehr Rheinbrohl", "VG Bad Hönningen")
    assert [tuple(r) for r in roles] == [("e.beispiel@example.org", "lead"), ("m.muster@example.org", "lead")]
    with tenancy.central() as con:                     # Eigenbetrieb: kein AVV nötig, Wehr bleibt nutzbar
        assert con.execute("SELECT status FROM dpa").fetchone()[0] == "not_required"
    assert "rheinbrohl" in tenancy.access_for("m.muster@example.org").tenants
    with db.connection(tenancy.tenant_path("rheinbrohl")) as con:
        assert len(store.load_incidents(con)) == 2
        assert tenancy.load_config(con, "Feuerwehr Rheinbrohl") == legacy.rheinbrohl_config()
        assert {r["name"] for r in con.execute("SELECT name FROM asset")} == {"logo-light", "logo-dark", "icon"}
    assert tenancy.is_allowed("m.muster@example.org")


def test_interrupted_migration_starts_over(old_install, monkeypatch):
    calls = []
    original = tenancy.create_vg

    def fail_once(*args):
        if not calls:
            calls.append(1)
            raise RuntimeError("Abbruch")
        return original(*args)

    monkeypatch.setattr(tenancy, "create_vg", fail_once)
    with pytest.raises(RuntimeError):
        legacy.migrate_single_install(str(old_install))
    assert legacy.needs_migration(str(old_install))     # alte Datei unangetastet, keine Zentrale
    legacy.migrate_single_install(str(old_install))
    with db.connection(tenancy.tenant_path("rheinbrohl")) as con:
        assert len(store.load_incidents(con)) == 2


def test_start_migrates_and_serves(old_install, monkeypatch):
    from fastapi.testclient import TestClient
    from app import auth, main
    monkeypatch.setattr(auth, "BASE_URL", "http://localhost")
    with TestClient(main.app) as client:
        assert client.get("/health").status_code == 200
    assert os.path.exists(old_install / "app.db") and legacy.needs_migration(str(old_install)) is False


def test_auth_emails_without_admin_emails_stop_start(old_install, monkeypatch):
    from fastapi.testclient import TestClient
    from app import main
    monkeypatch.setattr(tenancy, "ADMIN_EMAILS", set())
    with pytest.raises(RuntimeError, match="ADMIN_EMAILS"):
        with TestClient(main.app):
            pass
    assert legacy.needs_migration(str(old_install))
