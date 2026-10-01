# -*- coding: utf-8 -*-
"""Gesetzliche Feiertage Rheinland-Pfalz (wie Blatt Feiertage der Einsatzübersicht)."""
import datetime as dt
from functools import lru_cache


def easter_sunday(year):
    # Gaußsche Osterformel (Anonymer gregorianischer Algorithmus)
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return dt.date(year, month, day)


@lru_cache(maxsize=None)
def holidays(year):
    easter = easter_sunday(year)
    days = dt.timedelta
    return {
        dt.date(year, 1, 1): "Neujahr",
        easter - days(2): "Karfreitag",
        easter: "Ostersonntag",
        easter + days(1): "Ostermontag",
        dt.date(year, 5, 1): "Tag der Arbeit",
        easter + days(39): "Christi Himmelfahrt",
        easter + days(49): "Pfingstsonntag",
        easter + days(50): "Pfingstmontag",
        easter + days(60): "Fronleichnam",
        dt.date(year, 10, 3): "Tag der Deutschen Einheit",
        dt.date(year, 11, 1): "Allerheiligen",
        dt.date(year, 12, 25): "1. Weihnachtstag",
        dt.date(year, 12, 26): "2. Weihnachtstag",
    }


def is_weekend_or_holiday(day: dt.date):
    return day.weekday() >= 5 or day in holidays(day.year)
