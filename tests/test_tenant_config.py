# -*- coding: utf-8 -*-
import dataclasses
import datetime as dt

from app import domain
from app.tenant_config import TenantConfig, Vehicle
from conftest import CFG


def test_daytime_excludes_boundaries_like_excel():
    assert not CFG.is_daytime(dt.time(6, 0, 0))
    assert CFG.is_daytime(dt.time(6, 0, 1))
    assert CFG.is_daytime(dt.time(17, 59, 59))
    assert not CFG.is_daytime(dt.time(18, 0, 0))


def test_daytime_until_midnight():
    """Tag bis 24 Uhr ist zulässig (Einstellungen) und darf nicht an dt.time(24) scheitern."""
    late = dataclasses.replace(CFG, day_hours=(6, 24))
    assert late.is_daytime(dt.time(23, 59, 59)) and not late.is_daytime(dt.time(6, 0))


def test_area_by_name_prefix():
    assert CFG.area_of("Altenau-Nord") == "Altenau"
    assert CFG.area_of("Bad Neustadt") == "Bad Neustadt"
    assert CFG.area_of("altenau") == "Altenau"
    assert CFG.area_of("Rheinbreitbach") == domain.OTHER_AREA       # früher über „rhein“ fälschlich Altenau
    assert CFG.area_of("Linz") == domain.OTHER_AREA
    assert CFG.area_of(None) == domain.OTHER_AREA


def test_places_with_old_name_prefix_load_as_names(con):
    from app import tenancy
    con.execute("INSERT INTO setting (key, value) VALUES ('places', ?)", ('[["Musterstadt", "muster"]]',))
    assert tenancy.load_config(con, "A").places == ("Musterstadt",)


def test_plan_relevance():
    assert CFG.is_plan_relevant({"keyword": "B2", "place": "Probenhausen"})
    assert not CFG.is_plan_relevant({"keyword": "B1", "place": "Probenhausen"})
    assert not CFG.is_plan_relevant({"keyword": "B2", "place": "Testheim"})


def test_substitute_label():
    assert CFG.substitute_label("FL NR#.MUS 01/23-01", "02/45") == "01/23-01"
    assert CFG.substitute_label("FL NR#.MUS 02/45-01", "02/45") is None
    assert CFG.substitute_label(None, "02/45") is None


def test_rules_follow_the_tenant():
    other = TenantConfig(name="Feuerwehr Musterstadt", fleet=(Vehicle("03/11"), Vehicle("03/44", in_plan_crew=False)),
                         unit_prefix="FL NR#.ABC ", own_prefix="03/", places=("Musterstadt",),
                         plan_places=("Musterstadt",), plan_min_level=3, day_hours=(7, 19))
    assert other.vehicles == ("03/11", "03/44") and other.excluded_from_plan_crew == {"03/44"}
    assert other.own_vehicle_prefix == "FL NR#.ABC 03/"
    assert other.area_of("Altenau") == domain.OTHER_AREA
    assert not other.is_plan_relevant({"keyword": "B2", "place": "Musterstadt"})
    assert other.is_plan_relevant({"keyword": "B3", "place": "Musterstadt"})
    assert other.is_daytime(dt.time(18, 30)) and not other.is_daytime(dt.time(6, 30))
    assert other.client_config()["vehicles"] == ["03/11", "03/44"]


def test_vehicle_service_period():
    v = Vehicle("02/45", in_service_from="2024-03-01", in_service_until="2025-06-30")
    assert not v.in_service_on(dt.date(2024, 2, 29)) and v.in_service_on(dt.date(2024, 3, 1))
    assert v.in_service_on(dt.date(2025, 6, 30)) and not v.in_service_on(dt.date(2025, 7, 1))
    assert v.in_service_during(2024) and v.in_service_during(2025) and not v.in_service_during(2026)
    assert Vehicle("02/45").in_service_on(dt.date(1990, 1, 1))
