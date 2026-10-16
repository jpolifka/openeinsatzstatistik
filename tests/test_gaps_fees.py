# -*- coding: utf-8 -*-
"""Gebührenordnung: Eingabeprüfung, Pflege einzelner Fassungen und Hinweise bei unvollständigen Einsätzen."""
import datetime as dt

import pytest

from app import db, fees, legacy, tenancy
from test_fees import _fees, _incident, vg  # noqa: F401  (Fixture vg)

RATES = legacy.FEE_SCHEDULE_2024["rates"]


def test_rates_need_code_and_rate_per_vehicle_type():
    with pytest.raises(ValueError, match="Kürzel"):
        fees.check_rates({**RATES, "vehicles": [{"code": " ", "rate": 5}]})
    with pytest.raises(ValueError, match="Kürzel"):
        fees.check_rates({**RATES, "vehicles": [{"code": "LF", "rate": -1}]})
    with pytest.raises(ValueError, match="doppelt"):
        fees.check_rates({**RATES, "vehicles": [{"code": "HLF 20", "rate": 1}, {"code": "hlf-20", "rate": 2}]})


def test_schedule_needs_name_and_real_date(data_dir):
    with tenancy.central() as con:
        vg_id = tenancy.create_vg(con, "vg-f", "VG F")
        with pytest.raises(ValueError, match="Bezeichnung"):
            fees.save_schedule(con, vg_id, "", "2025-01-01", RATES, "a@example.org")
        with pytest.raises(ValueError, match="Bezeichnung"):
            fees.save_schedule(con, vg_id, "Name", "01.01.2025", RATES, "a@example.org")
        with pytest.raises(ValueError, match="Kalenderdatum"):
            fees.save_schedule(con, vg_id, "Name", "2025-02-30", RATES, "a@example.org")
        schedule_id = fees.save_schedule(con, vg_id, "Name", "2025-01-01", RATES, "a@example.org")
        assert fees.save_schedule(con, vg_id, "Neu", "2025-02-01", RATES, "a@example.org", schedule_id) == schedule_id
        with pytest.raises(KeyError):
            fees.save_schedule(con, vg_id, "Neu", "2025-02-01", RATES, "a@example.org", schedule_id + 100)
        assert fees.schedule_for(con, vg_id, "2025-01-15") is None
        assert fees.schedule_for(con, vg_id, "2025-03-01")["name"] == "Neu"
        assert fees.schedule_for(con, vg_id, "2000-01-01", schedule_id + 100) is None
        assert fees.vehicle_types(con, vg_id, "2025-03-01") == [v["code"] for v in RATES["vehicles"]]
        assert fees.vehicle_types(con, vg_id, "2000-01-01") == []


def test_vehicle_minutes_without_incident_end_are_unknown():
    assert fees._vehicle_minutes({"departed": "10:00:00"}, dt.datetime(2025, 3, 12, 10), None) is None
    assert fees._vehicle_minutes({"departed": "10:00:00", "finished": "10:30"}, None, None) == 30


def _tenants():
    return list(tenancy.vg_tenants(tenancy.access_for(None).tenant("wehr-a1", "stats.view").vg_id))


def _calculate(**kwargs):
    with tenancy.central() as con:
        vg_id = con.execute("SELECT id FROM vg WHERE slug = 'vg-a'").fetchone()[0]
        return fees.calculate(con, vg_id, "9000001", _tenants(), **kwargs)


def _update(sql, *params):
    with db.connection(tenancy.tenant_path("wehr-a1")) as con:
        con.execute(sql, params)


def test_unknown_record_and_missing_schedule(vg, monkeypatch):
    _incident(vg, monkeypatch)
    with tenancy.central() as con:
        vg_id = con.execute("SELECT id FROM vg WHERE slug = 'vg-a'").fetchone()[0]
        with pytest.raises(ValueError, match="noch keine Wehr"):
            fees.calculate(con, vg_id, "0000000", _tenants())
        with pytest.raises(ValueError, match="gibt es nicht"):
            fees.calculate(con, vg_id, "9000001", _tenants(), schedule_id=99999)
        con.execute("DELETE FROM fee_schedule WHERE vg_id = ?", (vg_id,))
        with pytest.raises(ValueError, match="keine Gebührenordnung hinterlegt"):
            fees.calculate(con, vg_id, "9000001", _tenants())


def test_day_before_first_schedule_has_no_valid_version(vg, monkeypatch):
    _incident(vg, monkeypatch)
    _update("UPDATE incident SET started_at = '2020-01-01T10:00:00', ended_at = '2020-01-01T11:00:00'")
    with pytest.raises(ValueError, match="Für den Einsatztag 2020-01-01"):
        _calculate()


def test_incomplete_incident_produces_hints(vg, monkeypatch):
    _incident(vg, monkeypatch)
    _update("UPDATE vehicle SET crew = NULL")
    _update("UPDATE incident SET ended_at = NULL")
    _update("UPDATE vehicle SET finished = NULL")
    hints = _calculate()["hints"]
    assert any("Einsatzende fehlt" in h for h in hints)
    assert any("keine Mannschaftsstärke" in h for h in hints)
    assert any("Beginn oder Ende des Einsatzes fehlt" in h for h in hints)


def test_incident_longer_than_a_day_warns_about_clock_times(vg, monkeypatch):
    _incident(vg, monkeypatch)
    _update("UPDATE incident SET ended_at = '2025-03-14T10:00:00'")
    assert any("länger als 24 Stunden" in h for h in _calculate()["hints"])
