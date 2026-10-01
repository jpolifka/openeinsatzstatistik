# -*- coding: utf-8 -*-
import datetime as dt
import re

from app import domain
from app.holidays import easter_sunday, is_weekend_or_holiday


def test_easter_sunday():
    assert easter_sunday(2025) == dt.date(2025, 4, 20)
    assert easter_sunday(2026) == dt.date(2026, 4, 5)


def test_weekend_or_holiday():
    assert is_weekend_or_holiday(dt.date(2026, 6, 4))        # Fronleichnam (Donnerstag)
    assert is_weekend_or_holiday(dt.date(2026, 9, 26))       # Samstag
    assert not is_weekend_or_holiday(dt.date(2026, 9, 30))   # Mittwoch


def test_keyword_parts():
    assert domain.category_of("H2") == "H"
    assert domain.alarm_level("H2") == 2
    assert domain.alarm_level("S") is None
    assert domain.alarm_level(None) is None


def test_daytime_excludes_boundaries_like_excel():
    assert not domain.is_daytime(dt.time(6, 0, 0))
    assert domain.is_daytime(dt.time(6, 0, 1))
    assert domain.is_daytime(dt.time(17, 59, 59))
    assert not domain.is_daytime(dt.time(18, 0, 0))


def test_area_by_name_prefix():
    assert domain.area_of("Rheinbrohl-Nord") == "Rheinbrohl"
    assert domain.area_of("Bad Hönningen") == "Bad Hönningen"
    assert domain.area_of("Linz") == domain.OTHER_AREA


def test_plan_relevance():
    assert domain.is_plan_relevant({"keyword": "B2", "place": "Hammerstein"})
    assert not domain.is_plan_relevant({"keyword": "B1", "place": "Hammerstein"})
    assert not domain.is_plan_relevant({"keyword": "B2", "place": "Leutesdorf"})


def test_substitute_label():
    assert domain.substitute_label("FL NR#.BHÖ 01/23-01", "02/45") == "01/23-01"
    assert domain.substitute_label("FL NR#.BHÖ 02/45-01", "02/45") is None
    assert domain.substitute_label(None, "02/45") is None


def test_keyword_catalog_codes_are_valid():
    codes = [code for code, _ in domain.KEYWORD_CATALOG]
    assert len(codes) == len(set(codes))
    assert all(re.fullmatch(r"[BHGWSU][1-4](\.\d\d)?", code) for code in codes)
    assert dict(domain.KEYWORD_CATALOG)["H2.03"] == "Verkehrsunfall"
    assert ".".join(domain.FIRE_ALARM_SYSTEM) in codes and ".".join(domain.FIRE_WATCH) in codes
