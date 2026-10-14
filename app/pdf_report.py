# -*- coding: utf-8 -*-
"""
Einsatzbericht-PDF aus dem BKS-Portal RLP lesen.

extract_text() holt den Text aus der PDF, parse_report() wertet ihn aus. Das Ergebnis
enthält nur, was im Bericht steht – abgeleitete Werte (Beginn, EHF, …) ergänzt report.py.
"""
import datetime as dt
import re

import pdfplumber

from app.bks_common import (KINDS, PERSON_VEHICLE, SHORT_CALL_SIGN, TACTICS, _call_sign_pattern, _parse_keyword,
                            clean_alarm_system, parse_number)

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
PERSON_ROW = re.compile(r"^(\S+) (\S+)(.*?)\s(nein|ja|AGT)\s(\d+)\s*(.*)$")
# Fahrzeug einer Person: voller Funkrufname, z. B. „FL NR#.ABC 02/45-01“ oder „RP WW 01/23-06“
PERSON_NOISE = re.compile(PERSON_VEHICLE.pattern + r"|\d\d\.\d\d\.\d\d \d\d:\d\d")
NOT_A_PERSON = ("Name", "FW", "EINSATZBERICHT")
ALARM_SYSTEM = re.compile(r"Nummer der Gefahrenmeldeanlage:\s*(\S+)")
TACTIC = re.compile(r"Ein(?:sa|a)tztaktik:\s*(" + "|".join(TACTICS) + ")", re.I)
FIRE_TIMES = {"fire_controlled_at": "Brand unter Kontrolle", "fire_out_at": "Feuer aus",
              "fire_watch_until": "Brandwache gestellt bis"}
# Zähler im Bericht: Menschenrettung je Verfahren, Tiere, Verletzte und Verstorbene (nur angegebene Zeilen)
RESCUE = re.compile(r"(Menschenrettung (?:über|mit) [^:\n]{1,50}):\s*(\d+)")
ANIMALS = re.compile(r"(Rettung von (?:Groß|Klein)vieh):\s*(\d+)")
INJURED = re.compile(r"(Verletzte andere Personen):\s*(\d+)", re.I)
INJURED_FIREFIGHTERS = re.compile(r"(Verletzte Feuerwehrangehörige):\s*(\d+)", re.I)
DECEASED = re.compile(r"(Verstorbene (?:andere Personen|Feuerwehrangehörige)):\s*(\d+)", re.I)


def extract_text(path):
    """Text der ganzen PDF sowie linke und rechte Hälfte von Seite 1."""
    with pdfplumber.open(path) as pdf:
        if not pdf.pages or len(pdf.pages) > 200:
            raise ValueError("Ein Einsatzbericht muss zwischen 1 und 200 PDF-Seiten enthalten.")
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
        alerted, departed, arrived, deployed, _returned, finished = values[:6]
        call_sign = own_call_sign.search(m.group(1))
        vehicles.append({
            "name": m.group(1), "call_sign": call_sign.group(1) if call_sign else None,
            "crew": int(m.group(5)), "respiratory": int(m.group(6)),
            "deployed": {"Ja": 1, "Nein": 0}.get(deployed),
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
                       "role": PERSON_NOISE.sub("", middle).strip(),
                       "agt": m.group(4) != "nein", "agt_min": int(m.group(5))})
    return people


def _count(pattern, text):
    """Summe der Zähler einer Art im Bericht; None, wenn keine Zeile der Art vorkommt. Eine Zeile zählt einmal."""
    found = {label: int(number) for label, number in pattern.findall(text)}
    return sum(found.values()) if found else None


def _parse_details(full, report):
    """Angaben zu Brandverlauf, Rettung und Personenschäden – fehlt eine Angabe, bleibt sie None."""
    m = ALARM_SYSTEM.search(full)
    report["alarm_system"] = clean_alarm_system(m.group(1)) if m else None
    m = TACTIC.search(full)
    report["tactic"] = next(t for t in TACTICS if t.lower() == m.group(1).lower()) if m else None
    for name, label in FIRE_TIMES.items():
        m = re.search(re.escape(label) + r":\s*(\d\d\.\d\d\.\d{4} \d\d:\d\d)", full)
        report[name] = dt.datetime.strptime(m.group(1), "%d.%m.%Y %H:%M") if m else None
    report["rescued"] = _count(RESCUE, full)
    report["rescued_animals"] = _count(ANIMALS, full)
    report["injured"] = _count(INJURED, full)
    report["injured_firefighters"] = _count(INJURED_FIREFIGHTERS, full)
    report["deceased"] = _count(DECEASED, full)


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

    # Grund des Einsatzabbruchs: am Zeilenanfang oder hinter der Alarmierungszeit; Fließtext bleibt außen vor
    m = re.search(r"(?:^|\d\d:\d\d )Einsatzabbruch:[ \t]*(.+?)[ \t]*$", full, re.M)
    report["abort_reason"] = m.group(1) if m else None
    _parse_details(full, report)

    report["vehicles"] = _parse_vehicles(full, report, unit_prefix)
    report["people"] = _parse_people(full)
    return report


def read_report(path, filename, unit_prefix):
    return parse_report(*extract_text(path), filename, unit_prefix)
