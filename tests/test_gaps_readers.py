# -*- coding: utf-8 -*-
"""Grenzen und Randfälle der Leser für Excel-Export und PDF."""
import datetime as dt
import io
import zipfile

import openpyxl
import pytest

from app import pdf_report, xlsx_report
from conftest import CFG
from test_report import FULL, LEFT
from test_xlsx_report import MAIN_ROW, make_workbook


def _workbook(rows_by_sheet):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for title, rows in rows_by_sheet.items():
        ws = wb.create_sheet(title)
        for row in rows:
            ws.append(row)
    data = io.BytesIO()
    wb.save(data)
    return data.getvalue()


# ---------------------------------------------------------------- xlsx
def test_workbook_limits(monkeypatch):
    data = make_workbook()
    monkeypatch.setattr(xlsx_report, "MAX_UNPACKED_BYTES", 10)
    with pytest.raises(ValueError, match="zu groß"):
        xlsx_report.read_workbook(data)
    monkeypatch.undo()
    monkeypatch.setattr(xlsx_report, "MAX_SHEETS", 1)
    with pytest.raises(ValueError, match="Tabellenblätter"):
        xlsx_report.read_workbook(data)
    monkeypatch.undo()
    monkeypatch.setattr(xlsx_report, "MAX_COLUMNS", 3)
    with pytest.raises(ValueError, match="Spalten"):
        xlsx_report.read_workbook(data)
    monkeypatch.undo()
    monkeypatch.setattr(xlsx_report, "MAX_ROWS", 2)
    with pytest.raises(ValueError, match="Zeilen"):
        xlsx_report.read_workbook(data)


def test_invalid_workbook_and_path_source(tmp_path):
    with pytest.raises(ValueError, match="Keine gültige Excel-Datei"):
        xlsx_report.read_workbook(b"kein zip")
    bad = io.BytesIO()
    with zipfile.ZipFile(bad, "w") as archive:
        archive.writestr("x.txt", "kein Excel")
    with pytest.raises(ValueError, match="Keine gültige Excel-Datei"):
        xlsx_report.read_workbook(bad.getvalue())
    path = tmp_path / "17-25.xlsx"
    path.write_bytes(make_workbook())
    parsed = xlsx_report.parse_report(xlsx_report.read_workbook(str(path)), "17-25.xlsx", CFG.unit_prefix)
    assert parsed["number"] == 17


@pytest.mark.parametrize("value, expected", [(None, ""), (3.0, "3"), (3.5, "3.5"), (" x ", "x")])
def test_text_conversion(value, expected):
    assert xlsx_report._text(value) == expected


def test_numeric_helpers_and_timestamps():
    assert xlsx_report._int("7") == 7 and xlsx_report._int("x") == 0 and xlsx_report._int(None) == 0
    row = {"Alarmiert": "12.03.25 10:00:00", "Rest": "", "AGT 1": "2", "AGT 2": 3}
    assert xlsx_report._count(row, "Alarmiert") == 0                  # Text zählt als 0, ist aber angegeben
    assert xlsx_report._count(row, "AGT", prefix=True) == 5
    assert xlsx_report._count(row, "Rest") is None
    stamp = dt.datetime(2025, 3, 12, 10)
    assert xlsx_report._timestamp(stamp) is stamp
    assert xlsx_report._timestamp("12.03.2025 10:05") == dt.datetime(2025, 3, 12, 10, 5)
    assert xlsx_report._timestamp("kein Datum") is None
    assert xlsx_report._records([]) == []
    assert xlsx_report._sheet({"Anderes": [1]}, "Anwesenheit") == []


def test_report_without_sheets_has_no_people_or_vehicles():
    sheets = {"Einsatzbericht": [("ID", "Feuerwehrhaus"), ("9000001", "FW NR#.MUS 02 Musterstadt")]}
    parsed = xlsx_report.parse_report(sheets, "17-25.xlsx", CFG.unit_prefix)
    assert parsed["vehicles"] == [] and parsed["people"] == []


def test_vehicle_rows_without_name_are_skipped_and_people_without_name_too():
    sheets = {
        "Einsatzbericht": [("ID", "Feuerwehrhaus"), ("9000001", "FW NR#.MUS 02 Musterstadt")],
        "Ausger. Fahrzeuge und Personen": [("Fahrzeuge", "Gesamt"), (None, 3), ("FL NR#.MUS 02/45-01", 2)],
        "Anwesenheitsliste": [("Name", "Vorname", "Fahrzeug", "AGT"), (None, "Erika", None, "ja"),
                              ("Muster", "Max", None, "ja"), ("Probe", "Otto")],
    }
    parsed = xlsx_report.parse_report(sheets, "17-25.xlsx", CFG.unit_prefix)
    assert [v["name"] for v in parsed["vehicles"]] == ["FL NR#.MUS 02/45-01"]
    assert [(p["last_name"], p["agt"]) for p in parsed["people"]] == [("Muster", True), ("Probe", False)]


def test_people_offset_is_found_by_agt_column_when_vehicle_missing():
    rows = [("Name", "Vorname", "AGT"), ("Muster", "Max", None, "nein")]
    assert xlsx_report._people_offset(rows, list(rows[0])) == 1
    assert xlsx_report._people_offset([("Name", "Vorname"), ("Muster", "Max")], ["Name", "Vorname"]) == 0
    assert xlsx_report._people_offset([("Fahrzeug", "AGT"), ("x", "y")], ["Fahrzeug", "AGT"]) == 0


# ---------------------------------------------------------------- pdf
class _Page:
    width, height = 100, 200

    def __init__(self, text="Text"):
        self._text = text

    def extract_text(self):
        return self._text

    def crop(self, box):
        return _Page(f"crop{int(box[0])}")


class _Pdf:
    def __init__(self, pages):
        self.pages = pages

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_extract_text_joins_pages_and_halves(monkeypatch):
    monkeypatch.setattr(pdf_report.pdfplumber, "open", lambda path: _Pdf([_Page("eins"), _Page(None)]))
    text, left, right = pdf_report.extract_text("x.pdf")
    assert text == "eins\n" and left == "crop0" and right.startswith("crop")


@pytest.mark.parametrize("pages", [0, 201])
def test_extract_text_rejects_empty_and_huge_pdfs(monkeypatch, pages):
    monkeypatch.setattr(pdf_report.pdfplumber, "open", lambda path: _Pdf([_Page()] * pages))
    with pytest.raises(ValueError, match="zwischen 1 und 200"):
        pdf_report.extract_text("x.pdf")


def test_incomplete_vehicle_row_is_padded_and_warned(monkeypatch):
    text = FULL.replace("FL NR#.MUS 02/24-01 0 / 0 / 0 / 0 / 0 12.03.25 10:08:30 12.03.25 10:13:00 12.03.25 10:18:00 Ja "
                        "12.03.25 10:44:04 12.03.25 10:50:00", "FL NR#.MUS 02/24-01 0 / 0 / 0 / 0 / 0 12.03.25 10:08:30")
    parsed = pdf_report.parse_report(text, LEFT, "", "17-25_B2_Test.pdf", CFG.unit_prefix)
    assert any(w.startswith("Fahrzeugzeile unvollständig") for w in parsed["warnings"])
