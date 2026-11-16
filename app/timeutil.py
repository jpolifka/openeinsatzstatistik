# -*- coding: utf-8 -*-
"""Umwandlung von Zeitangaben zwischen PDF, Datenbank (ISO-Text) und Excel."""
import datetime as dt


def parse_iso(text):
    """ISO-Text aus der Datenbank -> datetime (oder None)."""
    return dt.datetime.fromisoformat(text) if text else None


def to_iso(value):
    """datetime -> ISO-Text mit Sekunden (Format der Datenbank)."""
    return value.isoformat(timespec="seconds") if isinstance(value, dt.datetime) else None


def normalize_iso(text):
    """Beliebige ISO-Eingabe (z. B. aus datetime-local) auf das Datenbankformat bringen."""
    return to_iso(parse_iso(text))


def as_time(value):
    """datetime/time -> time; alles andere -> None."""
    if isinstance(value, dt.datetime):
        return value.time()
    return value if isinstance(value, dt.time) else None


def time_text(value):
    """datetime/time -> 'HH:MM:SS' (Format der Fahrzeugzeiten in der Datenbank)."""
    t = as_time(value)
    return t.strftime("%H:%M:%S") if t else None


def parse_time(text):
    """'HH:MM:SS' -> time (oder None). Unlesbare Werte (auch ein ISO-Zeitstempel) ergeben die Uhrzeit bzw. None,
    damit eine fehlerhafte Zeile nicht die ganze Auswertung zum Absturz bringt."""
    if not text:
        return None
    try:
        return dt.time.fromisoformat(text)
    except ValueError:
        try:
            return dt.datetime.fromisoformat(text).time()
        except ValueError:
            return None


def seconds_of_day(value):
    """Sekunden seit Mitternacht für time, datetime oder 'HH:MM:SS'."""
    t = parse_time(value) if isinstance(value, str) else as_time(value)
    if t is None and isinstance(value, str):
        return None            # unlesbarer Text: nicht angegeben (fehlendes Argument bleibt ein Programmierfehler)
    return t.hour * 3600 + t.minute * 60 + t.second


def year_of(start):
    """Einsatzjahr aus dem Beginn (datetime oder ISO-Text); ohne Beginn das laufende Jahr."""
    if isinstance(start, str):
        start = parse_iso(start)
    return start.year if start else dt.date.today().year
