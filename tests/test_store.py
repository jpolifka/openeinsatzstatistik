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
    moritz = members.find_or_create("Kunz", "Moritz")               # … auch mit gleicher Initiale
    assert moritz != max_id and members.find_or_create("Kunz", "Moritz") == moritz
    assert members.names[max_id] == "Kunz, Max"


def test_migration_drops_eight_minute_limit():
    con = db.connect(":memory:")
    db.migrate(con, db.TENANT_MIGRATIONS[:3])
    con.execute("INSERT INTO setting VALUES ('response_limits', '[8, 10]'), ('default_limit', '8')")
    con.commit()
    db.migrate(con)
    assert dict(con.execute("SELECT key, value FROM setting").fetchall()) == \
        {"response_limits": "[10]", "default_limit": "10"}
    con.close()


def test_find_existing_prefers_bks_report(con):
    first = store.create_incident(con, {**FIELDS, "bks_report_id": "9000003", "bks_record_id": "9000001"},
                                  source="pdf")
    other = store.create_incident(con, {**FIELDS, "number": 6}, source="pdf")
    assert store.find_existing(con, "9000003", 2026, 6) == first      # Nr. im Bericht geändert
    assert store.find_existing(con, "9999999", 2026, 6) == other      # unbekannter Bericht: über die Nr.
    assert store.find_existing(con, None, 2026, 7) is None
    with pytest.raises(store.DuplicateIncident, match="9000003"):
        store.create_incident(con, {**FIELDS, "number": 8, "bks_report_id": "9000003"}, source="pdf")
    # Die BKS-Datensätze kommen nur aus der PDF: Bearbeiten im Formular lässt sie stehen
    store.update_incident(con, first, {"description": "geändert"})
    assert store.load_incident(con, first)["bks_report_id"] == "9000003"


def test_report_rows_replace_imported_but_keep_manual(con):
    incident_id = store.create_incident(con, FIELDS, source="pdf")
    members = store.MemberDirectory(con)
    imported, manual, both = (members.find_or_create(*n) for n in (("Muster", "Max"), ("Beispiel", "Erika"),
                                                                   ("Probe", "Otto")))
    store.add_vehicle(con, incident_id, "02/45", None, 6, "10:03:00", "10:07:00")
    store.add_vehicle(con, incident_id, "02/24", None, 2, None, None, manual=True)
    store.add_vehicle(con, incident_id, "02/71", None, 3, None, None, manual=True)
    store.add_attendance(con, incident_id, imported)
    store.add_attendance(con, incident_id, manual, manual=True)
    store.add_attendance(con, incident_id, both, manual=True)

    vehicle = {"name": None, "crew": 5, "departed": "10:04:00", "arrived": "10:09:00", "alerted": "10:00:00",
               "finished": "11:00:00"}
    store.replace_report_rows(con, incident_id, [{**vehicle, "call_sign": "02/71"}],
                              [(both, "Maschinist", "02/71"), (both, "doppelt", None)])
    incident = store.load_incident(con, incident_id)
    # von Hand ergänzte Zeilen bleiben unverändert, auch wenn der Bericht sie ebenfalls nennt
    assert {cs: v["crew"] for cs, v in incident["vehicles"].items()} == {"02/24": 2, "02/71": 3}
    assert {p["id"]: (p["role"], p["manual"]) for p in incident["people"]} == \
        {manual: (None, 1), both: (None, 1)}


def test_report_rows_keep_list_when_report_has_none(con):
    incident_id = store.create_incident(con, FIELDS, source="pdf")
    member = store.MemberDirectory(con).find_or_create("Muster", "Max")
    store.add_vehicle(con, incident_id, "02/45", None, 6, "10:03:00", "10:07:00")
    store.add_attendance(con, incident_id, member)
    store.replace_report_rows(con, incident_id, [], [])
    incident = store.load_incident(con, incident_id)
    assert list(incident["vehicles"]) == ["02/45"] and len(incident["people"]) == 1


def test_manual_edit_survives_reimport(con):
    incident_id = store.create_incident(con, FIELDS, source="pdf")
    store.add_vehicle(con, incident_id, "02/45", None, 6, "10:03:00", "10:07:00")
    store.replace_vehicles(con, incident_id, [{"call_sign": "02/45", "crew": 6, "departed": "10:05", "arrived": "10:07"}])
    store.replace_report_rows(con, incident_id, [{"call_sign": "02/45", "name": None, "crew": 6, "departed": "10:03:00",
                                                  "arrived": "10:07:00"}], [])
    assert store.load_incident(con, incident_id)["vehicles"]["02/45"]["departed"] == "10:05:00"


def test_begin_immediate_serializes_number_assignment(tmp_path):
    """Zwei Schreiber, die die nächste Nummer lesen und speichern, bekommen verschiedene Nummern."""
    import threading
    from app import db
    path = str(tmp_path / "n.db")
    db.setup(path)
    numbers, barrier = [], threading.Barrier(2)

    def take():
        barrier.wait()
        with db.connection(path) as con:
            con.execute("BEGIN IMMEDIATE")
            n = store.next_number(con, 2026)
            con.execute("INSERT INTO incident (year, number, source) VALUES (2026, ?, 'test')", (n,))
            numbers.append(n)

    threads = [threading.Thread(target=take) for _ in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(numbers) == [1, 2]
