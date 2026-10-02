# -*- coding: utf-8 -*-
import dataclasses
import os

import pytest

from app import db, domain, tenancy
from app.tenant_config import TenantConfig, Vehicle
from conftest import CFG, grant, make_tenant


def test_create_tenant_with_own_database(data_dir):
    _, tenant_id = make_tenant("wehr-a1")
    path = tenancy.tenant_path("wehr-a1")
    assert os.path.exists(path)
    with db.connection(path) as con:
        assert con.execute("PRAGMA user_version").fetchone()[0] == len(db.TENANT_MIGRATIONS)
        assert tenancy.load_config(con, "Wehr wehr-a1") == dataclasses.replace(CFG, name="Wehr wehr-a1")
    with pytest.raises(ValueError):
        make_tenant("wehr-a1")


@pytest.mark.parametrize("slug", ["A1", "-a", "a", "a_b", "ä", "a" * 41, ""])
def test_slug_is_checked(data_dir, slug):
    with pytest.raises(ValueError):
        make_tenant(slug)


def test_config_roundtrip_with_fleet_and_keywords(data_dir):
    make_tenant("wehr-a1")
    cfg = TenantConfig(name="Wehr wehr-a1", fleet=(Vehicle("03/11", "HLF 20", "2024-01-01", None, None, True),
                                                   Vehicle("03/44", "", None, "2025-06-30", "03/11", False)),
                       substitutes={"03/90": "03/11"}, unit_prefix="FL NR#.ABC ", own_prefix="03/",
                       places=(("Musterstadt", "muster"),), plan_places=("Musterstadt",), day_hours=(7, 19),
                       keywords=(("B1", "Grundstufe", ""), ("B1.99", "Neues Stichwort", "Test")))
    with db.connection(tenancy.tenant_path("wehr-a1")) as con:
        tenancy.save_config(con, cfg)
        assert tenancy.load_config(con, cfg.name).keywords == domain.KEYWORD_CATALOG   # ohne eigene Liste: Vorlage
        tenancy.save_config(con, cfg, keywords=True)
        assert tenancy.load_config(con, cfg.name) == cfg


def test_config_cache_follows_saves_and_renames(data_dir):
    make_tenant("wehr-a1")
    tenant = tenancy.access_for(None).selected
    assert tenant.config.vehicles == CFG.vehicles
    with tenant.connection() as con:
        tenancy.save_config(con, dataclasses.replace(tenant.config, fleet=(Vehicle("02/99"),)))
    assert tenant.config.vehicles == CFG.vehicles          # noch zwischengespeichert …
    tenancy.forget_config("wehr-a1")
    assert tenant.config.vehicles == ("02/99",)            # … bis zum Verwerfen
    with tenancy.central() as con:
        con.execute("UPDATE tenant SET name = 'Neuer Name'")
    assert tenancy.access_for(None).selected.config.name == "Neuer Name"


def test_is_allowed(data_dir, monkeypatch):
    monkeypatch.setattr(tenancy, "ADMIN_EMAILS", {"admin@example.org"})
    vg_id, tenant_id = make_tenant("wehr-a1")
    grant("lead@example.org", "lead", tenant_id)
    grant("vg@example.org", "vg_stats", vg_id)
    assert tenancy.is_allowed(" Admin@Example.org ")
    assert tenancy.is_allowed("lead@example.org") and tenancy.is_allowed("vg@example.org")
    assert not tenancy.is_allowed("fremd@example.org") and not tenancy.is_allowed("")
    with tenancy.central() as con:
        con.execute("UPDATE tenant SET active = 0")
    assert not tenancy.is_allowed("lead@example.org") and not tenancy.is_allowed("vg@example.org")


def test_permissions_add_up_over_roles(data_dir):
    vg_id, a1 = make_tenant("wehr-a1")
    make_tenant("wehr-a2")
    grant("x@example.org", "viewer", a1)
    grant("x@example.org", "vg_stats", vg_id)
    access = tenancy.access_for("x@example.org")
    assert access.tenants["wehr-a1"].permissions == {"stats"} and access.tenants["wehr-a2"].permissions == {"stats"}
    grant("x@example.org", "editor", a1)                    # ersetzt die Rolle in derselben Wehr
    access = tenancy.access_for("x@example.org")
    assert access.tenants["wehr-a1"].permissions == {"stats", "incidents", "people", "write"}
    assert not access.superadmin and tenancy.access_for(None).superadmin
