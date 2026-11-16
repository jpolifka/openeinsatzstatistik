# -*- coding: utf-8 -*-
"""Excel-Export des BKS-Portals mit erfundenem Bericht – derselbe Einsatz wie in test_report."""
import datetime as dt
import io

import openpyxl
import pytest

from app import report, xlsx_report
from conftest import CFG

MAIN_HEADER = ("ID", "Datensatz", "Feuerwehrhaus", "Name", "Einsatznummer Leitstelle", "Einsatzbericht-Nr.",
               "Haupt-/Nebenbericht", "Einsatzstichwort", "Meldebild", "Einsatzstelle - Ort",
               "Einsatzstelle - Ortsteil", "Einsatzstelle - Straße", "Einsatzstelle - Objekt",
               "Zeitpunkt der Alarmierung der ersten Einheit", "Einsatzleiter")
MAIN_ROW = ("9000001", "9000000", "FW NR#.MUS 02 Musterstadt", "FW NR#.MUS 02 Musterstadt", "1250000001", "17/25",
            "Nebenbericht (NB)", "B2.08", "Zimmerbrand", "Altenau", "Altenau (NR)", "Musterweg 4",
            "WH Musterhaus", "12.03.2025 10:05", "Max Muster")
VEHICLE_HEADER = ("Fahrzeuge", "Einheitsführer", "Unterfuehrer", "Mannschaft", "Gesamt", "AGT", "Alarmiert",
                  "Ausrücken", "Eintreffen an E-Stelle", "Eingesetzt", "Rückkehr von E-Stelle", "Einsatzende",
                  "Gesamtzeit")
VEHICLES = [
    ("FL NR#.MUS 02/45-01", 0, 1, 1, 2, 0, "12.03.25 10:09:41", "12.03.25 10:12:04", "12.03.25 10:16:25", 1,
     "12.03.25 10:44:04", "12.03.25 10:48:21", None),
    ("FL NR#.MUS 02/24-01", 0, 0, 0, 0, 0, "12.03.25 10:08:30", "12.03.25 10:13:00", "12.03.25 10:18:00", 1,
     "12.03.25 10:44:04", "12.03.25 10:50:00", None),
    ("FL NR#.MUS 01/46-01", 0, 1, 5, 6, 2, "12.03.25 10:05:00", "12.03.25 10:07:00", "12.03.25 10:12:00", 1,
     "12.03.25 10:50:00", "12.03.25 10:56:59", None),
    ("FL NR#.LIN", 0, 0, 2, 2, 0, "12.03.25 10:09:00", None, None, 0, None, "12.03.25 11:05:00", None),
]
PEOPLE_HEADER = ("Name", "Vorname", "Fahrzeug", "Von", "Bis", "Funktion", "AGT", "Min (AGT)", "Bemerkung")
# Wie im Export: die Werte stehen eine Spalte rechts von ihrer Überschrift
PEOPLE = [
    ("Muster", "Max", 1, "FL NR#.MUS 02/45-01", "12.03.25 10:09", "12.03.25 10:48", "Einheitsführer", "nein", 0),
    ("Beispiel", "Erika", 1, "FL NR#.MUS 02/45-01", "12.03.25 10:09", "12.03.25 10:48", "Maschinist", "nein", 0),
    ("Probe", "Otto", 1, None, "12.03.25 10:09", "12.03.25 10:48", None, "nein", 0),
]


def make_workbook(main_rows=(MAIN_ROW,), people=PEOPLE, people_header=PEOPLE_HEADER):
    """Arbeitsmappe im Aufbau des Exports -> Bytes."""
    wb = openpyxl.Workbook()
    sheets = (("Einsatzbericht", MAIN_HEADER, main_rows),
              ("Ausger. Fahrzeuge und Personen", VEHICLE_HEADER, VEHICLES),
              ("Anw. Dienststellen", ("Verständigt", "Anwesend", "Dienststelle", "Name"), ()),
              ("Anwesenheitsliste", people_header, people))
    wb.remove(wb.active)
    for title, header, rows in sheets:
        ws = wb.create_sheet(title)
        ws.append(header)
        for row in rows:
            ws.append(row)
    data = io.BytesIO()
    wb.save(data)
    return data.getvalue()


def parse(data=None, filename="17-25_B2_Test.xlsx"):
    return xlsx_report.parse_report(xlsx_report.read_workbook(data or make_workbook()), filename, CFG.unit_prefix)


def test_parse_fields_vehicles_and_people():
    r = parse()
    assert r["source"] == "bks_xlsx"
    assert (r["number"], r["keyword"], r["subcode"]) == (17, "B2", "08")
    assert (r["unit"], r["unit_name"]) == ("FW NR#.MUS 02", "Musterstadt")
    assert (r["report_kind"], r["bks_report_id"], r["bks_record_id"]) == ("secondary", "9000001", "9000000")
    assert r["dispatch_number"] == "1250000001"
    assert r["district"] == "Altenau"
    assert r["first_alarm"] == dt.datetime(2025, 3, 12, 10, 5)
    assert [v["call_sign"] for v in r["vehicles"]] == ["02/45", "02/24", "01/46", None]
    assert r["vehicles"][0]["crew"] == 2 and r["vehicles"][2]["respiratory"] == 2
    assert r["vehicles"][3]["departed"] is None
    assert [(p["last_name"], p["vehicle"], p["role"]) for p in r["people"]] == [
        ("Muster", "02/45", "Einheitsführer"), ("Beispiel", "02/45", "Maschinist"), ("Probe", None, "")]
    assert r["people"][0]["vehicle_name"] == "FL NR#.MUS 02/45-01"


def test_people_without_offset():
    """Stehen die Werte unter ihren Überschriften, werden sie ebenso gelesen."""
    people = [row[:2] + row[3:] + (None,) for row in PEOPLE]
    r = parse(make_workbook(people=people))
    assert [(p["last_name"], p["vehicle"], p["role"]) for p in r["people"]] == [
        ("Muster", "02/45", "Einheitsführer"), ("Beispiel", "02/45", "Maschinist"), ("Probe", None, "")]


def test_derived_fields_like_pdf():
    r = report.read(report.parser(make_workbook(), "17-25_B2_Test.xlsx"), CFG)
    assert r["started_at"] == dt.datetime(2025, 3, 12, 10, 8, 30)
    assert r["ended_at"] == dt.datetime(2025, 3, 12, 11, 5)
    assert r["description"] == "Zimmerbrand / Musterhaus"
    assert r["unit_leader"] == "M. Muster"
    assert r["station_staff"] == 1
    assert set(r["slots"]) == {"02/45", "02/24"}
    assert r["warnings"] == []


def test_report_kinds():
    main = dict(zip(MAIN_HEADER, MAIN_ROW))
    assert parse(make_workbook([tuple({**main, "Haupt-/Nebenbericht": "Hauptbericht (HB)"}.values())])
                 )["report_kind"] == "main"
    master = parse(make_workbook([tuple({**main, "ID": "9000000", "Feuerwehrhaus": None, "Name": None,
                                         "Haupt-/Nebenbericht": None, "Datensatz": None}.values())]))
    assert (master["report_kind"], master["bks_record_id"], master["unit"]) == ("master", "9000000", None)


def test_rejects_several_reports_and_other_files():
    with pytest.raises(ValueError, match="mehrere Berichte"):
        parse(make_workbook([MAIN_ROW, MAIN_ROW]))
    wb = openpyxl.Workbook()
    data = io.BytesIO()
    wb.save(data)
    with pytest.raises(ValueError, match="Blatt „Einsatzbericht“"):
        parse(data.getvalue())
    with pytest.raises(ValueError, match="Keine gültige Excel-Datei"):
        xlsx_report.read_workbook(b"kein xlsx")


def test_rejects_oversized_workbooks(monkeypatch):
    monkeypatch.setattr(xlsx_report, "MAX_ROWS", 3)
    with pytest.raises(ValueError, match="zu viele Zeilen"):
        xlsx_report.read_workbook(make_workbook())
    monkeypatch.setattr(xlsx_report, "MAX_UNPACKED_BYTES", 1000)
    with pytest.raises(ValueError, match="zu groß"):
        xlsx_report.read_workbook(make_workbook())


def test_details_vehicles_and_agt():
    header = MAIN_HEADER + ("Nummer der Gefahrenmeldeanlage", "Einatztaktik", "Brand unter Kontrolle", "Feuer aus",
                            "Menschenrettung über baulichen Rettungsweg", "Menschenrettung über sonstiges",
                            "Rettung von Kleinvieh", "Verletzte andere Personen", "Verstorbene andere Personen")
    row = MAIN_ROW + ("301986", "Außenangriff", "12.03.2025 10:41", "12.03.2025 11:02", 2, 1, 4, 1, None)
    people = [PEOPLE[0], ("Beispiel", "Erika", 1, "FL NR#.MUS 02/45-01", "12.03.25 10:09", "12.03.25 10:48",
                          "Maschinist", "AGT", 25)]
    wb = openpyxl.load_workbook(io.BytesIO(make_workbook(people=people)))
    ws = wb["Einsatzbericht"]
    ws.delete_rows(1, 2)
    ws.append(header)
    ws.append(row)
    data = io.BytesIO()
    wb.save(data)
    r = parse(data.getvalue())
    assert (r["alarm_system"], r["tactic"]) == ("301986", "Außenangriff")
    assert r["fire_out_at"] == dt.datetime(2025, 3, 12, 11, 2)
    assert (r["rescued"], r["rescued_animals"], r["injured"], r["deceased"], r["injured_firefighters"]) == (3, 4, 1, None, None)
    assert [v["deployed"] for v in r["vehicles"]] == [1, 1, 1, 0]
    assert [(p["agt"], p["agt_min"]) for p in r["people"]] == [(False, 0), (True, 25)]
