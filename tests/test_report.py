# -*- coding: utf-8 -*-
"""PDF-Auswertung mit erfundenem Berichtstext im Aufbau des BKS-Portals."""
import datetime as dt
import copy

from app import report, store
from app.pdf_report import parse_report
from conftest import CFG

LEFT = """EINSATZBERICHT
Einsatzbericht-Nr.: 17/25
Einsatzstichwort: B2.08
Meldebild: Zimmerbrand
Einsatzstelle - Ort: Rheinbrohl
Einsatzstelle - Ortsteil: Rheinbrohl (NR)
Einsatzstelle - Straße: Musterweg 4
Einsatzstelle - Objekt: WH Musterhaus
"""
VEHICLES = """Fahrzeuge Stärke Alarmiert Ausrücken
FL NR#.BHÖ 02/45-01 0 / 1 / 1 / 2 / 0 12.03.25 10:09:41 12.03.25 10:12:04 12.03.25 10:16:25 Ja 12.03.25 10:44:04 12.03.25 10:48:21
FL NR#.BHÖ 02/24-01 0 / 0 / 0 / 0 / 0 12.03.25 10:08:30 12.03.25 10:13:00 12.03.25 10:18:00 Ja 12.03.25 10:44:04 12.03.25 10:50:00
FL NR#.BHÖ 01/46-01 0 / 1 / 5 / 6 / 2 12.03.25 10:05:00 12.03.25 10:07:00 12.03.25 10:12:00 Ja 12.03.25 10:50:00 12.03.25 10:56:59
FL NR#.LIN 0 / 0 / 2 / 2 / 0 12.03.25 10:09:00 - - Nein - 12.03.25 11:05:00
"""
PEOPLE = """Anwesenheitsliste:
Name Vorname Fahrzeug Von Bis Funktion AGT Min (AGT) Bemerkung
Muster Max FL NR#.BHÖ 02/45-01 12.03.25 10:09 12.03.25 10:48 Einheitsführer nein 0
Beispiel Erika FL NR#.BHÖ 02/45-01 12.03.25 10:09 12.03.25 10:48 Maschinist nein 0
Probe Otto 12.03.25 10:09 12.03.25 10:48 nein 0
Unterschriften zu Einsatzbericht 1
"""
FULL = LEFT + "Einsatzleiter: Max Muster\n" + VEHICLES + PEOPLE


def read(full=FULL, left=LEFT, right="", filename="17-25_B2_Test.pdf"):
    r = parse_report(full, left, right, filename, CFG.unit_prefix)
    report.complete_number(r)
    report.derive(r, CFG)
    report.check_plausibility(r)
    return r


def test_parse_fields_vehicles_and_people():
    r = parse_report(FULL, LEFT, "", "17-25_B2_Test.pdf", CFG.unit_prefix)
    assert (r["number"], r["keyword"], r["subcode"]) == (17, "B2", "08")
    assert r["district"] == "Rheinbrohl"
    assert [v["call_sign"] for v in r["vehicles"]] == ["02/45", "02/24", "01/46", None]
    assert r["vehicles"][0]["crew"] == 2 and r["vehicles"][0]["respiratory"] == 0
    assert r["vehicles"][3]["departed"] is None
    assert [(p["last_name"], p["vehicle"], p["role"]) for p in r["people"]] == [
        ("Muster", "02/45", "Einheitsführer"), ("Beispiel", "02/45", "Maschinist"), ("Probe", None, "")]
    assert r["people"][0]["vehicle_name"] == "FL NR#.BHÖ 02/45-01"


def test_derived_fields():
    r = read()
    assert r["started_at"] == dt.datetime(2025, 3, 12, 10, 8, 30)    # früheste Alarmierung 02/..
    assert r["ended_at"] == dt.datetime(2025, 3, 12, 11, 5)          # FEZ endet zuletzt
    assert r["place"] == "Rheinbrohl"
    assert r["description"] == "Zimmerbrand / Musterhaus"
    assert r["unit_leader"] == "M. Muster"
    assert r["station_staff"] == 1                                   # 3 Anwesende, 2 auf Fahrzeugen
    assert r["weekend_or_holiday"] == 0
    assert set(r["slots"]) == {"02/45", "02/24"}
    assert r["warnings"] == []


def test_fire_watch_and_missing_unit_leader():
    full = FULL.replace("B2.08", "Brandsicherheitswache").replace("Einheitsführer", "Gruppenführer")
    r = read(full, LEFT.replace("B2.08", "Brandsicherheitswache"))
    assert (r["keyword"], r["subcode"]) == ("S1", "00")
    assert r["description"].startswith("BSW / ")
    assert r["unit_leader"] == "M. Muster"                           # Einsatzleiter ist anwesend
    assert any("Kein Einheitsführer" in w for w in r["warnings"])


def test_number_from_other_spelling_or_filename():
    r = read(FULL.replace("17/25", "17-25"), LEFT.replace("17/25", "17-25"))
    assert r["number"] == 17 and r["warnings"] == []
    r = read(FULL.replace("17/25", ""), LEFT.replace("17/25", ""), filename="61-25_B1_Test.pdf")
    assert r["number"] == 61
    assert any("aus Dateiname" in w for w in r["warnings"])
    r = read(filename="18-25_B2_Test.pdf")
    assert any("weicht vom Dateinamen" in w for w in r["warnings"])
    r = read(FULL.replace("17/25", "B17/2025"), LEFT.replace("17/25", "B17/2025"))
    assert r["number"] == 17 and r["warnings"] == []


def test_substitute_vehicle_takes_block():
    full = FULL.replace("02/45-01", "01/23-01")
    r = read(full)
    assert r["slots"]["02/45"]["name"] == "FL NR#.BHÖ 01/23-01"
    assert any("als Ersatz für 02/45" in w for w in r["warnings"])


def test_save_and_differences(con):
    r = read()
    incident_id = report.save(con, r, report.to_fields(r))
    stored = store.load_incident(con, incident_id)
    assert [p["name"] for p in stored["people"]] == ["Muster, Max", "Beispiel, Erika", "Probe, Otto"]
    assert stored["vehicles"]["02/45"]["departed"] == "10:12:04"

    incident, existing = report.preview(con, r)
    assert existing["id"] == incident_id
    assert report.differences(existing, incident, CFG) == []
    assert not any(p["new"] for p in incident["people"])

    changed = {**incident, "unit_leader": "E. Beispiel"}
    assert report.differences(existing, changed, CFG) == [{"field": "Einheitsführung", "stored": "M. Muster", "report": "E. Beispiel"}]


def test_older_layout_with_incident_site_in_right_column():
    """Berichte von 2025: Meldebild und Einsatzstelle stehen in der rechten Spalte von Seite 1."""
    site = LEFT.split("Meldebild")[1]
    left = LEFT.split("Meldebild")[0]
    r = read(left=left, right="Meldebild" + site)
    assert r["reported_as"] == "Zimmerbrand"
    assert r["place"] == "Rheinbrohl"
    assert r["description"] == "Zimmerbrand / Musterhaus"


def test_comparison_detects_text_people_and_seconds(con):
    r = read()
    report.save(con, r, report.to_fields(r))
    incident, existing = report.preview(con, r)
    changed = copy.deepcopy(incident)
    changed["description"] += " korrigiert"
    changed["dispatch_number"] = "TEST-42"
    changed["people"][0]["role"] = "Andere Funktion"
    changed["vehicles"]["02/45"]["arrived"] = "10:16:26"
    fields = {d["field"] for d in report.differences(existing, changed, CFG)}
    assert {"Beschreibung", "Leitstellen-Nr.", "Anwesende", "Eintreffen 02/45"} <= fields


def test_abort_reason_is_read_from_header_line():
    left = LEFT + "Zeitpunkt der Alarmierung der ersten Einheit: 12.03.2025 10:00 Einsatzabbruch: Täuschungsalarm\n"
    assert parse_report(FULL.replace(LEFT, left), left, "", "17-25_B2_Test.pdf", CFG.unit_prefix)["abort_reason"] == "Täuschungsalarm"
    assert parse_report(FULL, LEFT, "", "17-25_B2_Test.pdf", CFG.unit_prefix)["abort_reason"] is None


DETAILS = """Einsatzstelle - Bemerkung Einsatzanlass: Rauch kein Einfluss Nummer der Gefahrenmeldeanlage: 301986
Einatztaktik: Innenangriff Brand unter Kontrolle: 12.03.2025 10:41
Feuer aus: 12.03.2025 11:02 Brandwache gestellt bis: 12.03.2025 14:00
Menschenrettung über baulichen Rettungsweg: 2
Menschenrettung über Hubrettungsfahrzeug: 1
Rettung von Kleinvieh: 3
Verletzte andere Personen: 1
Verletzte Feuerwehrangehörige: 0
"""


def test_details_are_read_from_the_report():
    full = FULL.replace(LEFT, LEFT + DETAILS)
    r = parse_report(full, LEFT + DETAILS, "", "17-25_B2_Test.pdf", CFG.unit_prefix)
    assert r["alarm_system"] == "301986" and r["tactic"] == "Innenangriff"
    assert r["fire_controlled_at"] == dt.datetime(2025, 3, 12, 10, 41)
    assert r["fire_out_at"] == dt.datetime(2025, 3, 12, 11, 2)
    assert r["fire_watch_until"] == dt.datetime(2025, 3, 12, 14, 0)
    assert (r["rescued"], r["rescued_animals"], r["injured"], r["injured_firefighters"], r["deceased"]) == (3, 3, 1, 0, None)
    assert [v["deployed"] for v in r["vehicles"]] == [1, 1, 1, 0]
    assert [v["respiratory"] for v in r["vehicles"]] == [0, 0, 2, 0]


def test_missing_details_stay_unknown():
    r = parse_report(FULL, LEFT, "", "17-25_B2_Test.pdf", CFG.unit_prefix)
    assert all(r[name] is None for name in ("alarm_system", "tactic", "fire_controlled_at", "rescued", "injured", "deceased"))


def test_agt_per_person_and_details_are_saved(con):
    people = PEOPLE.replace("Maschinist nein 0", "Maschinist AGT 25")
    full = LEFT + DETAILS + "Einsatzleiter: Max Muster\n" + VEHICLES + people
    r = read(full=full, left=LEFT + DETAILS)
    assert [(p["agt"], p["agt_min"]) for p in r["people"]] == [(False, 0), (True, 25), (False, 0)]
    incident_id = report.save(con, r, report.to_fields(r))
    stored = store.load_incident(con, incident_id)
    assert (stored["alarm_system"], stored["tactic"], stored["rescued"], stored["deceased"]) == ("301986", "Innenangriff", 3, None)
    assert stored["fire_controlled_at"] == "2025-03-12T10:41:00" and stored["building"] == "WH Musterhaus"
    assert {p["name"]: (p["agt"], p["agt_min"]) for p in stored["people"]}["Beispiel, Erika"] == (1, 25)
    assert (stored["vehicles"]["02/45"]["deployed"], stored["vehicles"]["02/24"]["respiratory"]) == (1, 0)
    incident, existing = report.preview(con, r)
    assert report.differences(existing, incident, CFG) == []
