# -*- coding: utf-8 -*-
from app import db, demo, fees, tenancy


def test_demo_seed_creates_two_configured_tenants_without_incidents_and_is_repeatable(data_dir):
    assert demo.seed() is True
    assert demo.seed() is False                       # zweiter Lauf legt nichts doppelt an
    with tenancy.central() as con:
        assert [r["slug"] for r in con.execute("SELECT slug FROM tenant ORDER BY slug")] == ["musterstadt", "nebenhausen"]
        vg_id = con.execute("SELECT id FROM vg").fetchone()[0]
        assert len(fees.schedules(con, vg_id)) == 1
        layer = tenancy.load_vg_layer(con, vg_id)
    assert layer.value("bks_code") == "NR#.MUS"
    assert tuple(layer.value("places")) == demo.PLACES and tuple(layer.value("response_limits")) == (10, 15)
    for slug, _name, station, fleet, people in demo.WEHREN:
        with db.connection(tenancy.tenant_path(slug)) as con:
            cfg = tenancy.load_config(con, slug, layer)
            assert con.execute("SELECT COUNT(*) FROM incident").fetchone()[0] == 0
            assert con.execute("SELECT COUNT(*) FROM member").fetchone()[0] == len(people)
        assert cfg.unit_marker == f"FW NR#.MUS {station}" and len(cfg.fleet) == len(fleet)
        assert cfg.places == demo.PLACES and cfg.response_limits == (10, 15)


def test_demo_names_are_placeholders(data_dir):
    demo.seed()
    placeholders = {"Fiktiv", "Beispiel", "Muster", "Probe", "Demo", "Sample", "Dummy", "Platzhalter", "Erfunden", "Test"}
    with db.connection(tenancy.tenant_path("musterstadt")) as con:
        names = [r["last_name"] for r in con.execute("SELECT last_name FROM member")]
    assert names and set(names) <= placeholders
