# -*- coding: utf-8 -*-
"""Gesetzliche Feiertage Rheinland-Pfalz (wie Blatt Feiertage der Einsatzübersicht)."""
import datetime as dt
from functools import lru_cache


def ostersonntag(jahr):
    # Gaußsche Osterformel (Anonymer gregorianischer Algorithmus)
    a, b, c = jahr % 19, jahr // 100, jahr % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    monat = (h + l - 7 * m + 114) // 31
    tag = (h + l - 7 * m + 114) % 31 + 1
    return dt.date(jahr, monat, tag)


@lru_cache(maxsize=None)
def feiertage(jahr):
    o = ostersonntag(jahr)
    t = dt.timedelta
    return {
        dt.date(jahr, 1, 1): "Neujahr",
        o - t(days=2): "Karfreitag",
        o: "Ostersonntag",
        o + t(days=1): "Ostermontag",
        dt.date(jahr, 5, 1): "Tag der Arbeit",
        o + t(days=39): "Christi Himmelfahrt",
        o + t(days=49): "Pfingstsonntag",
        o + t(days=50): "Pfingstmontag",
        o + t(days=60): "Fronleichnam",
        dt.date(jahr, 10, 3): "Tag der Deutschen Einheit",
        dt.date(jahr, 11, 1): "Allerheiligen",
        dt.date(jahr, 12, 25): "1. Weihnachtstag",
        dt.date(jahr, 12, 26): "2. Weihnachtstag",
    }


def ist_wochenende_oder_feiertag(d):
    return d.weekday() >= 5 or d in feiertage(d.year)
