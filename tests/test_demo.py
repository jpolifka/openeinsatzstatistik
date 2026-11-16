# -*- coding: utf-8 -*-
from app import demo, tenancy


def test_demo_seed_creates_two_tenants_and_is_repeatable(data_dir):
    assert demo.seed() is True
    assert demo.seed() is False                       # zweiter Lauf legt nichts doppelt an
    with tenancy.central() as con:
        assert [r["slug"] for r in con.execute("SELECT slug FROM tenant ORDER BY slug")] == ["musterstadt", "nebenhausen"]
    from app import db, store
    with db.connection(tenancy.tenant_path("musterstadt")) as con:
        years = {r["year"]: r["n"] for r in con.execute("SELECT year, COUNT(*) AS n FROM incident GROUP BY year")}
        assert years == {2025: 118, 2026: 104}
        assert con.execute("SELECT COUNT(*) FROM attendance").fetchone()[0] > 1000
        # keine Nummer doppelt, jedes Jahr lückenlos ab 1
        assert store.next_number(con, 2025) == 119


def test_demo_names_are_placeholders(data_dir):
    demo.seed()
    from app import db
    with db.connection(tenancy.tenant_path("musterstadt")) as con:
        names = [r["last_name"] for r in con.execute("SELECT last_name FROM member")]
    assert set(names) <= set(demo.LAST_NAMES)
