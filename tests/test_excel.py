# -*- coding: utf-8 -*-
import openpyxl

from app import excel_export, store
from app.excel_layout import Layout
from app.tenant_config import TenantConfig, Vehicle
from conftest import CFG, make_incident


def test_export_preserves_duration_over_24_hours():
    incident = make_incident(started_at="2025-03-12T10:00:00", ended_at="2025-03-13T12:00:00")
    values = excel_export.values(incident, [])
    assert (values["end"] - values["start"]).total_seconds() == 26 * 3600
    assert "MOD" not in excel_export.formulas(excel_export.Sheet(CFG), 4)["duration"]
    assert excel_export.NUMBER_FORMATS["duration"].startswith("[h]")


def test_user_text_is_not_exported_as_formula(con, tmp_path):
    text = '=HYPERLINK("https://example.invalid","Test")'
    store.create_incident(con, {"number": 1, "started_at": "2025-01-01T12:00:00",
                               "description": text}, source="pdf", filename="=DATEI")
    target = tmp_path / "safe.xlsx"
    excel_export.write_workbook(store.load_incidents(con, year=2025), [], 2025, target, CFG)
    wb = openpyxl.load_workbook(target)
    cells = [c for ws in wb for row in ws for c in row if c.value in (text, "=DATEI")]
    assert len(cells) == 2
    assert all(c.data_type == "s" for c in cells)
    assert any(c.data_type == "f" for ws in wb for row in ws for c in row)
    wb.close()


def test_layout_matches_einsatzuebersicht():
    layout = Layout(CFG.vehicles, CFG.default_limit, CFG.second_limit)
    column = layout.column
    assert (column["number"], column["unit_leader"]) == ("A", "L")
    assert [layout.vehicle_column("02/45", p) for p in ("crew", "departed", "turnout", "arrived", "arrival")] == \
        ["M", "N", "O", "P", "Q"]
    assert layout.vehicle_column("01/10", "crew") == "AG"
    assert (column["station_staff"], column["crew_total"], column["turnout"]) == ("AL", "AM", "AO")
    assert (column["crew_plan_total"], column["weekend_or_holiday"]) == ("AU", "AV")
    assert len(layout.headers) == 48
    assert "10 Min. erreicht" in layout.headers


def test_layout_grows_with_fleet():
    layout = Layout(("03/11", "03/12"), 10, 15)
    assert len(layout.headers) == 48 - 3 * 5
    assert layout.column["weekend_or_holiday"] == "AG" and "10 Min. erreicht" in layout.headers


def test_formulas_reference_layout():
    f = excel_export.formulas(excel_export.Sheet(CFG), 4)
    assert f["crew_total"] == "=SUM(M4,R4,W4,AB4,AG4,AL4)"
    assert f["crew_plan_total"] == "=M4+R4+W4+AB4"
    assert f["02/45.arrival"] == '=IFERROR((MOD((P4-E4),1))*24*60,"")'
    assert f["on_time"] == "=IF(AP4<=10.0001,1,0)"


def test_export_writes_overview_and_attendance(con, tmp_path):
    incident_id = store.create_incident(con, {
        "number": 3, "started_at": "2025-03-12T22:00:00", "ended_at": "2025-03-13T01:30:00", "keyword": "B2",
        "subcode": "08", "description": "Zimmerbrand / Musterweg", "place": "Musterstadt", "unit_leader": "M. Muster",
        "station_staff": 2}, source="pdf", filename="03-25.pdf", warnings=["Bitte prüfen"])
    store.add_vehicle(con, incident_id, "03/11", "FL NR#.ABC 03/11-01", 6, "22:03:00", "22:07:00")
    store.add_attendance(con, incident_id, store.MemberDirectory(con).find_or_create("Muster", "Max"))
    cfg = TenantConfig(name="Feuerwehr Musterstadt", fleet=(Vehicle("03/11"), Vehicle("03/12")), own_prefix="03/")
    target = tmp_path / "export.xlsx"
    excel_export.write_workbook(store.load_incidents(con, year=2025), store.members_of_year(con, 2025), 2025,
                                target, cfg)

    workbook = openpyxl.load_workbook(target)
    overview, attendance = workbook["Einsatzübersicht_Import"], workbook["Anwesenheit_Import"]
    assert overview["M3"].value == "Stärke (11)" and overview["M4"].value == 6
    assert overview["X4"].value == "=SUM(M4,R4,W4)"                   # Gesamtstärke: zwei Fahrzeuge + Gerätehaus
    assert overview["AI3"].value == "PDF-Datei" and overview["AJ4"].value == "Bitte prüfen"
    assert attendance["F3"].value == "Muster, Max" and attendance["F4"].value == 1
    assert any("(03/..)" in (row[0] or "") for row in workbook["Anleitung"].iter_rows(values_only=True))


def test_formulas_without_vehicles_are_valid():
    """Ohne (Plan-)Fahrzeuge keine leeren Formeln und kein MIN() ohne Argumente – Excel lehnt beides ab."""
    f = excel_export.formulas(excel_export.Sheet(TenantConfig(name="Neu")), 4)
    assert f["turnout"] == f["arrival"] == '=""'
    assert all(f[k] == "=0" for k in ("crew_on_arrival", "crew_within_limit", "crew_within_second", "crew_plan_total"))
    only_excluded = TenantConfig(name="Neu", fleet=(Vehicle("03/11", in_plan_crew=False),))
    assert excel_export.formulas(excel_export.Sheet(only_excluded), 4)["crew_plan_total"] == "=0"


def test_attendance_without_members_and_apostrophe_in_name(con, tmp_path):
    store.create_incident(con, {"number": 1, "started_at": "2025-03-12T10:00:00", "ended_at": "2025-03-12T11:00:00",
                                "keyword": "B1"}, source="pdf")
    cfg = TenantConfig(name="Wehr Muster's Hof", fleet=(Vehicle("03/11"),), own_prefix="03/")
    target = tmp_path / "gesamt.xlsx"
    excel_export.write_combined_workbook([(cfg, store.load_incidents(con, year=2025), [])], [], {}, 2025, 10, target)
    workbook = openpyxl.load_workbook(target)
    attendance = next(ws for ws in workbook if ws.title.startswith("Anwesenheit"))
    assert attendance["A4"].value.startswith("='Einsätze Wehr Muster''s Hof'!")
    assert attendance["F4"].value == 0                                   # Stärke ohne Kameraden
