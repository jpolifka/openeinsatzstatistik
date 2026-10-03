"""Dateisystemausfälle: nur synthetische Wehren im isolierten Datenordner."""
from pathlib import Path
from app import db, store, tenancy, tenant_lifecycle
from conftest import make_tenant


def test_archive_failure_keeps_registry_and_recovers(data_dir, monkeypatch):
    make_tenant("wehr-a")
    with db.connection(tenancy.tenant_path("wehr-a")) as con:
        store.create_incident(con, {"number": 1, "started_at": "2025-03-12T10:00:00",
                                    "description": "Synthetischer Restore-Test"}, "pdf")
    original = tenant_lifecycle.shutil.move
    with tenancy.central() as con:
        tenant_lifecycle.begin_archive(con, "wehr-a", None)
    def fail(*args):
        raise OSError("simulierter Dateisystemfehler")
    monkeypatch.setattr(tenant_lifecycle.shutil, "move", fail)
    assert not tenant_lifecycle.finish_archive("wehr-a")
    with tenancy.central() as con:
        assert con.execute("SELECT active FROM tenant WHERE slug = 'wehr-a'").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM tenant_archive").fetchone()[0] == 1
    assert Path(tenancy.tenant_path("wehr-a")).exists()
    monkeypatch.setattr(tenant_lifecycle.shutil, "move", original)
    tenancy.setup()
    with tenancy.central() as con:
        assert not con.execute("SELECT 1 FROM tenant WHERE slug = 'wehr-a'").fetchone()
        assert not con.execute("SELECT 1 FROM tenant_archive").fetchone()
    archives = list((data_dir / "deleted").glob("wehr-a-*/einsaetze.db"))
    assert len(archives) == 1
    with db.connection(str(archives[0])) as con:
        assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        with db.connection(str(data_dir / "restore-copy.db")) as restored:
            con.backup(restored)
            db.migrate(restored)
            assert store.load_incidents(restored)[0]["description"] == "Synthetischer Restore-Test"


def test_crash_after_move_finishes_without_recreating_source(data_dir):
    make_tenant("wehr-a")
    with tenancy.central() as con:
        tenant_lifecycle.begin_archive(con, "wehr-a", None)
        target = con.execute("SELECT target FROM tenant_archive").fetchone()[0]
    archived = data_dir / "deleted" / target
    archived.parent.mkdir()
    Path(tenancy.tenant_path("wehr-a")).parent.rename(archived)
    tenancy.setup()
    assert not Path(tenancy.tenant_path("wehr-a")).exists()
    assert (archived / "einsaetze.db").exists()


def test_rolled_back_creation_is_preserved_and_slug_reusable(data_dir):
    with tenancy.central() as con:
        vg = tenancy.create_vg(con, "vg-a", "VG Muster")
    try:
        with tenancy.central() as con:
            tenancy.create_tenant(con, "wehr-a", "Wehr Muster", vg)
            raise RuntimeError("Fehler vor Commit")
    except RuntimeError:
        pass
    tenancy.setup()
    assert len(list((data_dir / "deleted").glob("incomplete-wehr-a-*/einsaetze.db"))) == 1
    with tenancy.central() as con:
        tenancy.create_tenant(con, "wehr-a", "Wehr Muster", vg)
    tenancy.setup()
    assert Path(tenancy.tenant_path("wehr-a")).exists()
