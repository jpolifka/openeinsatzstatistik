# -*- coding: utf-8 -*-
"""Fehlerpfade und Randfälle von store und rbac (Eingabeprüfung, veraltete Revisionen, Leitplanken)."""
import pytest

from app import rbac, store, tenancy
from test_store import FIELDS


# ---------------------------------------------------------------- store: Eingaben
@pytest.mark.parametrize("change, message", [
    ({"number": -1}, "nicht negativ"),
    ({"station_staff": -2}, "nicht negativ"),
    ({"injured": -1}, "Anzahlen"),
    ({"started_at": "2026-06-04T10:00:00+02:00"}, "Zeitzonen"),
    ({"ended_at": "2026-06-04T09:00"}, "nicht vor dem Beginn"),
])
def test_invalid_fields_are_rejected(con, change, message):
    with pytest.raises(ValueError, match=message):
        store.create_incident(con, {**FIELDS, **change}, source="pdf")


def test_member_found_by_stored_name_is_reused(con):
    members = store.MemberDirectory(con)
    first = members.find_or_create("Muster", "Max")
    # Matcher kennt den Namen nicht unter dieser Schreibweise, die Zeile mit gleichem Anzeigenamen aber schon
    members.matcher = None
    assert members.find_or_create("Muster", "Max") == first


def test_renumber_ignores_missing_year(con):
    assert store.renumber(con, None) is None


def test_leader_names(con):
    incident_id = store.create_incident(con, {**FIELDS, "unit_leader": "M. Muster"}, source="pdf")
    leaders = store.LeaderNames(con)
    person = {"name": "Muster, Max"}
    assert leaders.spelling(person) == leaders.spelling(person)            # zweiter Aufruf aus dem Zwischenspeicher
    assert isinstance(leaders.is_leader("M. Muster", person), bool)
    assert store.person_names({"last_name": "Muster", "first_name": "Max", "name": "x"}) == ("Muster", "Max")
    assert incident_id


# ---------------------------------------------------------------- store: Fahrzeuge und Anwesenheit
def test_replace_vehicles_rejects_invalid_crew_and_time(con):
    incident_id = store.create_incident(con, FIELDS, source="pdf")
    with pytest.raises(ValueError, match="ungültig"):
        store.replace_vehicles(con, incident_id, [{"call_sign": "02/45", "crew": 100}])
    with pytest.raises(ValueError, match="Uhrzeit"):
        store.replace_vehicles(con, incident_id, [{"call_sign": "02/45", "crew": 1, "departed": "25:99"}])


def test_replace_attendance_skips_blank_names_and_rejects_unknown_member(con):
    incident_id = store.create_incident(con, FIELDS, source="pdf")
    store.replace_attendance(con, incident_id, [{"name": "   "}, {"name": "Beispiel, Erika", "role": " Maschinist "}])
    people = store.load_incident(con, incident_id)["people"]
    assert [(p["name"], p["role"], p["manual"]) for p in people] == [("Beispiel, Erika", "Maschinist", 1)]
    with pytest.raises(ValueError, match="Unbekannter Kamerad"):
        store.replace_attendance(con, incident_id, [{"id": 9999}])


def test_update_and_delete_with_stale_revision(con):
    incident_id = store.create_incident(con, FIELDS, source="pdf")
    with pytest.raises(store.StaleIncident):
        store.update_incident(con, incident_id, {"description": "x"}, revision=7)
    with pytest.raises(store.StaleIncident):
        store.delete_incident(con, incident_id, revision=7)
    with pytest.raises(KeyError):
        store.update_incident(con, 9999, {"description": "x"})
    store.delete_incident(con, incident_id, revision=0)
    assert con.execute("SELECT COUNT(*) FROM incident").fetchone()[0] == 0


def test_update_that_loses_the_race_reports_stale(con, monkeypatch):
    """Zwischen Lesen und Schreiben ändert ein anderer: das bedingte UPDATE trifft keine Zeile."""
    incident_id = store.create_incident(con, FIELDS, source="pdf")
    real = con.execute

    class Racing:
        def __getattr__(self, name):
            return getattr(con, name)

        def execute(self, sql, params=()):
            if sql.lstrip().startswith("UPDATE incident SET"):
                real("UPDATE incident SET revision = revision + 1 WHERE id = ?", (incident_id,))
            return real(sql, params)

    with pytest.raises(store.StaleIncident):
        store.update_incident(Racing(), incident_id, {"description": "x"}, revision=0)


def test_pending_report_replaces_older_version(con):
    report = {"bks_report_id": "9000001", "bks_record_id": "9000000", "keyword": "B2", "subcode": "08"}
    first = store.add_pending(con, report, "a.pdf", b"x", "a@example.org")
    second = store.add_pending(con, report, "b.pdf", b"yy", "a@example.org")
    assert [p["filename"] for p in store.pending_reports(con)] == ["b.pdf"]
    assert store.pending_usage(con) == (1, 2)
    assert store.pending_pdf(con, second) == ("b.pdf", b"yy")
    assert store.pending_pdf(con, 999) == (None, None)
    store.delete_pending(con, second)
    assert store.pending_reports(con) == []


def test_add_fleet_vehicles_and_usage(con):
    import datetime as dt
    store.add_fleet_vehicles(con, [("02/45", "FL NR#.MUS 02/45-01")], dt.date(2025, 1, 1))
    store.add_fleet_vehicles(con, [("02/45", "andere"), ("02/24", None)], None)          # vorhandenes bleibt
    rows = {r["call_sign"]: r for r in con.execute("SELECT * FROM fleet")}
    assert set(rows) == {"02/45", "02/24"} and rows["02/45"]["in_service_from"] == "2025-01-01"
    assert store.vehicles_with_data(con) == {}


# ---------------------------------------------------------------- rbac: Leitplanken und Schlüssel
@pytest.fixture
def roles(data_dir):
    with tenancy.central() as con:
        yield con, rbac.Roles(con)


def _save(con, roles, **values):
    base = dict(role_id=None, vg_id=None, scope="tenant", label="Neue Rolle", description="", parent_id=None,
                permissions=[], granted_by=[], grants=[])
    return rbac.save_role(con, roles, **{**base, **values})


@pytest.mark.parametrize("values, message", [
    ({"label": "x"}, "2 bis 60"),
    ({"scope": "kreis"}, "Bereich"),
    ({"permissions": ["gibt.es.nicht"]}, "Unbekanntes Recht"),
    ({"parent_id": 99999}, "Erben"),
])
def test_save_role_validates_input(roles, values, message):
    con, loaded = roles
    with pytest.raises(rbac.Invalid, match=message):
        _save(con, loaded, **values)


def test_save_role_distribution_rules(roles):
    con, loaded = roles
    vg_id = con.execute("INSERT INTO vg (slug, name) VALUES ('vg-x', 'VG X')").lastrowid
    own = _save(con, loaded, vg_id=vg_id, label="Eigene Rolle")
    loaded = rbac.Roles(con)
    # Verteilung nur auf Rollen, die in der VG gelten
    with pytest.raises(rbac.Invalid, match="in dieser VG gelten"):
        _save(con, loaded, vg_id=vg_id, label="Verteiler", grants=[99999])
    other_vg = con.execute("INSERT INTO vg (slug, name) VALUES ('vg-y', 'VG Y')").lastrowid
    with pytest.raises(rbac.Invalid, match="in dieser VG gelten"):
        _save(con, loaded, vg_id=other_vg, label="Verteiler", grants=[own])
    # Globale Rollen verteilen nur globale Rollen
    with pytest.raises(rbac.Invalid, match="in dieser VG gelten"):
        _save(con, loaded, vg_id=None, label="Global", grants=[own])


def test_make_key_counts_up_on_collision(roles):
    con, _ = roles
    first = rbac.make_key(con, "Sonder Rolle", None)
    con.execute("INSERT INTO role (key, vg_id, scope, label) VALUES (?, NULL, 'tenant', 'x')", (first,))
    assert rbac.make_key(con, "Sonder Rolle", None) == f"{first}_2"
    assert rbac.make_key(con, "Größe ß", None) == "groesse_ss"


def test_unknown_role_has_no_permissions(roles):
    _, loaded = roles
    assert loaded.permissions(99999) == frozenset()


def test_delete_role_guards(roles):
    con, loaded = roles
    system = loaded.find("viewer", None)
    with pytest.raises(rbac.Invalid, match="Systemrollen"):
        rbac.delete_role(con, loaded, system.id)
    custom = _save(con, loaded, label="Löschbar")
    rbac.delete_role(con, rbac.Roles(con), custom)
    assert rbac.Roles(con).get(custom) is None
