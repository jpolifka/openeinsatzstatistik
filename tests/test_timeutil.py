# -*- coding: utf-8 -*-
"""Zeitumwandlungen: Grundlage für Azeit/Ezeit und die Datenbankformate."""
import datetime as dt

import pytest

from app import timeutil


def test_iso_roundtrip_drops_microseconds():
    value = dt.datetime(2025, 3, 12, 10, 0, 5, 999)
    assert timeutil.to_iso(value) == "2025-03-12T10:00:05"
    assert timeutil.parse_iso("2025-03-12T10:00:05") == dt.datetime(2025, 3, 12, 10, 0, 5)


@pytest.mark.parametrize("empty", [None, "", 0, dt.date(2025, 3, 12), dt.time(10, 0)])
def test_empty_or_foreign_values_become_none(empty):
    assert timeutil.to_iso(empty) is None
    assert timeutil.parse_iso(empty if isinstance(empty, str) or empty is None else "") is None
    assert timeutil.normalize_iso("") is None


def test_normalize_accepts_datetime_local_input():
    assert timeutil.normalize_iso("2025-03-12T10:00") == "2025-03-12T10:00:00"


def test_invalid_iso_text_raises():
    with pytest.raises(ValueError):
        timeutil.parse_iso("kein Datum")


def test_time_text_and_parse_time_roundtrip():
    assert timeutil.time_text(dt.datetime(2025, 3, 12, 23, 59, 59)) == "23:59:59"
    assert timeutil.time_text(dt.time(0, 0)) == "00:00:00"
    assert timeutil.time_text("10:00:00") is None            # nur datetime/time
    assert timeutil.parse_time("00:00:00") == dt.time(0, 0)
    assert timeutil.parse_time(None) is None


def test_seconds_of_day_boundaries():
    assert timeutil.seconds_of_day("00:00:00") == 0
    assert timeutil.seconds_of_day("23:59:59") == 86399
    assert timeutil.seconds_of_day(dt.time(1, 2, 3)) == 3723
    assert timeutil.seconds_of_day(dt.datetime(2025, 3, 30, 2, 30)) == 9000   # Tag der Zeitumstellung: Uhrzeit zählt


def test_seconds_of_day_rejects_missing_value():
    with pytest.raises(AttributeError):
        timeutil.seconds_of_day(None)


def test_midnight_crossing_wraps_modulo_a_day():
    """Wie in Excel: ein Ausrücken nach Mitternacht ergibt positive Minuten ab Beginn (Modulo 24 h)."""
    start, later = timeutil.seconds_of_day("23:50:00"), timeutil.seconds_of_day("00:10:00")
    assert (later - start) % 86400 == 20 * 60


def test_year_of_uses_start_or_current_year():
    assert timeutil.year_of("2024-12-31T23:59:59") == 2024
    assert timeutil.year_of(dt.datetime(2026, 1, 1)) == 2026
    assert timeutil.year_of(None) == dt.date.today().year
