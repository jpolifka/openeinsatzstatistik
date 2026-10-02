# -*- coding: utf-8 -*-
"""
Einsatzbericht-PDF aus dem BKS-Portal RLP lesen.

extract_text() holt den Text aus der PDF, parse_report() wertet ihn aus. Das Ergebnis
enthält nur, was im Bericht steht – abgeleitete Werte (Beginn, EHF, …) ergänzt report.py.
"""
import datetime as dt
import functools
import re

import pdfplumber

# Seite 1 ist zweispaltig; manche Felder sind nur im linken oder rechten Teil eindeutig
COLUMN_SPLIT = 0.495
TIMESTAMP = r"(\d\d\.\d\d\.\d\d \d\d:\d\d:\d\d)"
# Fahrzeugzeile: Funkrufname (alles vor der Stärke, z. B. „FL NR#.ABC 02/45-01“, „RP WW 01/23-06“,
# „H CH 23“; Zeilen ohne Namen wie „- 0 / 0 …“ nicht), Stärke „0 / 1 / 5 / 6 / 2“, dann die Zeiten
VEHICLE_ROW = re.compile(r"^([A-Z].*?)\s+(\d+) / (\d+) / (\d+) / (\d+) / (\d+)\s+(.*)$")
VEHICLE_VALUES = re.compile(TIMESTAMP + r"\d?|(?<!\S)(-)(?!\S)|\b(Ja|Nein)\b")
DISPATCH_NUMBER = re.compile(r"Einsatznummer Leitstelle:\s*(\d+)")
# Kopfzeile mit der berichtenden Einheit, z. B. "FW NR#.ABC 02 Musterstadt Alarmierung: …";
# neuere Berichte nennen sie außerdem als "Feuerwehrhaus: FW NR#.ABC 02 Musterstadt"
UNIT = re.compile(r"^(FW NR#\.\S+ \d\d) (.*?) Alarmierung:", re.M)
STATION = re.compile(r"^Feuerwehrhaus:\s*(FW NR#\.\S+ \d\d)\s*(.*?)(?:\s+Meldebild:.*)?$", re.M)
# Datensätze im BKS-Portal: der Stammdatensatz eines Einsatzes (VG, ohne Einheit) und je Einheit ein
# Haupt- bzw. Nebenbericht, der mit "Datensatz: <ID>" auf den Stammdatensatz verweist
REPORT_KIND = re.compile(r"^(Stammdatensatz|Hauptbericht|Nebenbericht) (\d+)", re.M)
RECORD = re.compile(r"^Datensatz:\s*(\d+)", re.M)
KINDS = {"Stammdatensatz": "master", "Hauptbericht": "main", "Nebenbericht": "secondary"}
PERSON_ROW = re.compile(r"^(\S+) (\S+)(.*?)\s(nein|ja|AGT)\s(\d+)\s*(.*)$")
# Fahrzeug einer Person: voller Funkrufname, z. B. „FL NR#.ABC 02/45-01“ oder „RP WW 01/23-06“
PERSON_VEHICLE = re.compile(r"(?:[A-Z]{2} )?[A-Z][A-Z0-9#.ÄÖÜ]* \d\d/\d\d-\d\d")
PERSON_NOISE = re.compile(PERSON_VEHICLE.pattern + r"|\d\d\.\d\d\.\d\d \d\d:\d\d")
SHORT_CALL_SIGN = re.compile(r"(\d\d/\d\d)-\d\d$")
NOT_A_PERSON = ("Name", "FW", "EINSATZBERICHT")


@functools.lru_cache(maxsize=32)
def _call_sign_pattern(unit_prefix):
    """Funkrufname eines Fahrzeugs der Einheit, z. B. "FL NR#.ABC 02/45-01" -> 02/45."""
    return re.compile("^" + re.escape(unit_prefix) + r"(\d\d/\d\d)-\d\d")


def extract_text(path):
    """Text der ganzen PDF sowie linke und rechte Hälfte von Seite 1."""
    with pdfplumber.open(path) as pdf:
        pages = [p.extract_text() or "" for p in pdf.pages]
        first = pdf.pages[0]
        split = first.width * COLUMN_SPLIT
        left = first.crop((0, 0, split, first.height)).extract_text() or ""
        right = first.crop((split, 0, first.width, first.height)).extract_text() or ""
    return "\n".join(pages), left, right


def _field(text, label):
    m = re.search(re.escape(label) + r":\s*(.*)", text)
    return m.group(1).strip() if m else ""


def _page_one_field(left, right, label):
    """Feld der Einsatzstelle: neuere Berichte führen es links, ältere (2025) rechts."""
    return _field(left, label) or _field(right, label)


def _timestamp(text):
    return dt.datetime.strptime(text, "%d.%m.%y %H:%M:%S") if text not in ("-", "Ja", "Nein") else None


def _parse_keyword(text, report):
    m = re.match(r"([A-Z])(\d)\.(\d\d)", text)
    if m:
        return m.group(1) + m.group(2), m.group(3)
    if "sicherheitswache" in text.lower():
        return "S1", "00"
    report["warnings"].append(f"Stichwort '{text}' nicht erkannt")
    return text, ""


def parse_number(text):
    """Laufende Nr. aus der Einsatzbericht-Nr. "34/26", auch mit Kürzel davor wie "B67/2026" oder "FEZ 36/2026"."""
    m = re.match(r"[A-Za-zÄÖÜäöü]*\s*(\d+)\s*/\s*(\d+)", text)
    return int(m.group(1)) if m else None


def _parse_vehicles(text, report, unit_prefix):
    own_call_sign = _call_sign_pattern(unit_prefix)
    vehicles = []
    for line in text.splitlines():
        m = VEHICLE_ROW.match(line)
        if not m:
            continue
        values = [ts or dash or yes_no for ts, dash, yes_no in VEHICLE_VALUES.findall(m.group(7))]
        if len(values) < 6:
            report["warnings"].append(f"Fahrzeugzeile unvollständig: {line[:60]}")
            values += ["-"] * (6 - len(values))
        alerted, departed, arrived, _deployed, _returned, finished = values[:6]
        call_sign = own_call_sign.search(m.group(1))
        vehicles.append({
            "name": m.group(1), "call_sign": call_sign.group(1) if call_sign else None,
            "crew": int(m.group(5)), "respiratory": int(m.group(6)),
            "alerted": _timestamp(alerted), "departed": _timestamp(departed),
            "arrived": _timestamp(arrived), "finished": _timestamp(finished),
        })
    return vehicles


def _parse_people(text):
    section = text.split("Anwesenheitsliste:", 1)[-1].split("Unterschriften zu Einsatzbericht")[0]
    people = []
    for line in section.splitlines():
        m = PERSON_ROW.match(line)
        if not m or m.group(1) in NOT_A_PERSON:
            continue
        middle = m.group(3)
        vehicle = PERSON_VEHICLE.search(middle)
        # vehicle: Kurzname wie früher (z. B. 02/45); den Block der Wehr bestimmt report.derive
        people.append({"last_name": m.group(1), "first_name": m.group(2),
                       "vehicle_name": vehicle.group(0) if vehicle else None,
                       "vehicle": SHORT_CALL_SIGN.search(vehicle.group(0)).group(1) if vehicle else None,
                       "role": PERSON_NOISE.sub("", middle).strip()})
    return people


def parse_report(full, left, right, filename, unit_prefix):
    """Felder, Fahrzeugtabelle und Anwesenheitsliste aus dem Berichtstext.

    unit_prefix: Anfang der Fahrzeugnamen der Einheit (TenantConfig.unit_prefix); nur deren Fahrzeuge
    bekommen einen Funkrufnamen (call_sign).
    """
    report = {"filename": filename, "source": "pdf", "warnings": []}
    number_text = _field(full, "Einsatzbericht-Nr.")
    report["number"] = parse_number(number_text)
    report["number_text"] = number_text
    m = DISPATCH_NUMBER.search(full)
    report["dispatch_number"] = m.group(1) if m else None
    m = UNIT.search(full) or STATION.search(full)
    report["unit"], report["unit_name"] = (m.group(1), m.group(2).strip()) if m else (None, None)
    m = REPORT_KIND.search(full)
    report["report_kind"], report["bks_report_id"] = (KINDS[m.group(1)], m.group(2)) if m else (None, None)
    m = RECORD.search(full)
    report["bks_record_id"] = m.group(1) if m else \
        report["bks_report_id"] if report["report_kind"] == "master" else None

    keyword_text = _field(left, "Einsatzstichwort") or _field(full, "Einsatzstichwort")
    report["keyword"], report["subcode"] = _parse_keyword(keyword_text, report)
    report["reported_as"] = _page_one_field(left, right, "Meldebild")
    report["town"] = _page_one_field(left, right, "Einsatzstelle - Ort")
    report["district"] = re.sub(r"\s*\(.*\)\s*$", "", _page_one_field(left, right, "Einsatzstelle - Ortsteil"))
    report["street"] = _page_one_field(left, right, "Einsatzstelle - Straße")
    report["building"] = _page_one_field(left, right, "Einsatzstelle - Objekt")
    report["incident_commander"] = _field(full, "Einsatzleiter")
    m = re.search(r"Zeitpunkt der Alarmierung der ersten Einheit:\s*(\d\d\.\d\d\.\d{4} \d\d:\d\d)", full)
    report["first_alarm"] = dt.datetime.strptime(m.group(1), "%d.%m.%Y %H:%M") if m else None

    report["vehicles"] = _parse_vehicles(full, report, unit_prefix)
    report["people"] = _parse_people(full)
    return report


def read_report(path, filename, unit_prefix):
    return parse_report(*extract_text(path), filename, unit_prefix)
