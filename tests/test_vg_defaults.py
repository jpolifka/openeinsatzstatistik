# -*- coding: utf-8 -*-
"""Vorgaben der VG für ihre Wehren: Vererbung, Abweichungen und die einmalige Übernahme."""
import dataclasses

import pytest

from app import domain, tenancy
from app.tenant_config import TenantConfig
from conftest import CFG, grant, login, make_tenant


def _tenant(slug):
    return tenancy.access_for(None, f"t:{slug}").selected


def _vg_id(slug="vg-a"):
    with tenancy.central() as con:
        return con.execute("SELECT id FROM vg WHERE slug = ?", (slug,)).fetchone()[0]


def _own_settings(slug):
    with _tenant(slug).connection() as con:
        return {r[0] for r in con.execute("SELECT key FROM setting")}


def test_lift_keeps_configured_values_and_fills_unconfigured(data_dir):
    make_tenant("wehr-a1")
    make_tenant("wehr-a2", cfg=dataclasses.replace(CFG, control_center="FL NR#.XYZ", day_hours=(7, 19)))
    make_tenant("wehr-a3", cfg=TenantConfig(name=""))               # noch nichts eingestellt
    with _tenant("wehr-a1").connection() as con:                     # eigener Katalog wie bisher: vollständig
        con.executemany("INSERT INTO keyword (code, name, terms, sort_order) VALUES (?, ?, ?, ?)",
                        [(c, "Kleinbrand" if c == "B1" else n, t, i)
                         for i, (c, n, t) in enumerate(domain.KEYWORD_CATALOG, 1)])
    with tenancy.central() as con:
        con.execute("UPDATE vg SET defaults_lifted = 0")
    tenancy._configs.clear()
    before = {slug: _tenant(slug).config for slug in ("wehr-a1", "wehr-a2")}

    tenancy.lift_vg_defaults()

    # eingestellte Werte bleiben, wie sie waren; ohne eigenen Katalog (Vorlage) gilt künftig der der VG
    assert _tenant("wehr-a1").config == before["wehr-a1"]
    assert _tenant("wehr-a2").config == dataclasses.replace(before["wehr-a2"], keywords=before["wehr-a1"].keywords)
    layer = _tenant("wehr-a1").layer
    assert layer.value("control_center") == CFG.control_center          # Gleichstand: die erste Wehr
    assert layer.settings["places"] == list(CFG.places) and layer.settings["bks_code"] == "NR#.BHÖ"
    assert {k["code"]: k["name"] for k in layer.keyword_list}["B1"] == "Kleinbrand"
    assert _own_settings("wehr-a1") >= {"station", "plan_places"} and "places" not in _own_settings("wehr-a1")
    assert {"control_center", "day_hours"} <= _own_settings("wehr-a2")
    with _tenant("wehr-a1").connection() as con:                     # Katalog gleich der VG: keine Abweichung
        assert con.execute("SELECT COUNT(*) FROM keyword").fetchone()[0] == 0
    fresh = _tenant("wehr-a3").config                                 # übernimmt die Vorgaben
    assert fresh.places == CFG.places and fresh.control_center == CFG.control_center
    assert fresh.plan_places == () and fresh.unit_prefix == CFG.unit_prefix and fresh.unit_marker == ""

    tenancy.lift_vg_defaults()                                        # nur einmal je VG
    assert _tenant("wehr-a2").config.day_hours == (7, 19)


def test_vg_value_is_inherited_until_the_tenant_deviates(data_dir):
    make_tenant("wehr-a1", cfg=TenantConfig(name=""))
    vg_id = _vg_id()
    tenant = _tenant("wehr-a1")
    assert tenant.config.day_hours == (domain.DAY_START_HOUR, domain.DAY_END_HOUR)

    def vg_day_hours(hours):
        with tenancy.central() as con:
            tenancy.save_vg_settings(con, vg_id, {"day_hours": hours})
        tenancy.forget_vg_config(vg_id)

    def tenant_day_hours(hours):
        with tenant.connection() as con:
            tenancy.save_config(con, dataclasses.replace(tenant.config, day_hours=hours), tenant.layer)
        tenancy.forget_config(tenant.slug)

    vg_day_hours((7, 19))
    assert tenant.config.day_hours == (7, 19) and "day_hours" not in _own_settings("wehr-a1")
    tenant_day_hours((8, 20))                                          # Abweichung
    vg_day_hours((5, 17))
    assert tenant.config.day_hours == (8, 20)
    tenant_day_hours((5, 17))                                          # wieder wie die VG: folgt ihr
    assert "day_hours" not in _own_settings("wehr-a1")
    vg_day_hours((6, 18))
    assert tenant.config.day_hours == (6, 18)


def test_bks_code_from_vg_and_station_from_tenant(data_dir):
    make_tenant("wehr-a1", cfg=TenantConfig(name="", unit_marker="FW NR#.ABC 03", unit_prefix="FL NR#.ABC ",
                                            own_prefix="03/"))
    vg_id = _vg_id()
    with tenancy.central() as con:
        tenancy.save_vg_settings(con, vg_id, {"bks_code": "NR#.ABC"})
    tenancy.forget_vg_config(vg_id)
    tenant = _tenant("wehr-a1")
    with tenant.connection() as con:                                   # Kennung wie die VG: nur der Standort
        tenancy.save_config(con, tenant.config, tenant.layer)
        assert tenancy.config_sources(con) == set()
    assert "unit_marker" not in _own_settings("wehr-a1") and "station" in _own_settings("wehr-a1")
    with tenancy.central() as con:
        tenancy.save_vg_settings(con, vg_id, {"bks_code": "NR#.NEU"})
    tenancy.forget_vg_config(vg_id)
    cfg = tenant.config
    assert (cfg.unit_marker, cfg.unit_prefix, cfg.own_prefix) == ("FW NR#.NEU 03", "FL NR#.NEU ", "03/")


def test_new_tenant_inherits_vg_defaults(data_dir):
    make_tenant("wehr-a1", cfg=TenantConfig(name=""))
    with tenancy.central() as con:
        tenancy.save_vg_settings(con, _vg_id(), {"places": ["Musterstadt"], "numbering": "by_date"})
        tenancy.create_tenant(con, "wehr-a2", "Wehr Neu", _vg_id())
    cfg = _tenant("wehr-a2").config
    assert cfg.places == ("Musterstadt",) and cfg.numbering == "by_date"
    assert _own_settings("wehr-a2") <= set(tenancy.TENANT_ONLY)


@pytest.fixture
def client(make_client):
    vg_a, a1 = make_tenant("wehr-a1", "vg-a")
    make_tenant("wehr-a2", "vg-a")
    grant("lead@example.org", "lead", a1)
    grant("vglead@example.org", "vg_lead", vg_a)
    return make_client(login=True)


def test_vg_keyword_catalog_and_tenant_deviation(client):
    login(client, "lead@example.org")
    assert client.get("/api/admin/vgs/vg-a/keywords").status_code == 403
    client.cookies.clear()
    login(client, "vglead@example.org")
    start = client.get("/api/admin/vgs/vg-a/keywords").json()
    assert not start["custom"] and start["deviations"] == {}
    client.put("/api/admin/vgs/vg-a/keywords/B1", json={"name": "Kleinbrand"})
    catalogs = [{k["code"]: k for k in client.get(f"/api/admin/{slug}/keywords").json()["keywords"]}
                for slug in ("wehr-a1", "wehr-a2")]
    assert all(c["B1"]["name"] == "Kleinbrand" and c["B1"]["source"] == "vg" for c in catalogs)
    client.delete("/api/admin/wehr-a1/keywords/B1.01")                 # gilt in Wehr a1 nicht
    client.put("/api/admin/wehr-a1/keywords/B1.99", json={"name": "Eigenes"})
    vg = client.get("/api/admin/vgs/vg-a/keywords").json()
    assert vg["deviations"]["B1.01"] == [{"tenant": "Wehr wehr-a1", "kind": "off"}]
    assert vg["tenant_only"] == ["B1.99"]
    assert "B1.01" in {c for c, _, _ in _tenant("wehr-a1").config.inactive_keywords}
    assert "B1.01" in {c for c, _, _ in _tenant("wehr-a2").config.keywords}
    reset = client.delete("/api/admin/vgs/vg-a/keywords").json()
    assert not reset["custom"]
    assert {k["code"]: k["name"] for k in reset["keywords"]}["B1"] != "Kleinbrand"
