# -*- coding: utf-8 -*-
import openpyxl

from app import excel_export, store
from app.excel_layout import Layout
from app.tenant_config import TenantConfig, Vehicle
from conftest import CFG


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
    assert "8 Min. erreicht" in layout.headers


def test_layout_grows_with_fleet():
    layout = Layout(("03/11", "03/12"), 10, 15)
    assert len(layout.headers) == 48 - 3 * 5
    assert layout.column["weekend_or_holiday"] == "AG" and "10 Min. erreicht" in layout.headers


def test_formulas_reference_layout():
    f = excel_export.formulas(excel_export.Sheet(CFG), 4)
    assert f["crew_total"] == "=SUM(M4,R4,W4,AB4,AG4,AL4)"
    assert f["crew_plan_total"] == "=M4+R4+W4+AB4"
    assert f["02/45.arrival"] == '=IFERROR((MOD((P4-E4),1))*24*60,"")'
    assert f["on_time"] == "=IF(AP4<=8.0001,1,0)"


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
