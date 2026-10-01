# -*- coding: utf-8 -*-
import openpyxl

from app import db, excel_export, excel_import, store
from app.excel_layout import COLUMN, HEADERS, vehicle_column


def test_layout_matches_einsatzuebersicht():
    assert (COLUMN["number"], COLUMN["unit_leader"]) == ("A", "L")
    assert [vehicle_column("02/45", p) for p in ("crew", "departed", "turnout", "arrived", "arrival")] == \
        ["M", "N", "O", "P", "Q"]
    assert vehicle_column("01/10", "crew") == "AG"
    assert (COLUMN["station_staff"], COLUMN["crew_total"], COLUMN["turnout"]) == ("AL", "AM", "AO")
    assert (COLUMN["crew_plan_total"], COLUMN["weekend_or_holiday"]) == ("AU", "AV")
    assert len(HEADERS) == 48


def test_formulas_reference_layout():
    f = excel_export.formulas(4)
    assert f["crew_total"] == "=SUM(M4,R4,W4,AB4,AG4,AL4)"
    assert f["crew_plan_total"] == "=M4+R4+W4+AB4"
    assert f["02/45.arrival"] == '=IFERROR((MOD((P4-E4),1))*24*60,"")'
    assert f["on_time"] == "=IF(AP4<=8.0001,1,0)"


def _stored_incident(con):
    incident_id = store.create_incident(con, {
        "number": 3, "started_at": "2025-03-12T22:00:00", "ended_at": "2025-03-13T01:30:00", "keyword": "B2",
        "subcode": "08", "description": "Zimmerbrand / Musterweg", "place": "Rheinbrohl", "unit_leader": "M. Muster",
        "station_staff": 2}, source="pdf", filename="03-25.pdf", warnings=["Bitte prüfen"])
    store.add_vehicle(con, incident_id, "02/45", "FL NR#.BHÖ 02/45-01", 6, "22:03:00", "22:07:00")
    member_id = store.MemberDirectory(con).find_or_create("Muster", "Max")
    store.add_attendance(con, incident_id, member_id)
    return incident_id


def test_export_then_import_keeps_overview(con, tmp_path):
    _stored_incident(con)
    incidents = store.load_incidents(con, year=2025)
    target = tmp_path / "export.xlsx"
    excel_export.write_workbook(incidents, store.members_of_year(con, 2025), 2025, target)

    ws = openpyxl.load_workbook(target)["Anwesenheit_Import"]
    assert ws["F3"].value == "Muster, Max" and ws["F4"].value == 1

    # Import in eine frische Datenbank: Werte der Einsatzübersicht kommen unverändert zurück
    fresh = db.connect(":memory:")
    db.migrate(fresh)
    result = excel_import.import_workbook(fresh, target)
    assert result["added"] == 1
    imported = store.load_incidents(fresh, year=2025)[0]
    for name in store.FIELDS:
        assert imported[name] == incidents[0][name], name
    assert imported["weekend_or_holiday"] == incidents[0]["weekend_or_holiday"]
    assert {k: (v["crew"], v["departed"], v["arrived"]) for k, v in imported["vehicles"].items()} == \
        {"02/45": (6, "22:03:00", "22:07:00")}
    fresh.close()
