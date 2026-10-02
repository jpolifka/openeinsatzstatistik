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


def test_keyword_catalog_codes_are_valid():
    codes = [code for code, _, _ in domain.KEYWORD_CATALOG]
    assert len(codes) == len(set(codes))
    assert all(re.fullmatch(r"[BHGWSU][1-4](\.\d\d)?", code) for code in codes)
    names = {code: name for code, name, _ in domain.KEYWORD_CATALOG}
    assert names["H2.03"] == "Verkehrsunfall"
    assert ".".join(domain.FIRE_ALARM_SYSTEM) in codes and ".".join(domain.FIRE_WATCH) in codes


def test_describe_call_sign():
    assert domain.describe_call_sign("RP WW 01/23-06") == {
        "bos": "Rheinpfalz (Land)", "place": "WW", "station": "01", "code": "23", "number": 6,
        "kind": "Tanklöschfahrzeug 3000", "types": ["TLF 3000", "TLF 16/24Tr", "TLF 16/25"], "label": ""}
    florian = domain.describe_call_sign("FL NR#.ABC 02/41-01")
    assert (florian["bos"], florian["place"], florian["station"], florian["label"]) == ("Florian", "NR#.ABC", "02", "TSF")
    assert domain.describe_call_sign("WW 16/83-01")["label"] == "RTW"
    assert domain.describe_call_sign("FL NR#.LIN") == {} and domain.describe_call_sign(None) == {}
