# -*- coding: utf-8 -*-
"""Fahrzeugliste mit Dienstzeitraum: Aufnahme beim Import, Zuordnung, Spalten im Export."""
import dataclasses
import datetime as dt

from app import db, excel_export, main, report, store, tenancy
from app.pdf_report import parse_report
from app.tenant_config import Vehicle
from conftest import CFG, make_tenant
from test_report import FULL, LEFT

# Zusätzliche Fahrzeugzeile einer eigenen, noch nicht gelisteten Einheit (02/99)
NEW_VEHICLE = "FL NR#.BHÖ 02/99-01 0 / 0 / 2 / 2 / 0 12.03.25 10:10:00 12.03.25 10:14:00 12.03.25 10:19:00 Ja " \
              "12.03.25 10:44:04 12.03.25 10:50:00\n"


def _read(cfg=CFG, full=FULL):
    r = parse_report(full, LEFT, "", "17-25_B2_Test.pdf", cfg.unit_prefix)
    report.derive(r, cfg)
    return r


def test_unknown_own_vehicle_is_no_error_but_new():
    r = _read(full=FULL.replace("FL NR#.LIN", NEW_VEHICLE + "FL NR#.LIN"))
    assert r["new_vehicles"] == ["02/99"] and "02/99" in r["slots"]
    assert not any("Nicht in Liste" in w for w in r["warnings"])
    assert r["day"] == dt.date(2025, 3, 12)


def test_vehicle_out_of_service_gets_hint_but_counts():
    cfg = dataclasses.replace(CFG, fleet=(Vehicle("02/45", in_service_until="2025-01-31"), Vehicle("02/24")))
    r = _read(cfg)
    assert "02/45" in r["slots"]
    assert any("02/45 ist laut Fahrzeugliste an diesem Tag außer Dienst" in w for w in r["warnings"])


def test_accepting_report_adds_vehicle_to_fleet(make_client):
    make_tenant("wehr-a1")
    client = make_client()
    r = _read(full=FULL.replace("FL NR#.LIN", NEW_VEHICLE + "FL NR#.LIN"))
    data = main._preview_json(r, tenancy.access_for(None).selected, tenancy.access_for(None))
    assert data["new_vehicles"] == ["02/99"] and "02/99" in [v["call_sign"] for v in data["vehicles"]]
    token = main.previews.add([(r, "wehr-a1")], None)
    saved = client.post("/api/reports/accept", json={"token": token, "filename": r["filename"], "fields": {}}).json()
    assert [v["call_sign"] for v in saved["vehicles"]][-1] == "02/99"
    assert client.get("/api/config").json()["vehicles"][-1] == "02/99"
    with db.connection(tenancy.tenant_path("wehr-a1")) as con:
        row = con.execute("SELECT in_service_from FROM fleet WHERE call_sign = '02/99'").fetchone()
    assert row["in_service_from"] == "2025-03-12"


def test_export_columns_follow_service_period(con, tmp_path):
    cfg = dataclasses.replace(CFG, fleet=(Vehicle("02/45"), Vehicle("02/24", in_service_until="2024-12-31"),
                                          Vehicle("02/71", in_service_from="2026-01-01")))
    assert cfg.vehicles_in(2025) == ("02/45",)
    assert cfg.vehicles_in(2024) == ("02/45", "02/24") and cfg.vehicles_in(2026) == ("02/45", "02/71")
    incident_id = store.create_incident(con, {"number": 1, "started_at": "2025-03-12T10:00:00", "keyword": "B2"},
                                        source="pdf")
    store.add_vehicle(con, incident_id, "02/24", None, 3, None, "10:07:00")   # außer Dienst, aber mit Daten
    incidents = store.load_incidents(con, year=2025)
    assert cfg.vehicles_in(2025, incidents) == ("02/45", "02/24")
    sheet = excel_export.Sheet(cfg, 2025, incidents)
    assert sheet.layout.vehicles == ("02/45", "02/24")
    excel_export.write_workbook(incidents, [], 2025, tmp_path / "x.xlsx", cfg)


def test_incident_shows_vehicles_in_service_or_with_data():
    cfg = dataclasses.replace(CFG, fleet=(Vehicle("02/45"), Vehicle("02/24", in_service_until="2024-12-31"),
                                          Vehicle("02/71", in_service_from="2026-01-01")))
    incident = {"started_at": "2025-03-12T10:00:00", "vehicles": {}}
    assert cfg.vehicles_for(incident) == ("02/45",)
    assert cfg.vehicles_for({**incident, "vehicles": {"02/71": {}}}) == ("02/45", "02/71")
