# -*- coding: utf-8 -*-
"""Einsätze, Fahrzeuge, Kameraden und Anwesenheit in der Datenbank lesen und schreiben."""
import json
import re

from app import domain
from app.holidays import is_weekend_or_holiday
from app.names import NameMatcher, leader_spelling, matches_leader, split_name
from app.timeutil import normalize_iso, parse_iso, to_iso, year_of

# Ganzes Stichwort mit oder ohne Punkt: B2.07, B207, b2 07, S1.00, B2.
FULL_KEYWORD = re.compile(r"([A-Za-z]\d)\s*[.\s]?\s*(\d{0,2})")

# Bearbeitbare Felder eines Einsatzes – Grundlage für Formular, Speichern und Abgleich
FIELDS = ("number", "started_at", "ended_at", "keyword", "subcode", "description", "place",
          "unit_leader", "station_staff", "dispatch_number")
INT_FIELDS = ("number", "station_staff")
# Datensätze im BKS-Portal (eigener Bericht, Stammdatensatz des Einsatzes): kommen aus der PDF, nicht aus dem Formular
ID_FIELDS = ("bks_report_id", "bks_record_id")
TEXT_FIELDS = tuple(name for name in FIELDS if name not in INT_FIELDS + ("started_at", "ended_at", "dispatch_number"))


class DuplicateIncident(ValueError):
    def __init__(self, number, year, message=None):
        super().__init__(message or f"Einsatz Nr. {number}/{year} ist bereits vorhanden.")


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
    f = {name: fields.get(name) for name in FIELDS + ID_FIELDS}
    f["number"] = to_int(f["number"])
    f["station_staff"] = to_int(f["station_staff"]) or 0
    f["started_at"], f["ended_at"] = normalize_iso(f["started_at"]), normalize_iso(f["ended_at"])
    for name in TEXT_FIELDS:
        f[name] = (f[name] or "").strip()
    f["keyword"], f["subcode"] = split_keyword(f["keyword"], f["subcode"])
    # Einsatznummer der Leitstelle: leer heißt unbekannt (Altdaten aus Excel)
    for name in ("dispatch_number", *ID_FIELDS):
        f[name] = str(f[name] or "").strip() or None
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
        rows = self.con.execute("SELECT id, name FROM member").fetchall()
        self.names = {r["id"]: r["name"] for r in rows}
        self.matcher = NameMatcher([(r["id"], r["name"]) for r in rows]) if rows else None

    def find(self, last_name, first_name):
        if not self.matcher:
            return None
        return self.matcher.match(last_name, first_name)

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
            "SELECT a.incident_id, a.role, a.vehicle, a.manual, m.id, m.name, m.last_name, m.first_name "
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


def find_existing(con, bks_report_id, year, number):
    """Erfasster Einsatz zu einem Bericht: über den Bericht im BKS-Portal, sonst über Jahr und Nr."""
    if bks_report_id:
        row = con.execute("SELECT id FROM incident WHERE bks_report_id = ?", (str(bks_report_id),)).fetchone()
        if row:
            return row["id"]
    return find_incident(con, year, number)


def _check_unique(con, f, incident_id=None):
    other = find_incident(con, f["year"], f["number"])
    if other and other != incident_id:
        raise DuplicateIncident(f["number"], f["year"])
    if f["bks_report_id"]:
        row = con.execute("SELECT id, number, year FROM incident WHERE bks_report_id = ?", (f["bks_report_id"],)).fetchone()
        if row and row["id"] != incident_id:
            raise DuplicateIncident(row["number"], row["year"], f"Der Bericht {f['bks_report_id']} ist schon als "
                                    f"Einsatz Nr. {row['number']}/{row['year']} erfasst.")


def next_number(con, year):
    """Nächste freie Einsatznummer des Jahres."""
    return con.execute("SELECT COALESCE(MAX(number), 0) + 1 FROM incident WHERE year = ?", (year,)).fetchone()[0]


def renumber(con, year):
    """Einsätze eines Jahres nach Beginn durchnummerieren (Nummerierung "by_date").

    Zwei Schritte über negative Nummern, damit der eindeutige Index (Jahr, Nr.) unterwegs nicht anschlägt.
    """
    if year is None:
        return
    ids = [r[0] for r in con.execute("SELECT id FROM incident WHERE year = ? ORDER BY started_at, id", (year,))]
    con.executemany("UPDATE incident SET number = ? WHERE id = ?", [(-n, i) for n, i in enumerate(ids, start=1)])
    con.executemany("UPDATE incident SET number = ? WHERE id = ?", [(n, i) for n, i in enumerate(ids, start=1)])


def is_empty(con):
    return not con.execute("SELECT 1 FROM incident LIMIT 1").fetchone()


# ---------------------------------------------------------------- Schreiben
def _placeholders(values):
    return ",".join("?" * len(values))


def _insert(con, table, row):
    return con.execute(f"INSERT INTO {table} ({', '.join(row)}) VALUES ({_placeholders(row)})",
                       list(row.values())).lastrowid


def create_incident(con, fields, source, filename=None, warnings=(), weekend_or_holiday=None, modified_by=None):
    """Einsatz anlegen und die ID zurückgeben."""
    f = normalize_fields(fields, weekend_or_holiday)
    _check_unique(con, f)
    return _insert(con, "incident", {**f, "source": source, "filename": filename, "modified_by": modified_by,
                                     "warnings": json.dumps(list(warnings), ensure_ascii=False)})


def add_vehicle(con, incident_id, call_sign, name, crew, departed, arrived, alerted=None, finished=None, manual=False):
    _insert(con, "vehicle", {"incident_id": incident_id, "call_sign": call_sign, "name": name,
                             "crew": crew, "departed": departed, "arrived": arrived,
                             "alerted": alerted, "finished": finished, "manual": int(manual)})


def add_attendance(con, incident_id, member_id, role=None, vehicle=None, manual=False):
    con.execute("INSERT OR IGNORE INTO attendance (incident_id, member_id, role, vehicle, manual) VALUES (?,?,?,?,?)",
                (incident_id, member_id, role, vehicle, int(manual)))


def replace_report_rows(con, incident_id, vehicles, attendance):
    """Fahrzeuge und Anwesenheit aus einem (erneut eingelesenen) Bericht schreiben.

    Zeilen aus dem vorigen Bericht entfallen; manuell ergänzte bleiben, außer der Bericht bringt
    dasselbe Fahrzeug bzw. dieselbe Person. attendance: [(kamerad_id, funktion, fahrzeug)].
    """
    con.execute("DELETE FROM vehicle WHERE incident_id = ? AND manual = 0", (incident_id,))
    con.execute("DELETE FROM attendance WHERE incident_id = ? AND manual = 0", (incident_id,))
    for row in vehicles:
        con.execute("DELETE FROM vehicle WHERE incident_id = ? AND call_sign = ?", (incident_id, row["call_sign"]))
        add_vehicle(con, incident_id, **row)
    seen = set()
    for member_id, role, vehicle in attendance:
        if member_id not in seen:   # doppelte Zeile im Bericht: die erste zählt
            seen.add(member_id)
            con.execute("DELETE FROM attendance WHERE incident_id = ? AND member_id = ?", (incident_id, member_id))
            add_attendance(con, incident_id, member_id, role, vehicle)


TIME = re.compile(r"([01]\d|2[0-3]):([0-5]\d)(?::([0-5]\d))?")


def _time(value):
    """Uhrzeit aus dem Formular ("HH:MM" oder "HH:MM:SS") -> "HH:MM:SS"; leer -> None."""
    value = (value or "").strip()
    if not value:
        return None
    m = TIME.fullmatch(value)
    if not m:
        raise ValueError(f"Uhrzeit „{value}“ ist ungültig (Format HH:MM).")
    return f"{m.group(1)}:{m.group(2)}:{m.group(3) or '00'}"


def replace_vehicles(con, incident_id, rows):
    """Fahrzeuge aus dem Formular: [{call_sign, crew, departed, arrived}]. Nicht genannte Fahrzeuge entfallen;
    vorhandene behalten Name, Alarmierung und Ende, neue gelten als manuell ergänzt."""
    current = {r["call_sign"]: dict(r) for r in con.execute("SELECT * FROM vehicle WHERE incident_id = ?", (incident_id,))}
    wanted, rows_by_sign = {}, {row["call_sign"]: row for row in rows}
    for row in rows:
        crew = to_int(row.get("crew"))
        if crew is not None and not 0 <= crew <= 99:
            raise ValueError(f"Stärke {crew} bei {row['call_sign']} ist ungültig.")
        wanted[row["call_sign"]] = {"crew": crew, "departed": _time(row.get("departed")),
                                    "arrived": _time(row.get("arrived"))}
    for call_sign in set(current) - set(wanted):
        con.execute("DELETE FROM vehicle WHERE incident_id = ? AND call_sign = ?", (incident_id, call_sign))
    for call_sign, values in wanted.items():
        if call_sign in current:
            for key in ("departed", "arrived"):    # nur Minuten im Formular: Sekunden aus dem Bericht behalten
                stored, given = current[call_sign][key], (rows_by_sign[call_sign].get(key) or "").strip()
                if stored and len(given) == 5 and stored[:5] == given:
                    values[key] = stored
            con.execute("UPDATE vehicle SET crew = ?, departed = ?, arrived = ? WHERE incident_id = ? AND call_sign = ?",
                        (values["crew"], values["departed"], values["arrived"], incident_id, call_sign))
        else:
            add_vehicle(con, incident_id, call_sign, None, values["crew"], values["departed"], values["arrived"],
                        manual=True)


def replace_attendance(con, incident_id, people):
    """Anwesenheit aus dem Formular: [{id oder name, role, vehicle}]. Nicht genannte Personen entfallen;
    neue gelten als manuell ergänzt, unbekannte Namen („Nachname, Vorname“) werden als Kameraden angelegt."""
    current = {r["member_id"] for r in con.execute("SELECT member_id FROM attendance WHERE incident_id = ?",
                                                   (incident_id,))}
    members, wanted = MemberDirectory(con), {}
    for p in people:
        member_id = p.get("id")
        if member_id is None:
            name = " ".join((p.get("name") or "").split())
            if not name:
                continue
            last_name, first_name = split_name(name)
            member_id = members.find_or_create(last_name, first_name)
        elif not con.execute("SELECT 1 FROM member WHERE id = ?", (member_id,)).fetchone():
            raise ValueError("Unbekannter Kamerad.")
        wanted.setdefault(member_id, ((p.get("role") or "").strip() or None, (p.get("vehicle") or "").strip() or None))
    for member_id in current - set(wanted):
        con.execute("DELETE FROM attendance WHERE incident_id = ? AND member_id = ?", (incident_id, member_id))
    for member_id, (role, vehicle) in wanted.items():
        if member_id in current:
            con.execute("UPDATE attendance SET role = ?, vehicle = ? WHERE incident_id = ? AND member_id = ?",
                        (role, vehicle, incident_id, member_id))
        else:
            add_attendance(con, incident_id, member_id, role, vehicle, manual=True)


def all_members(con):
    """Alle Kameraden der Wehr (Vorschläge beim Ergänzen der Anwesenheit)."""
    return [dict(r) for r in con.execute("SELECT id, name FROM member ORDER BY name")]


def update_incident(con, incident_id, changes, modified_by=None, source=None):
    """Felder ändern; Jahr und Wochenende/Feiertag werden neu abgeleitet.
    source: {source, filename, warnings} beim Aktualisieren aus einem Bericht."""
    current = con.execute("SELECT * FROM incident WHERE id = ?", (incident_id,)).fetchone()
    if not current:
        raise KeyError(incident_id)
    f = normalize_fields({**dict(current), **changes})
    _check_unique(con, f, incident_id)
    if source:
        f.update(source=source["source"], filename=source["filename"],
                 warnings=json.dumps(list(source["warnings"]), ensure_ascii=False))
    assignments = ", ".join(f"{name} = ?" for name in f)
    con.execute(f"UPDATE incident SET {assignments}, modified = datetime('now', 'localtime'), modified_by = ? "
                "WHERE id = ?", [*f.values(), modified_by, incident_id])


def add_fleet_vehicles(con, vehicles, day):
    """Beim Import entdeckte eigene Fahrzeuge [(call_sign, Funkrufname)] hinten an die Fahrzeugliste anfügen."""
    order = con.execute("SELECT COALESCE(MAX(sort_order), 0) FROM fleet").fetchone()[0]
    for i, (call_sign, name) in enumerate(vehicles, start=1):
        label = domain.describe_call_sign(name).get("label", "")    # Fahrzeugtyp, wenn die Kennzahl eindeutig ist
        con.execute("INSERT OR IGNORE INTO fleet (call_sign, name, label, sort_order, in_service_from) "
                    "VALUES (?, ?, ?, ?, ?)", (call_sign, name or "", label, order + i, day.isoformat() if day else None))


def vehicles_with_data(con):
    """{Funkrufname: Anzahl Einsätze} – für den Hinweis beim Entfernen aus der Fahrzeugliste."""
    return {r[0]: r[1] for r in con.execute("SELECT call_sign, COUNT(*) FROM vehicle GROUP BY call_sign")}


def delete_incident(con, incident_id):
    con.execute("DELETE FROM incident WHERE id = ?", (incident_id,))


# ---------------------------------------------------------------- Weitergegebene Berichte
def add_pending(con, report, filename, pdf, email=None):
    """Bericht, den jemand aus einer anderen Wehr eingelesen hat, zur Übernahme ablegen (neuer Stand ersetzt alten)."""
    if report.get("bks_report_id"):
        con.execute("DELETE FROM pending_report WHERE bks_report_id = ?", (report["bks_report_id"],))
    keyword = f"{report.get('keyword') or ''}.{report.get('subcode') or ''}".strip(".")
    return _insert(con, "pending_report", {
        "bks_report_id": report.get("bks_report_id"), "bks_record_id": report.get("bks_record_id"),
        "number_text": report.get("number_text"), "first_alarm": to_iso(report.get("first_alarm")),
        "keyword": keyword, "reported_as": report.get("reported_as"), "filename": filename, "pdf": pdf,
        "uploaded_by": email})


def pending_reports(con):
    return [dict(r) for r in con.execute("SELECT id, bks_report_id, bks_record_id, number_text, first_alarm, keyword, "
                                         "reported_as, filename, uploaded_by, uploaded FROM pending_report ORDER BY uploaded")]


def pending_pdf(con, pending_id):
    row = con.execute("SELECT filename, pdf FROM pending_report WHERE id = ?", (pending_id,)).fetchone()
    return (row["filename"], row["pdf"]) if row else (None, None)


def delete_pending(con, pending_id, bks_report_id=None):
    """Abgelegten Bericht entfernen – nach Übernahme auch denselben Bericht aus einem anderen Upload."""
    con.execute("DELETE FROM pending_report WHERE id = ? OR bks_report_id = ?", (pending_id, bks_report_id))
