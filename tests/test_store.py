# -*- coding: utf-8 -*-
import pytest

from app import db, store


def test_migrates_legacy_german_schema_with_data():
    con = db.connect(":memory:")
    db.TENANT_MIGRATIONS[0](con)                    # Schritt 1: altes deutsches Schema
    con.execute("PRAGMA user_version = 1")
    con.execute("INSERT INTO einsatz (id, jahr, nr, beginn, stichwort, quelle, personen_gh) "
                "VALUES (1, 2025, 7, '2025-01-05T10:00:00', 'H2', 'excel', 2)")
    con.execute("INSERT INTO fahrzeug VALUES (1, '02/45', NULL, 6, '10:03:00', '10:07:00')")
    con.execute("INSERT INTO kamerad VALUES (1, 'Muster, Max', 'Muster', 'Max', 1)")
    con.execute("INSERT INTO anwesenheit VALUES (1, 1, 'Maschinist', '02/45')")
    con.commit()

    db.migrate(con)
    assert con.execute("PRAGMA user_version").fetchone()[0] == len(db.TENANT_MIGRATIONS)
    incident = store.load_incident(con, 1)
    assert (incident["year"], incident["number"], incident["keyword"], incident["station_staff"]) == (2025, 7, "H2", 2)
    assert incident["vehicles"]["02/45"]["crew"] == 6
    assert incident["people"][0]["role"] == "Maschinist"
    # Fremdschlüssel zeigen nach dem Umbenennen auf die neuen Tabellen
    store.delete_incident(con, 1)
    assert con.execute("SELECT COUNT(*) FROM attendance").fetchone()[0] == 0
    con.close()


FIELDS = {"number": 5, "started_at": "2026-06-04T10:00", "ended_at": "2026-06-04T11:00", "keyword": " B2 ",
          "subcode": "07", "description": "BMA", "place": "Rheinbrohl", "unit_leader": "", "station_staff": "3"}


def test_create_normalizes_and_derives(con):
    incident_id = store.create_incident(con, FIELDS, source="pdf", filename="05-26.pdf", warnings=["Hinweis"])
    incident = store.load_incident(con, incident_id)
    assert incident["started_at"] == "2026-06-04T10:00:00"
    assert incident["keyword"] == "B2" and incident["station_staff"] == 3
    assert incident["year"] == 2026
    assert incident["weekend_or_holiday"] == 1          # Fronleichnam
    assert incident["warnings"] == ["Hinweis"]


@pytest.mark.parametrize("keyword, subcode, expected", [
    ("s1.00", "", ("S1", "00")), ("B2.07", "99", ("B2", "07")), ("B207", "", ("B2", "07")), ("b2 07", "", ("B2", "07")),
    ("H1.3", "", ("H1", "03")), ("h1.", "03", ("H1", "03")), ("w1", "01", ("W1", "01")), ("BMA", "", ("BMA", ""))])
def test_full_keyword_is_split(con, keyword, subcode, expected):
    incident_id = store.create_incident(con, {**FIELDS, "keyword": keyword, "subcode": subcode}, source="pdf")
    incident = store.load_incident(con, incident_id)
    assert (incident["keyword"], incident["subcode"]) == expected


def test_leader_names_use_known_spelling(con):
    store.create_incident(con, {**FIELDS, "unit_leader": "Muster, M."}, source="pdf")
    leaders = store.LeaderNames(con)
    person = {"name": "Max Muster"}                     # ohne Namensspalten, Konvention "Vorname Nachname"
    assert leaders.spelling(person) == "Muster, M."
    assert leaders.is_leader("M. Muster", person) and not leaders.is_leader("E. Muster", person)


def test_duplicates_are_rejected(con):
    store.create_incident(con, FIELDS, source="pdf")
    with pytest.raises(store.DuplicateIncident):
        store.create_incident(con, FIELDS, source="pdf")
    other = store.create_incident(con, {**FIELDS, "number": 6}, source="pdf")
    with pytest.raises(store.DuplicateIncident):
        store.update_incident(con, other, {"number": 5})


def test_update_rederives_weekend(con):
    incident_id = store.create_incident(con, FIELDS, source="pdf")
    store.update_incident(con, incident_id, {"started_at": "2026-06-03T10:00:00"})
    incident = store.load_incident(con, incident_id)
    assert incident["weekend_or_holiday"] == 0
    assert incident["modified"]
    with pytest.raises(KeyError):
        store.update_incident(con, 999, {})


def test_member_directory_keeps_relatives_apart(con):
    members = store.MemberDirectory(con)
    max_id = members.find_or_create("Kunz", "Max")
    assert members.find_or_create("Kunz", "Max") == max_id
    assert members.find_or_create("Kunz", "Erika") != max_id       # gleicher Nachname, anderer Vorname
    assert members.names[max_id] == "Kunz, Max"
