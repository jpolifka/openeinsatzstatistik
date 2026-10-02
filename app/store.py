# -*- coding: utf-8 -*-
"""Einsätze, Fahrzeuge, Kameraden und Anwesenheit in der Datenbank lesen und schreiben."""
import json
import re

from app.holidays import is_weekend_or_holiday
from app.names import NameMatcher, leader_spelling, matches_leader, normalize, split_name
from app.timeutil import normalize_iso, parse_iso, year_of

# Ganzes Stichwort mit oder ohne Punkt: B2.07, B207, b2 07, S1.00, B2.
FULL_KEYWORD = re.compile(r"([A-Za-z]\d)\s*[.\s]?\s*(\d{0,2})")

# Bearbeitbare Felder eines Einsatzes – Grundlage für Formular, Speichern und Abgleich
FIELDS = ("number", "started_at", "ended_at", "keyword", "subcode", "description", "place",
          "unit_leader", "station_staff", "dispatch_number")
INT_FIELDS = ("number", "station_staff")
TEXT_FIELDS = tuple(name for name in FIELDS if name not in INT_FIELDS + ("started_at", "ended_at", "dispatch_number"))


class DuplicateIncident(ValueError):
    def __init__(self, number, year):
        super().__init__(f"Einsatz Nr. {number}/{year} ist bereits vorhanden.")


def to_int(value):
    if isinstance(value, (bool, int, float)):
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def split_keyword(keyword, subcode=""):
    """Ganzes Stichwort im Feld Stichwort in Stichwort und Stufe aufteilen: B207 und B2.07 -> (B2, 07)."""
    m = FULL_KEYWORD.fullmatch(keyword or "")
    if not m:
        return (keyword or "").upper(), subcode
    return m.group(1).upper(), m.group(2).zfill(2) if m.group(2) else subcode


def normalize_fields(fields, weekend_or_holiday=None):
    """Eingaben bereinigen und Jahr sowie Wochenende/Feiertag aus dem Beginn ableiten."""
    f = {name: fields.get(name) for name in FIELDS}
    f["number"] = to_int(f["number"])
    f["station_staff"] = to_int(f["station_staff"]) or 0
    f["started_at"], f["ended_at"] = normalize_iso(f["started_at"]), normalize_iso(f["ended_at"])
    for name in TEXT_FIELDS:
        f[name] = (f[name] or "").strip()
    f["keyword"], f["subcode"] = split_keyword(f["keyword"], f["subcode"])
    # Einsatznummer der Leitstelle: leer heißt unbekannt (Altdaten aus Excel)
    f["dispatch_number"] = str(f["dispatch_number"] or "").strip() or None
    start = parse_iso(f["started_at"])
    f["year"] = year_of(start)
    if weekend_or_holiday is None:
        weekend_or_holiday = bool(start and is_weekend_or_holiday(start.date()))
    f["weekend_or_holiday"] = int(weekend_or_holiday)
    return f


# ---------------------------------------------------------------- Kameraden
def person_names(person):
    """(nachname, vorname) eines Anwesenden – aus den Namensspalten oder aus dem Anzeigenamen."""
    if person.get("last_name") and person.get("first_name"):
        return person["last_name"], person["first_name"]
    return split_name(person["name"])


class LeaderNames:
    """EHF-Schreibweisen der vorhandenen Einsätze, damit ein Anwesender per Klick als EHF eingetragen
    und der eingetragene EHF in der Anwesenheit erkannt wird – unabhängig von der Namenskonvention."""

    def __init__(self, con):
        self.spellings = {r[0]: r[1] for r in con.execute(
            "SELECT unit_leader, COUNT(*) FROM incident WHERE unit_leader != '' GROUP BY unit_leader")}
        self._cache = {}

    def spelling(self, person):
        key = person_names(person)
        if key not in self._cache:
            self._cache[key] = leader_spelling(self.spellings, *key)
        return self._cache[key]

    @staticmethod
    def is_leader(unit_leader, person):
        return matches_leader(unit_leader, *person_names(person))


class MemberDirectory:
    """Namensabgleich gegen alle bekannten Kameraden; legt Unbekannte bei Bedarf an."""

    def __init__(self, con):
        self.con = con
        self._load()

    def _load(self):
        rows = self.con.execute("SELECT id, name, first_name FROM member").fetchall()
        self.names = {r["id"]: r["name"] for r in rows}
        self.first_names = {r["id"]: r["first_name"] for r in rows}
        self.matcher = NameMatcher([(r["id"], r["name"]) for r in rows]) if rows else None

    def find(self, last_name, first_name):
        if not self.matcher:
            return None
        member_id = self.matcher.match(last_name, first_name)
        # Der Abgleich ordnet bei eindeutigem Nachnamen ohne Blick auf den Vornamen zu –
        # ein neues Mitglied mit gleichem Nachnamen darf nicht beim Verwandten landen.
        known_first = self.first_names.get(member_id)
        if member_id is not None and first_name and known_first:
            given, known = normalize(first_name)[:1], normalize(known_first)[:1]
            if given and known and given != known and normalize(last_name)[:1] != known:
                return None
        return member_id

    def find_or_create(self, last_name, first_name, name=None):
        member_id = self.find(last_name, first_name)
        if member_id is not None:
            return member_id
        name = name or f"{last_name}, {first_name}".strip(", ")
        existing = self.con.execute("SELECT id FROM member WHERE name = ?", (name,)).fetchone()
        if existing:
            return existing["id"]
        member_id = self.con.execute(
            "INSERT INTO member (name, last_name, first_name, sort_order) "
            "VALUES (?, ?, ?, (SELECT COALESCE(MAX(sort_order), 0) + 1 FROM member))",
            (name, last_name, first_name)).lastrowid
        self._load()
        return member_id


def members_of_year(con, year):
    """Kameraden mit mindestens einem Einsatz im Jahr, in der Reihenfolge der Anwesenheitsliste."""
    return [dict(r) for r in con.execute(
        "SELECT DISTINCT m.id, m.name, m.sort_order FROM member m "
        "JOIN attendance a ON a.member_id = m.id JOIN incident i ON i.id = a.incident_id "
        "WHERE i.year = ? ORDER BY m.sort_order, m.name", (year,))]


# ---------------------------------------------------------------- Lesen
def load_incidents(con, year=None, ids=None):
    """Einsätze mit Fahrzeugen ({funkrufname: …}) und Anwesenden als Dicts."""
    sql, params = "SELECT * FROM incident", []
    if year is not None:
        sql, params = sql + " WHERE year = ?", [year]
    elif ids is not None:
        sql, params = sql + f" WHERE id IN ({_placeholders(ids)})", list(ids)
    rows = [dict(r) for r in con.execute(sql + " ORDER BY year, number IS NULL, number, started_at", params)]
    by_id = {r["id"]: r for r in rows}
    if not by_id:
        return []
    for r in rows:
        r["warnings"] = json.loads(r["warnings"] or "[]")
        r["vehicles"], r["people"] = {}, []
    in_ids = f"IN ({_placeholders(by_id)})"
    for v in con.execute(f"SELECT * FROM vehicle WHERE incident_id {in_ids}", list(by_id)):
        by_id[v["incident_id"]]["vehicles"][v["call_sign"]] = dict(v)
    for p in con.execute(
            "SELECT a.incident_id, a.role, a.vehicle, m.id, m.name, m.last_name, m.first_name "
            f"FROM attendance a JOIN member m ON m.id = a.member_id WHERE a.incident_id {in_ids} "
            "ORDER BY m.sort_order, m.name", list(by_id)):
        by_id[p["incident_id"]]["people"].append(dict(p))
    return rows


def load_incident(con, incident_id):
    found = load_incidents(con, ids=[incident_id])
    return found[0] if found else None


def years(con):
    return [dict(r) for r in con.execute(
        "SELECT year, COUNT(*) AS count, MAX(number) AS last_number FROM incident GROUP BY year ORDER BY year")]


def incident_months(con):
    """Anzahl Einsätze je Monat über alle Jahre -> {"JJJJ-MM": anzahl}."""
    return {r[0]: r[1] for r in con.execute(
        "SELECT substr(started_at, 1, 7), COUNT(*) FROM incident WHERE started_at IS NOT NULL GROUP BY 1")}


def latest_year(con):
    row = con.execute("SELECT MAX(year) FROM incident").fetchone()
    return row[0]


def find_incident(con, year, number):
    if number is None:
        return None
    row = con.execute("SELECT id FROM incident WHERE year = ? AND number = ?", (year, number)).fetchone()
    return row["id"] if row else None


def is_empty(con):
    return not con.execute("SELECT 1 FROM incident LIMIT 1").fetchone()


# ---------------------------------------------------------------- Schreiben
def _placeholders(values):
    return ",".join("?" * len(values))


def _insert(con, table, row):
    return con.execute(f"INSERT INTO {table} ({', '.join(row)}) VALUES ({_placeholders(row)})",
                       list(row.values())).lastrowid


def create_incident(con, fields, source, filename=None, warnings=(), replace_id=None, weekend_or_holiday=None,
                    modified_by=None):
    """Einsatz anlegen (oder einen vorhandenen ersetzen) und die ID zurückgeben."""
    f = normalize_fields(fields, weekend_or_holiday)
    if replace_id:
        delete_incident(con, replace_id)
    elif find_incident(con, f["year"], f["number"]):
        raise DuplicateIncident(f["number"], f["year"])
    return _insert(con, "incident", {**f, "source": source, "filename": filename, "modified_by": modified_by,
                                     "warnings": json.dumps(list(warnings), ensure_ascii=False)})


def add_vehicle(con, incident_id, call_sign, name, crew, departed, arrived):
    _insert(con, "vehicle", {"incident_id": incident_id, "call_sign": call_sign, "name": name,
                             "crew": crew, "departed": departed, "arrived": arrived})


def add_attendance(con, incident_id, member_id, role=None, vehicle=None):
    con.execute("INSERT OR IGNORE INTO attendance (incident_id, member_id, role, vehicle) VALUES (?,?,?,?)",
                (incident_id, member_id, role, vehicle))


def update_incident(con, incident_id, changes, modified_by=None):
    """Felder ändern; Jahr und Wochenende/Feiertag werden neu abgeleitet."""
    current = con.execute("SELECT * FROM incident WHERE id = ?", (incident_id,)).fetchone()
    if not current:
        raise KeyError(incident_id)
    f = normalize_fields({**dict(current), **changes})
    other = find_incident(con, f["year"], f["number"])
    if other and other != incident_id:
        raise DuplicateIncident(f["number"], f["year"])
    assignments = ", ".join(f"{name} = ?" for name in f)
    con.execute(f"UPDATE incident SET {assignments}, modified = datetime('now', 'localtime'), modified_by = ? "
                "WHERE id = ?", [*f.values(), modified_by, incident_id])


def delete_incident(con, incident_id):
    con.execute("DELETE FROM incident WHERE id = ?", (incident_id,))
