# -*- coding: utf-8 -*-
"""
Einsatzbericht als Excel-Export aus dem BKS-Portal RLP lesen.

Gegenstück zu pdf_report: read_workbook() holt die Blätter, parse_report() liefert dasselbe Ergebnis wie
pdf_report.parse_report – abgeleitete Werte ergänzt report.py.

Aufbau des Exports: Blatt „Einsatzbericht“ (eine Zeile je Bericht, Spalten wie die Felder der PDF),
„Ausger. Fahrzeuge und Personen“ (Fahrzeugtabelle) und „Anwesenheitsliste“. Die Unterblätter verweisen
nicht auf den Bericht, deshalb wird nur ein Bericht je Datei gelesen. In der Anwesenheitsliste stehen die
Werte eine Spalte rechts von ihrer Überschrift; die Spalten werden deshalb am Inhalt ausgerichtet.
"""
import datetime as dt
import io
import re
import zipfile

import openpyxl
from openpyxl.utils.exceptions import InvalidFileException

from app.bks_common import (KINDS, PERSON_VEHICLE, SHORT_CALL_SIGN, _call_sign_pattern, _parse_keyword,
                            clean_alarm_system, clean_tactic, parse_number)

MAIN_SHEET = "Einsatzbericht"
VEHICLE_SHEET = "Ausger. Fahrzeuge"
PEOPLE_SHEET = "Anwesenheitsliste"
# „FW NR#.ABC 02 Musterstadt“ -> Einheit und Name
STATION = re.compile(r"^(FW NR#\.\S+ \d\d)\s*(.*)$")
TIME_FORMATS = ("%d.%m.%y %H:%M:%S", "%d.%m.%Y %H:%M:%S", "%d.%m.%y %H:%M", "%d.%m.%Y %H:%M")
YES_NO = ("ja", "nein", "agt")


# Ein Bericht hat wenige hundert Zeilen; mehr deutet auf eine fremde oder präparierte Datei
MAX_UNPACKED_BYTES = 50 * 1024 * 1024
MAX_ROWS = 5000
MAX_COLUMNS = 128
MAX_SHEETS = 32


def read_workbook(source):
    """Blätter der Arbeitsmappe (Pfad oder Bytes) -> {blattname: [zeilen]}; Zeilen als Tupel ohne Leerzeilen."""
    source = io.BytesIO(source) if isinstance(source, bytes) else source
    try:
        with zipfile.ZipFile(source) as archive:     # xlsx ist eine ZIP-Datei: entpackte Größe vorab prüfen
            if sum(i.file_size for i in archive.infolist()) > MAX_UNPACKED_BYTES:
                raise ValueError("Die Excel-Datei ist zu groß für einen Einsatzbericht.")
        wb = openpyxl.load_workbook(source, read_only=True, data_only=True)
    except (InvalidFileException, zipfile.BadZipFile, KeyError, OSError):
        raise ValueError("Keine gültige Excel-Datei (xlsx).")
    try:
        if len(wb.worksheets) > MAX_SHEETS:
            raise ValueError("Die Excel-Datei hat zu viele Tabellenblätter für einen Einsatzbericht.")
        return {ws.title: _rows(ws) for ws in wb.worksheets}
    finally:
        wb.close()


def _rows(ws):
    if ws.max_column and ws.max_column > MAX_COLUMNS:
        raise ValueError("Die Excel-Datei hat zu viele Spalten für einen Einsatzbericht.")
    rows = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i >= MAX_ROWS:
            raise ValueError("Die Excel-Datei hat zu viele Zeilen für einen Einsatzbericht.")
        if any(c not in (None, "") for c in row):
            rows.append(row)
    return rows


def _sheet(sheets, prefix):
    return next((rows for title, rows in sheets.items() if title.startswith(prefix)), [])


def _text(value):
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


def _int(value):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _count(row, *titles, prefix=False):
    """Summe der Zähler aus den Spalten (Überschrift oder Anfang der Überschrift); None, wenn alle leer sind."""
    values = [v for title, v in row.items() if _text(v) and any(
        _text(title).startswith(t) if prefix else _text(title) == t for t in titles)]
    return sum(_int(v) for v in values) if values else None


def _timestamp(value):
    if isinstance(value, dt.datetime):
        return value
    text = _text(value)
    for fmt in TIME_FORMATS:
        try:
            return dt.datetime.strptime(text, fmt)
        except ValueError:
            pass
    return None


def _records(rows):
    """Zeilen eines Blatts als Dicts nach den Überschriften der ersten Zeile."""
    if not rows:
        return []
    header = [_text(h) for h in rows[0]]
    return [dict(zip(header, row)) for row in rows[1:]]


def _report_kind(row):
    text = _text(row.get("Haupt-/Nebenbericht"))
    kind = next((code for label, code in KINDS.items() if text.startswith(label)), None)
    if not kind and not _text(row.get("Feuerwehrhaus")):
        kind = "master"  # Stammdatensatz der VG: ohne Einheit und Berichtsart
    return kind


def _parse_vehicles(rows, unit_prefix):
    own_call_sign = _call_sign_pattern(unit_prefix)
    vehicles = []
    for row in _records(rows):
        name = _text(row.get("Fahrzeuge"))
        if not name:
            continue
        call_sign = own_call_sign.search(name)
        vehicles.append({
            "name": name, "call_sign": call_sign.group(1) if call_sign else None,
            "crew": _int(row.get("Gesamt")), "respiratory": _int(row.get("AGT")),
            "deployed": {"1": 1, "ja": 1, "0": 0, "nein": 0}.get(_text(row.get("Eingesetzt")).lower()),
            "alerted": _timestamp(row.get("Alarmiert")), "departed": _timestamp(row.get("Ausrücken")),
            "arrived": _timestamp(row.get("Eintreffen an E-Stelle")), "finished": _timestamp(row.get("Einsatzende")),
        })
    return vehicles


def _people_offset(rows, header):
    """Versatz der Werte gegenüber den Überschriften (im Export bisher 1): erkannt an der Spalte mit
    dem Fahrzeug, ersatzweise an der Spalte mit ja/nein (AGT)."""
    for title, matches in (("Fahrzeug", lambda v: bool(PERSON_VEHICLE.fullmatch(v))),
                           ("AGT", lambda v: v.lower() in YES_NO)):
        if title not in header:
            continue
        col = header.index(title)
        for offset in (0, 1):
            if any(col + offset < len(row) and matches(_text(row[col + offset])) for row in rows[1:]):
                return offset
    return 0


def _parse_people(rows):
    if not rows:
        return []
    header = [_text(h) for h in rows[0]]
    offset = _people_offset(rows, header)

    def cell(row, title):
        col = header.index(title) + (offset if title not in ("Name", "Vorname") else 0) if title in header else None
        return _text(row[col]) if col is not None and col < len(row) else ""

    people = []
    for row in rows[1:]:
        last_name, first_name = cell(row, "Name"), cell(row, "Vorname")
        if not last_name:
            continue
        vehicle = cell(row, "Fahrzeug")
        vehicle = vehicle if PERSON_VEHICLE.fullmatch(vehicle) else ""
        people.append({"last_name": last_name, "first_name": first_name,
                       "vehicle_name": vehicle or None,
                       "vehicle": SHORT_CALL_SIGN.search(vehicle).group(1) if vehicle else None,
                       "role": cell(row, "Funktion"),
                       "agt": cell(row, "AGT").lower() in ("ja", "agt"), "agt_min": _int(cell(row, "Min (AGT)"))})
    return people


def parse_report(sheets, filename, unit_prefix):
    """Felder, Fahrzeugtabelle und Anwesenheitsliste aus dem Excel-Export (wie pdf_report.parse_report)."""
    main_rows = _records(_sheet(sheets, MAIN_SHEET))
    if not main_rows:
        raise ValueError("Keine Einsatzbericht-Datei aus dem BKS-Portal (Blatt „Einsatzbericht“ fehlt oder ist leer).")
    if len(main_rows) > 1:
        raise ValueError("Die Datei enthält mehrere Berichte – bitte jeden Bericht einzeln exportieren.")
    row = main_rows[0]
    report = {"filename": filename, "source": "bks_xlsx", "warnings": []}
    report["number_text"] = _text(row.get("Einsatzbericht-Nr."))
    report["number"] = parse_number(report["number_text"])
    report["dispatch_number"] = _text(row.get("Einsatznummer Leitstelle")) or None
    m = STATION.match(_text(row.get("Feuerwehrhaus")))
    report["unit"], report["unit_name"] = (m.group(1), m.group(2).strip()) if m else (None, None)
    report["report_kind"] = _report_kind(row)
    report["bks_report_id"] = _text(row.get("ID")) or None
    report["bks_record_id"] = _text(row.get("Datensatz")) or \
        (report["bks_report_id"] if report["report_kind"] == "master" else None)

    report["keyword"], report["subcode"] = _parse_keyword(_text(row.get("Einsatzstichwort")), report)
    report["reported_as"] = _text(row.get("Meldebild"))
    report["town"] = _text(row.get("Einsatzstelle - Ort"))
    report["district"] = re.sub(r"\s*\(.*\)\s*$", "", _text(row.get("Einsatzstelle - Ortsteil")))
    report["street"] = _text(row.get("Einsatzstelle - Straße"))
    report["building"] = _text(row.get("Einsatzstelle - Objekt"))
    report["incident_commander"] = _text(row.get("Einsatzleiter"))
    report["first_alarm"] = _timestamp(row.get("Zeitpunkt der Alarmierung der ersten Einheit"))

    report["abort_reason"] = _text(row.get("Einsatzabbruch")) or None
    report["alarm_system"] = clean_alarm_system(_text(row.get("Nummer der Gefahrenmeldeanlage")))
    report["tactic"] = clean_tactic(_text(row.get("Einatztaktik")) or _text(row.get("Einsatztaktik")))
    report["fire_controlled_at"] = _timestamp(row.get("Brand unter Kontrolle"))
    report["fire_out_at"] = _timestamp(row.get("Feuer aus"))
    report["fire_watch_until"] = _timestamp(row.get("Brandwache gestellt bis"))
    report["rescued"] = _count(row, "Menschenrettung", prefix=True)
    report["rescued_animals"] = _count(row, "Rettung von Großvieh", "Rettung von Kleinvieh")
    report["injured"] = _count(row, "Verletzte andere Personen")
    report["injured_firefighters"] = _count(row, "Verletzte Feuerwehrangehörige")
    report["deceased"] = _count(row, "Verstorbene andere Personen", "Verstorbene Feuerwehrangehörige")

    report["vehicles"] = _parse_vehicles(_sheet(sheets, VEHICLE_SHEET), unit_prefix)
    report["people"] = _parse_people(_sheet(sheets, PEOPLE_SHEET))
    return report


def read_report(source, filename, unit_prefix):
    return parse_report(read_workbook(source), filename, unit_prefix)
