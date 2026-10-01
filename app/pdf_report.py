# -*- coding: utf-8 -*-
"""
Einsatzbericht-PDF aus dem BKS-Portal RLP lesen.

extract_text() holt den Text aus der PDF, parse_report() wertet ihn aus. Das Ergebnis
enthält nur, was im Bericht steht – abgeleitete Werte (Beginn, EHF, …) ergänzt report.py.
"""
import datetime as dt
import re

import pdfplumber

from app.domain import UNIT_PREFIX

# Seite 1 ist zweispaltig; manche Felder sind nur im linken oder rechten Teil eindeutig
COLUMN_SPLIT = 0.495
TIMESTAMP = r"(\d\d\.\d\d\.\d\d \d\d:\d\d:\d\d)"
VEHICLE_ROW = re.compile(r"^(FL NR#\.\w+(?: \d\d/\d\d-\d\d)?|WW [\d/-]+|KO [\d/-]+|H CH \d+)\s+"
                         r"(\d+) / (\d+) / (\d+) / (\d+) / (\d+)\s+(.*)$")
VEHICLE_VALUES = re.compile(TIMESTAMP + r"\d?|(?<!\S)(-)(?!\S)|\b(Ja|Nein)\b")
OWN_CALL_SIGN = re.compile("^" + re.escape(UNIT_PREFIX) + r"(\d\d/\d\d)-\d\d")
PERSON_ROW = re.compile(r"^(\S+) (\S+)(.*?)\s(nein|ja|AGT)\s(\d+)\s*(.*)$")
PERSON_VEHICLE = re.compile(r"FL NR#\.\w+ (\d\d/\d\d)-\d\d")
PERSON_NOISE = re.compile(r"FL NR#\.\S+ \S+|\d\d\.\d\d\.\d\d \d\d:\d\d")
NOT_A_PERSON = ("Name", "FW", "EINSATZBERICHT")


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


def _parse_vehicles(text, report):
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
        call_sign = OWN_CALL_SIGN.search(m.group(1))
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
        people.append({"last_name": m.group(1), "first_name": m.group(2),
                       "vehicle": vehicle.group(1) if vehicle else None,
                       "role": PERSON_NOISE.sub("", middle).strip()})
    return people


def parse_report(full, left, right, filename):
    """Felder, Fahrzeugtabelle und Anwesenheitsliste aus dem Berichtstext."""
    report = {"filename": filename, "warnings": []}
    number_text = _field(full, "Einsatzbericht-Nr.")
    m = re.match(r"(\d+)\s*/\s*(\d+)", number_text)
    report["number"] = int(m.group(1)) if m else None
    report["number_text"] = number_text

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

    report["vehicles"] = _parse_vehicles(full, report)
    report["people"] = _parse_people(full)
    return report


def read_report(path, filename):
    return parse_report(*extract_text(path), filename)
