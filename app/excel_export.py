# -*- coding: utf-8 -*-
"""
Excel-Export im Spaltenformat der Einsatzübersicht.

Blatt Einsatzübersicht_Import entspricht Zeile für Zeile den Spalten der Einsatzübersicht (Werte
und Formeln, bei fünf Fahrzeugen A:AV), Blatt Anwesenheit_Import dem Blatt Anwesenheit – zum
Kopieren in die Excel-Datei. Spalten und Formeln richten sich nach der TenantConfig der Wehr.
"""
import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.workbook.properties import CalcProperties

from app.excel_layout import ATTENDANCE_FIRST_COLUMN, ATTENDANCE_TOTALS, FIRST_ROW, HEADER_ROW, Layout
from app.timeutil import parse_iso, parse_time

OVERVIEW_SHEET = "Einsatzübersicht_Import"
ATTENDANCE_SHEET = "Anwesenheit_Import"

HEADER_FONT = Font(name="Arial", size=10, bold=True, color="FFFFFFFF")
HEADER_FILL = PatternFill("solid", fgColor="FF0070C0")
FORMULA_FILL = PatternFill("solid", fgColor="FFF2F2F2")
WARNING_FILL = PatternFill("solid", fgColor="FFFFF2CC")
THIN = Side(style="thin", color="FFBFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
CENTER = Alignment(horizontal="center", vertical="center")

LEFT_ALIGNED = {"description", "place", "unit_leader"}
UNFORMATTED = LEFT_ALIGNED | {"number", "on_time", "weekend_or_holiday"}
NUMBER_FORMATS = {"date": "DD.MM.YYYY", "weekday": "@", "keyword": "@", "subcode": "@",
                  "start": "h:mm;@", "end": "h:mm;@", "duration": "h:mm;@"}
WIDTHS = {"number": 6, "date": 11, "weekday": 11, "day_night": 8, "description": 48, "place": 15,
          "unit_leader": 16, "gap": 3}


class Sheet:
    """Spaltenaufbau und Formeln der Einsatzübersicht einer Wehr."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.layout = Layout(cfg.vehicles, cfg.default_limit, cfg.second_limit)
        self.file_column = self.layout.last_column + 2
        self.warnings_column = self.layout.last_column + 3
        self.number_formats = {**NUMBER_FORMATS, **{f"{cs}.{part}": "h:mm" for cs in cfg.vehicles
                                                    for part in ("departed", "arrived")}}
        self.formula_keys = set(formulas(self, FIRST_ROW))


# ---------------------------------------------------------------- Formeln der Einsatzübersicht
def _cells(column, keys, row):
    return ",".join(f"{column[k]}{row}" for k in keys)


def formulas(sheet, r):
    """Formeln einer Zeile wie in der Einsatzübersicht (Kriterien-Texte mit Dezimalkomma wie im Original)."""
    cfg, column = sheet.cfg, sheet.layout.column
    c = {key: f"{letter}{r}" for key, letter in column.items()}
    vehicles = cfg.vehicles
    crew = [f"{cs}.crew" for cs in vehicles]
    arrival_pairs = [(c[f"{cs}.crew"], c[f"{cs}.arrival"]) for cs in vehicles]
    limit, second = cfg.default_limit, cfg.second_limit
    day_start, day_end = cfg.day_hours
    f = {
        "weekday": f'=TEXT({c["date"]},"TTTT")',
        "day_night": f'=IF(AND({c["start"]}>{day_start / 24:g},{c["start"]}<{day_end / 24:g}),"Tag","Nacht")',
        "duration": f'=MOD(({c["end"]}-{c["start"]}),1)',
        "crew_total": f'=SUM({_cells(column, crew + ["station_staff"], r)})',
        "turnout": f'=SUM(MIN({_cells(column, [f"{cs}.turnout" for cs in vehicles], r)}))',
        "arrival": f'=SUM(MIN({_cells(column, [f"{cs}.arrival" for cs in vehicles], r)}))',
        "on_time": f'=IF({c["arrival"]}<={limit + 0.0001:g},1,0)',
        "crew_on_arrival": "+".join(f'SUMIF({a},{c["arrival"]},{s})' for s, a in arrival_pairs),
        "crew_within_limit": "+".join(f'SUMIFS({s},{a},">"&{c["arrival"]},{a},"<={limit},001")'
                                      for s, a in arrival_pairs),
        "crew_within_second": "+".join(f'SUMIFS({s},{a},">"&{c["arrival"]},{a},">{limit}",{a},"<={second},001")'
                                       for s, a in arrival_pairs),
        "crew_plan_total": "+".join(c[f"{cs}.crew"] for cs in vehicles if cs not in cfg.excluded_from_plan_crew),
    }
    for key in ("crew_on_arrival", "crew_within_limit", "crew_within_second", "crew_plan_total"):
        f[key] = "=" + f[key]
    for cs in vehicles:
        for time_part, minutes_part in (("departed", "turnout"), ("arrived", "arrival")):
            f[f"{cs}.{minutes_part}"] = f'=IFERROR((MOD(({c[f"{cs}.{time_part}"]}-{c["start"]}),1))*24*60,"")'
    return f


def values(incident, cfg):
    """Werte einer Zeile aus einem gespeicherten Einsatz."""
    start, end = parse_iso(incident["started_at"]), parse_iso(incident["ended_at"])
    v = {"number": incident["number"],
         "date": start.replace(hour=0, minute=0, second=0) if start else None,
         "start": start.time() if start else None, "end": end.time() if end else None,
         "keyword": incident["keyword"], "subcode": incident["subcode"], "description": incident["description"],
         "place": incident["place"], "unit_leader": incident["unit_leader"],
         "station_staff": incident["station_staff"], "weekend_or_holiday": incident["weekend_or_holiday"]}
    for cs in cfg.vehicles:
        vehicle = incident["vehicles"].get(cs) or {}
        v[f"{cs}.crew"] = vehicle.get("crew") or None
        v[f"{cs}.departed"] = parse_time(vehicle.get("departed")) or "-"
        v[f"{cs}.arrived"] = parse_time(vehicle.get("arrived")) or "-"
    return v


def _format(sheet, cell, key):
    cell.border = BORDER
    cell.font = Font(name="Calibri", size=11)
    cell.alignment = Alignment(horizontal="left" if key in LEFT_ALIGNED else "center", vertical="center")
    if key in sheet.number_formats:
        cell.number_format = sheet.number_formats[key]
    elif key not in UNFORMATTED:
        cell.number_format = "0"
    if key in sheet.formula_keys:
        cell.fill = FORMULA_FILL


def _style_header(cell, **alignment):
    cell.font, cell.fill, cell.border = HEADER_FONT, HEADER_FILL, BORDER
    cell.alignment = Alignment(wrap_text=True, **alignment)


# ---------------------------------------------------------------- Blätter
def _write_overview(ws, sheet, incidents, year):
    layout = sheet.layout
    column = layout.column
    ws["A1"] = f"{sheet.cfg.name}: Import aus Einsatzberichten – Spalten A:{get_column_letter(layout.last_column)} " \
               f"entsprechen 1:1 dem Blatt Einsatzübersicht_{year}"
    ws["A1"].font = Font(name="Calibri", size=16, bold=True)
    groups = [(layout.vehicle_column(cs, "crew"), layout.vehicle_column(cs, "arrival"), cs.replace("/", "-") + "-1")
              for cs in layout.vehicles]
    groups.append((column["turnout"], column["weekend_or_holiday"], "Berechnung für Auswertung"))
    for first, last, title in groups:
        cell = ws[f"{first}2"]
        cell.value, cell.font, cell.alignment = title, Font(name="Calibri", size=11, bold=True), CENTER
        ws.merge_cells(f"{first}2:{last}2")
    for i, title in enumerate(layout.headers + ["", "PDF-Datei", "Prüfhinweise"], start=1):
        cell = ws.cell(HEADER_ROW, i, title)
        if title:
            _style_header(cell, horizontal="center", vertical="center")
    ws.row_dimensions[HEADER_ROW].height = 60

    for r, incident in enumerate(incidents, start=FIRST_ROW):
        row_values, row_formulas = values(incident, sheet.cfg), formulas(sheet, r)
        for i, (key, _) in enumerate(layout.columns, start=1):
            if key != "gap":
                _format(sheet, ws.cell(r, i, row_formulas.get(key, row_values.get(key))), key)
        ws.cell(r, sheet.file_column, incident["filename"] or "")
        warnings = ws.cell(r, sheet.warnings_column, "; ".join(incident["warnings"]))
        if incident["warnings"]:
            warnings.fill = WARNING_FILL

    widths = {column[k]: w for k, w in WIDTHS.items()}
    widths.update({get_column_letter(sheet.file_column): 40, get_column_letter(sheet.warnings_column): 70})
    for i in range(1, sheet.warnings_column + 1):
        letter = get_column_letter(i)
        ws.column_dimensions[letter].width = widths.get(letter, 9)
    ws.freeze_panes = f"{column['start']}{FIRST_ROW}"


def _write_attendance(ws, sheet, incidents, members, overview_title):
    ws["A1"] = "Anwesenheit – Spalten entsprechen 1:1 dem Blatt Anwesenheit (Werte kopieren)"
    ws["A1"].font = Font(name="Calibri", size=14, bold=True)
    member_columns = {m["id"]: ATTENDANCE_FIRST_COLUMN + i for i, m in enumerate(members)}
    last = ATTENDANCE_FIRST_COLUMN + len(members) - 1
    total_column, hours_column = last + 1, last + 2
    titles = {1: "Nr.", 2: "Datum", 3: "Tag", 4: "Tag / Nacht", 5: "Einsatzdauer",
              **{member_columns[m["id"]]: m["name"] for m in members},
              total_column: ATTENDANCE_TOTALS[0], hours_column: ATTENDANCE_TOTALS[1]}
    for column, title in titles.items():
        is_member = ATTENDANCE_FIRST_COLUMN <= column <= last
        _style_header(ws.cell(HEADER_ROW, column, title), horizontal="center", vertical="bottom",
                      text_rotation=90 if is_member else 0)
    ws.row_dimensions[HEADER_ROW].height = 120

    # Spalten A–E verweisen auf die gleiche Zeile im Blatt Einsatzübersicht_Import
    linked = ((1, "number", "0"), (2, "date", "DD.MM.YYYY"), (3, "weekday", "@"), (4, "day_night", "@"),
              (5, "duration", "h:mm"))
    L = get_column_letter
    for r, incident in enumerate(incidents, start=FIRST_ROW):
        for column, key, number_format in linked:
            cell = ws.cell(r, column, f"='{overview_title}'!{sheet.layout.column[key]}{r}")
            cell.number_format, cell.fill, cell.border, cell.alignment = number_format, FORMULA_FILL, BORDER, CENTER
        for column in range(ATTENDANCE_FIRST_COLUMN, last + 1):
            ws.cell(r, column).border, ws.cell(r, column).alignment = BORDER, CENTER
        for person in incident["people"]:
            ws.cell(r, member_columns[person["id"]], 1)
        total = ws.cell(r, total_column, f"=SUM({L(ATTENDANCE_FIRST_COLUMN)}{r}:{L(last)}{r})")
        total.fill, total.border, total.alignment = FORMULA_FILL, BORDER, CENTER
        hours = ws.cell(r, hours_column, f"={L(total_column)}{r}*E{r}")
        hours.number_format, hours.fill, hours.border, hours.alignment = "[h]:mm", FORMULA_FILL, BORDER, CENTER
    for column in range(1, hours_column + 1):
        ws.column_dimensions[L(column)].width = 4.5 if ATTENDANCE_FIRST_COLUMN <= column <= last else 11
    ws.freeze_panes = f"{L(ATTENDANCE_FIRST_COLUMN)}{FIRST_ROW}"
    return last


def _write_instructions(ws, sheet, last_member_column):
    cfg = sheet.cfg
    last = get_column_letter(sheet.layout.last_column)
    substitutes = [f"• {sub}-01 wird bei Einsatz mit eigener Besatzung im Block {target.replace('/', '-')}-1 "
                   "eingetragen." for sub, target in cfg.substitutes.items()]
    lines = [
        "So kommen die Daten in die Einsatzübersicht",
        "",
        f"1. Blatt '{OVERVIEW_SHEET}': Zeilen markieren (Spalten A bis {last}), kopieren und in der "
        "Einsatzübersicht in die erste freie Tabellenzeile einfügen (Strg+V). Die Formeln passen sich automatisch an.",
        f"2. Blatt '{ATTENDANCE_SHEET}': Spalten {get_column_letter(ATTENDANCE_FIRST_COLUMN)} bis "
        f"{get_column_letter(last_member_column)} der gleichen Zeilen kopieren und im Blatt Anwesenheit ab Spalte "
        f"{get_column_letter(ATTENDANCE_FIRST_COLUMN)} einfügen (Rechtsklick > Einfügeoptionen > Werte).",
        f"3. Spalte 'Prüfhinweise' ({get_column_letter(sheet.warnings_column)}) beachten – gelb markierte Zeilen bitte "
        "kontrollieren.",
        "",
        "Regeln der automatischen Übernahme",
        f"• Einsatzbeginn = frühester Alarmierungszeitpunkt der eigenen Fahrzeuge ({cfg.own_prefix}..).",
        f"• Einsatzende = spätestes Einsatzende der eigenen Fahrzeuge bzw. der FEZ ({cfg.control_center}).",
        "• Stichwort 'H2.03' -> Einsatzstichwort H2, Stufe 03; Brandsicherheitswache -> S1 / 00.",
        "• Stärke = Gesamtstärke je Fahrzeug aus dem Bericht; Zeiten mit Sekunden (Anzeige hh:mm).",
        "• Personen Gerätehaus = Anwesende laut Liste minus Besatzung der erfassten Fahrzeuge.",
        "• EHF = Person mit Funktion 'Einheitsführer'; fehlt diese, der Einsatzleiter (mit Hinweis).",
        "• Wochenende/Feiertag = Sa/So oder gesetzlicher Feiertag in Rheinland-Pfalz.",
        *substitutes,
        "• Grau hinterlegte Zellen enthalten Formeln wie in der Einsatzübersicht.",
    ]
    for line in lines:
        ws.append([line])
    ws["A1"].font = Font(name="Calibri", size=14, bold=True)
    ws["A7"].font = Font(name="Calibri", size=12, bold=True)
    ws.column_dimensions["A"].width = 130
    for row in ws.iter_rows():
        row[0].alignment = Alignment(wrap_text=True, vertical="top")


def write_workbook(incidents, members, year, target, cfg):
    """incidents wie aus store.load_incidents, members wie aus store.members_of_year, cfg: TenantConfig."""
    sheet = Sheet(cfg)
    wb = openpyxl.Workbook()
    overview = wb.active
    overview.title = OVERVIEW_SHEET
    _write_overview(overview, sheet, incidents, year)
    last_member_column = _write_attendance(wb.create_sheet(ATTENDANCE_SHEET), sheet, incidents, members, OVERVIEW_SHEET)
    _write_instructions(wb.create_sheet("Anleitung"), sheet, last_member_column)
    wb.calculation = CalcProperties(fullCalcOnLoad=True)
    wb.save(target)


# ---------------------------------------------------------------- Mehrere Wehren und Kennzahlen
SUMMARY_COLUMNS = (("name", "Wehr", None), ("count", "Einsätze", "0"), ("plan_count", "Bedarfsplan: Einsätze", "0"),
                   ("on_time", "davon in der Zeitgrenze", "0"), ("rate", "Erreichungsgrad", "0%"),
                   ("arrival_min", "Ø Eintreffzeit (min)", "0.0"), ("duration_hours", "Einsatzstunden", "0.0"),
                   ("staff_hours", "Personalstunden", "0.0"))


def _sheet_title(prefix, name, taken):
    """Blattname (höchstens 31 Zeichen, ohne verbotene Zeichen), eindeutig in der Mappe."""
    base = f"{prefix} {''.join(c for c in name if c not in '[]:*?/\\')}"[:31].rstrip()
    title, n = base, 2
    while title in taken:
        title, n = f"{base[:28]} {n}", n + 1
    taken.add(title)
    return title


def write_summary(ws, rows, total, year, limit, notes=()):
    """Kennzahlen je Wehr und Summe (rows/total: metrics.summary mit "name"). Ohne Namen von Personen."""
    ws["A1"] = f"Einsatzstatistik {year} – Kennzahlen je Wehr (Bedarfsplan mit {limit} Minuten)"
    ws["A1"].font = Font(name="Calibri", size=14, bold=True)
    for i, (_, title, _) in enumerate(SUMMARY_COLUMNS, start=1):
        _style_header(ws.cell(HEADER_ROW, i, title), horizontal="center", vertical="center")
    for r, row in enumerate([*rows, total], start=FIRST_ROW):
        for i, (key, _, number_format) in enumerate(SUMMARY_COLUMNS, start=1):
            cell = ws.cell(r, i, row.get(key))
            cell.border = BORDER
            if number_format:
                cell.number_format = number_format
            if row is total:
                cell.font = Font(name="Calibri", size=11, bold=True)
    for i, note in enumerate(notes, start=FIRST_ROW + len(rows) + 2):
        ws.cell(i, 1, note)
    ws.column_dimensions["A"].width = 30
    for i in range(2, len(SUMMARY_COLUMNS) + 1):
        ws.column_dimensions[get_column_letter(i)].width = 16


def write_summary_workbook(rows, total, year, limit, target, notes=()):
    """Nur die Kennzahlen (für Rollen ohne Zugriff auf Namen)."""
    wb = openpyxl.Workbook()
    wb.active.title = "Übersicht"
    write_summary(wb.active, rows, total, year, limit, notes)
    wb.save(target)


def write_combined_workbook(parts, rows, total, year, limit, target, notes=()):
    """Gesamt-Excel mehrerer Wehren: Übersicht plus je Wehr Einsatzübersicht und Anwesenheit.

    parts: [(cfg, incidents, members)] in der Reihenfolge der Übersicht.
    """
    wb = openpyxl.Workbook()
    wb.active.title = "Übersicht"
    write_summary(wb.active, rows, total, year, limit, notes)
    taken = {"Übersicht"}
    for cfg, incidents, members in parts:
        sheet = Sheet(cfg)
        overview_title = _sheet_title("Einsätze", cfg.name, taken)
        _write_overview(wb.create_sheet(overview_title), sheet, incidents, year)
        _write_attendance(wb.create_sheet(_sheet_title("Anwesenheit", cfg.name, taken)), sheet, incidents, members,
                          overview_title)
    wb.calculation = CalcProperties(fullCalcOnLoad=True)
    wb.save(target)
