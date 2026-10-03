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


# Fahrzeug des Landes im Standort der Wehr: anderes Präfix, gleiche Kennzahl wie 01/23 der Einheit
STATE_VEHICLE = "RP WW 01/23-06 0 / 1 / 1 / 2 / 0 12.03.25 10:10:00 12.03.25 10:14:00 12.03.25 10:19:00 Ja " \
                "12.03.25 10:44:04 12.03.25 10:50:00\n"
UNIT_0123 = "FL NR#.BHÖ 01/23-01 0 / 0 / 3 / 3 / 0 12.03.25 10:10:00 12.03.25 10:15:00 12.03.25 10:20:00 Ja " \
            "12.03.25 10:44:04 12.03.25 10:50:00\n"


def test_vehicle_with_other_prefix_is_parsed():
    r = parse_report(FULL.replace("FL NR#.LIN", STATE_VEHICLE + "FL NR#.LIN"), LEFT, "", "x.pdf", CFG.unit_prefix)
    state = [v for v in r["vehicles"] if v["name"] == "RP WW 01/23-06"]
    assert len(state) == 1 and state[0]["crew"] == 2 and state[0]["call_sign"] is None


def test_vehicles_are_assigned_by_full_call_sign():
    cfg = dataclasses.replace(CFG, substitutes={}, fleet=(
        Vehicle("02/45", name="FL NR#.BHÖ 02/45-01"), Vehicle("01/23", name="FL NR#.BHÖ 01/23-01"),
        Vehicle("01/23-06", name="RP WW 01/23-06"), Vehicle("02/24")))
    r = _read(cfg, FULL.replace("FL NR#.LIN", STATE_VEHICLE + UNIT_0123 + "FL NR#.LIN"))
    assert r["slots"]["01/23-06"]["name"] == "RP WW 01/23-06"
    assert r["slots"]["01/23"]["name"] == "FL NR#.BHÖ 01/23-01"
    assert r["slots"]["02/24"]["name"] == "FL NR#.BHÖ 02/24-01"      # ohne Namen weiter über das Präfix
    assert r["new_vehicles"] == []
    assert cfg.substitute_label("RP WW 01/23-06", "01/23-06") is None
    assert cfg.is_own("RP WW 01/23-06") and not cfg.is_own("RP WW 01/23-07")


def test_substitute_by_full_call_sign():
    cfg = dataclasses.replace(CFG, substitutes={"RP WW 01/23-06": "02/45"},
                              fleet=(Vehicle("02/45", name="FL NR#.BHÖ 02/45-01"),))
    full = FULL.replace("FL NR#.BHÖ 02/45-01", "RP WW 01/23-06")            # mit Besatzung
    r = _read(cfg, full)
    assert r["slots"]["02/45"]["name"] == "RP WW 01/23-06"
    assert cfg.substitute_label("RP WW 01/23-06", "02/45") == "RP WW 01/23-06"


def test_new_vehicle_gets_name_and_short_call_sign():
    cfg = dataclasses.replace(CFG, fleet=(Vehicle("02/99", name="FL NR#.BHÖ 02/99-01"),))
    second = NEW_VEHICLE.replace("02/99-01", "02/99-02")
    r = _read(cfg, FULL.replace("FL NR#.LIN", second + "FL NR#.LIN"))
    assert "02/99-02" in r["new_vehicles"]
    assert ("02/99-02", "FL NR#.BHÖ 02/99-02") in report.new_fleet_vehicles(r)


def test_migration_fills_fleet_names(tmp_path):
    con = db.connect(str(tmp_path / "t.db"))
    db.migrate(con, db.TENANT_MIGRATIONS[:5])
    con.execute("INSERT INTO fleet (call_sign, sort_order) VALUES ('02/45', 1), ('02/24', 2)")
    incident_id = con.execute("INSERT INTO incident (year, number, source) VALUES (2025, 1, 'pdf')").lastrowid
    con.execute("INSERT INTO vehicle (incident_id, call_sign, name) VALUES (?, '02/45', 'FL NR#.BHÖ 02/45-01')",
                (incident_id,))
    for number in (2, 3):                     # Ersatzfahrzeug öfter in der Spalte 02/24 als das eigene (nie)
        other = con.execute("INSERT INTO incident (year, number, source) VALUES (2025, ?, 'pdf')", (number,)).lastrowid
        con.execute("INSERT INTO vehicle (incident_id, call_sign, name) VALUES (?, '02/24', 'RP WW 01/23-06')", (other,))
    con.commit()
    db.migrate(con)
    assert dict(con.execute("SELECT call_sign, name FROM fleet").fetchall()) == {
        "02/45": "FL NR#.BHÖ 02/45-01", "02/24": ""}
