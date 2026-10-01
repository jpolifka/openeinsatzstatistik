# -*- coding: utf-8 -*-
"""
Aufbau der Excel-Einsatzübersicht – gemeinsame Grundlage für Import und Export.

Blatt Einsatzübersicht: Kopf in Zeile 3, Einsätze ab Zeile 4, Spalten A:AV. Die Fahrzeugblöcke
(je Stärke, Ausrücken, Azeit, Eintreffen, Ezeit) werden aus domain.VEHICLES erzeugt.
Blatt Anwesenheit: Kameraden ab Spalte F, danach die Summenspalten Stärke und Gesamtstunden.
"""
from openpyxl.utils import get_column_letter

from app import domain

HEADER_ROW = 3
FIRST_ROW = 4
ATTENDANCE_FIRST_COLUMN = 6
ATTENDANCE_TOTALS = ("Stärke", "Gesamtstunden")
SHEET_ATTENDANCE_PREFIX = "anwesenheit"

VEHICLE_PARTS = ("crew", "departed", "turnout", "arrived", "arrival")


def _vehicle_headers(call_sign):
    short = call_sign.split("/")[-1]
    return (f"Stärke ({short})", f"Ausrückezeit ({short})", f"Azeit ({short}) min.",
            f"Eintreffzeit ({short})", f"Ezeit (8/15 min)\n({short})")


def _columns():
    """[(schlüssel, Überschrift)] in Spaltenreihenfolge ab A."""
    columns = [("number", "Nr."), ("date", "Datum"), ("weekday", "Tag"), ("day_night", "Tag / Nacht"),
               ("start", "Einsatzbeginn"), ("end", "Einsatzende"), ("duration", "Einsatzdauer"),
               ("keyword", "Einsatzstichwort"), ("subcode", "Stufe"), ("description", "Einsatz"),
               ("place", "Ort"), ("unit_leader", "EHF")]
    for call_sign in domain.VEHICLES:
        columns += [(f"{call_sign}.{part}", header)
                    for part, header in zip(VEHICLE_PARTS, _vehicle_headers(call_sign))]
    columns += [("station_staff", "Personen Gerätehaus"), ("crew_total", "Gesamtstärke"), ("gap", ""),
                ("turnout", "Azeit min."), ("arrival", "Ezeit"), ("on_time", "8 Min. erreicht"),
                ("crew_on_arrival", "Stärke bei E-Treffen"), ("crew_within_limit", "Stärke nach 8 Min."),
                ("crew_within_second", "Stärke nach 15Min."), ("crew_plan_total", "Gesamtstärke"),
                ("weekend_or_holiday", "Wochenende / Feiertag")]
    return columns


COLUMNS = _columns()
HEADERS = [header for _, header in COLUMNS]
# Schlüssel -> Spaltenbuchstabe, z. B. COLUMN["number"] == "A", COLUMN["02/45.crew"] == "M"
COLUMN = {key: get_column_letter(i) for i, (key, _) in enumerate(COLUMNS, start=1)}
LAST_COLUMN = len(COLUMNS)


def vehicle_column(call_sign, part):
    return COLUMN[f"{call_sign}.{part}"]


def attendance_sheet(workbook):
    return next((ws for ws in workbook.worksheets if ws.title.lower().startswith(SHEET_ATTENDANCE_PREFIX)), None)
