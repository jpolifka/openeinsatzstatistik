# -*- coding: utf-8 -*-
"""Randfälle der Ableitung, der Prüfhinweise und des Abgleichs in report.py."""
import copy
import dataclasses
import datetime as dt

from app import report
from conftest import CFG
from test_report import read


def test_town_is_used_when_district_is_unknown():
    r = read()
    r["district"], r["town"] = "Unbekannter Ortsteil", CFG.place_names[0]
    assert report._place(r, CFG) == CFG.place_names[0]
    r["district"], r["town"] = "Unbekannt", "Auch unbekannt"
    assert report._place(r, CFG) == "Unbekannt"


def test_missing_times_are_reported():
    r = read()
    for v in r["vehicles"]:
        v["alerted"], v["finished"] = None, None
    r["first_alarm"] = None
    report.derive(r, CFG)
    assert r["started_at"] is None and r["ended_at"] is None
    assert {"Einsatzbeginn nicht ermittelbar", "Einsatzende nicht ermittelbar"} <= set(r["warnings"])


def test_plausibility_checks():
    r = read()
    r["warnings"].clear()
    r["started_at"], r["ended_at"] = dt.datetime(2025, 3, 12, 10), dt.datetime(2025, 3, 12, 9)
    r["people"] = []
    r["number"] = None
    report.check_plausibility(r, dataclasses.replace(CFG, numbering="bks"))
    assert any("vor Einsatzbeginn" in w for w in r["warnings"])
    assert "Anwesenheitsliste leer" in r["warnings"]
    assert "Einsatzbericht-Nr. nicht erkannt" in r["warnings"]
    r["warnings"].clear()
    r["ended_at"] = r["started_at"] + dt.timedelta(hours=report.MAX_DURATION_HOURS + 1)
    report.check_plausibility(r, dataclasses.replace(CFG, numbering="by_date"))
    assert any("über" in w for w in r["warnings"])
    assert "Einsatzbericht-Nr. nicht erkannt" not in r["warnings"]


def test_current_warnings_of_stored_incident():
    assert report.current_warnings({"started_at": None, "ended_at": None, "people": []}) == [
        "Einsatzbeginn fehlt", "Einsatzende fehlt – Dauer und Personalstunden sind unvollständig",
        "Anwesenheitsliste leer – Personalstunden sind unvollständig"]
    long = {"started_at": "2025-03-12T10:00:00", "ended_at": "2025-03-14T10:00:00", "people": [{"name": "x"}]}
    assert [w for w in report.current_warnings(long) if "über" in w]
    assert report.current_warnings({"started_at": "2025-03-12T10:00:00", "ended_at": "2025-03-12T11:00:00",
                                    "people": [{"name": "x"}]}) == []


def test_unknown_own_vehicle_gets_new_block_once():
    r = read()
    extra = copy.deepcopy(r["vehicles"][0])
    extra["name"] = "FL NR#.MUS 02/99-01"
    extra["call_sign"] = None
    r["vehicles"].append(extra)
    slots = report.assign_vehicles(r, CFG)
    r["slots"] = slots
    assert "02/99" in r["new_vehicles"] and "02/99" in slots
    assert report.new_fleet_vehicles(r) == [("02/99", "FL NR#.MUS 02/99-01")]
    # Zweites, gleichnamiges Fahrzeug: Block ist belegt, wird nicht doppelt aufgenommen
    twin = copy.deepcopy(extra)
    r["vehicles"].append(twin)
    report.assign_vehicles(r, CFG)
    assert r["new_vehicles"].count("02/99") == 1


def test_attendance_compared_by_name_without_ids():
    stored = {"manual_fields": [], "vehicles": {}, "people": [{"name": "Muster, Max", "role": "A"}]}
    same = {"vehicles": {}, "people": [{"name": "Muster, Max", "role": "A"}]}
    other = {"vehicles": {}, "people": [{"last_name": "Beispiel", "first_name": "Erika", "role": "A"}]}
    base = {k: None for k in report.COMPARED_FIELDS}
    assert report.differences({**stored, **base}, {**same, **base}, CFG) == []
    diffs = report.differences({**stored, **base}, {**other, **base}, CFG)
    assert [d["field"] for d in diffs] == ["Anwesende"]
