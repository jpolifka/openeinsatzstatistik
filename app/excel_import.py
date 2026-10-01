# -*- coding: utf-8 -*-
"""Einmaliger Import der bisherigen Excel-Einsatzübersichten (Einsatzübersicht_JJJJ.xlsx)."""
import datetime as dt
import glob
import logging
import os
import re
import unicodedata

import openpyxl

from app import domain, store
from app.excel_layout import (ATTENDANCE_FIRST_COLUMN, ATTENDANCE_TOTALS, COLUMN, FIRST_ROW, HEADER_ROW,
                              attendance_sheet, vehicle_column)
from app.names import split_name
from app.timeutil import as_duration, as_time, time_text, to_iso

log = logging.getLogger("pdf2einsatz")
FILENAME = re.compile(r"Einsatzübersicht_20\d\d\.xlsx$")


def _text(value):
    return str(value or "").strip()


def _start_and_end(date, start_time, end_time, duration):
    """Beginn aus Datum + Uhrzeit; Ende über die Dauer, sonst über die Uhrzeit (ggf. am Folgetag)."""
    start = dt.datetime.combine(date, start_time or dt.time())
    if duration is not None:
        return start, start + duration
    if end_time:
        end = dt.datetime.combine(date, end_time)
        return start, end + dt.timedelta(days=1) if end < start else end
    return start, None


def _import_overview(con, sheet, filename):
    """Blatt Einsatzübersicht -> {Nr.: Einsatz-ID}; bereits erfasste Nummern ergeben None."""
    ids_by_number, added, skipped = {}, 0, 0
    for r in range(FIRST_ROW, sheet.max_row + 1):
        date = sheet.cell(r, 2).value
        if not isinstance(date, dt.datetime):
            continue
        value = lambda key: sheet[f"{COLUMN[key]}{r}"].value
        number = store.to_int(value("number"))
        if store.find_incident(con, date.year, number):
            skipped += 1
            ids_by_number[number] = None
            continue
        start, end = _start_and_end(date.date(), as_time(value("start")), as_time(value("end")),
                                    as_duration(value("duration")))
        fields = {"number": number, "started_at": to_iso(start), "ended_at": to_iso(end),
                  **{key: _text(value(key)) for key in store.TEXT_FIELDS}, "station_staff": value("station_staff")}
        incident_id = store.create_incident(con, fields, source="excel", filename=filename,
                                            weekend_or_holiday=store.to_int(value("weekend_or_holiday")))
        for call_sign in domain.VEHICLES:
            cell = lambda part: sheet[f"{vehicle_column(call_sign, part)}{r}"].value
            crew, departed, arrived = store.to_int(cell("crew")), as_time(cell("departed")), as_time(cell("arrived"))
            if crew or departed or arrived:
                store.add_vehicle(con, incident_id, call_sign, None, crew, time_text(departed), time_text(arrived))
        ids_by_number[number] = incident_id
        added += 1
    return ids_by_number, added, skipped


def _attendance_columns(con, sheet):
    """Kopfzeile des Blatts Anwesenheit -> [(spalte, kamerad_id)]; legt Kameraden an."""
    members = store.MemberDirectory(con)
    columns = []
    for cell in sheet[HEADER_ROW]:
        header = cell.value.strip() if isinstance(cell.value, str) else ""
        if cell.column < ATTENDANCE_FIRST_COLUMN or not header:
            continue
        if header in ATTENDANCE_TOTALS:
            break
        last_name, first_name = split_name(header)
        columns.append((cell.column, members.find_or_create(last_name, first_name, name=" ".join(header.split()))))
    return columns


def _import_attendance(con, sheet, ids_by_number):
    count = 0
    columns = _attendance_columns(con, sheet)
    for r in range(FIRST_ROW, sheet.max_row + 1):
        incident_id = ids_by_number.get(store.to_int(sheet.cell(r, 1).value))
        if not incident_id:
            continue
        for column, member_id in columns:
            if store.to_int(sheet.cell(r, column).value) == 1:
                store.add_attendance(con, incident_id, member_id)
                count += 1
    return count


def import_workbook(con, path):
    """Einsatzübersicht_JJJJ.xlsx einlesen. Bereits vorhandene Nummern werden übersprungen."""
    workbook = openpyxl.load_workbook(path, data_only=True)
    filename = os.path.basename(path)
    ids_by_number, added, skipped = _import_overview(con, workbook.worksheets[0], filename)
    attendance = attendance_sheet(workbook)
    present = _import_attendance(con, attendance, ids_by_number) if attendance else 0
    log.info("Import %s: %d Einsätze neu, %d übersprungen, %d Anwesenheiten", path, added, skipped, present)
    return {"file": filename, "added": added, "skipped": skipped, "attendance": present}


def initial_import(con, folder):
    """Beim ersten Start alle Einsatzübersicht_JJJJ.xlsx aus dem Import-Ordner übernehmen."""
    if not store.is_empty(con):
        return []
    paths = [p for p in glob.glob(os.path.join(folder, "**", "*.xlsx"), recursive=True)
             if FILENAME.match(unicodedata.normalize("NFC", os.path.basename(p)))]
    return [import_workbook(con, p) for p in sorted(paths)]
