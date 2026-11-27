# -*- coding: utf-8 -*-
"""Persönliche Atemschutz-Dokumentation: Einsatz, Übung, Streckendurchgang und G26.3 – je Person, nur für sie selbst.

Harte Leitplanken (siehe Tests in tests/test_atemschutz.py):
- Alles, was eine Person sieht oder ändert, läuft über `Own(con, member_id)`; jede SQL-Anweisung dort enthält
  `member_id = ?` – auch bei Änderung und Löschen (eine Eintrags-ID allein reicht nie).
- Die Person wird nie vom Aufrufer genannt, sondern aus der angemeldeten E-Mail bestimmt (`member_for`).
- Die einzige personenübergreifende Abfrage ist `summary` (nur Summen, für die Wehrführung); sie steht in
  SUMMARY_FUNCTIONS, und der Test über den Quelltext lässt nur dort SQL ohne `member_id` zu.
- Die Tabellen agt_* fließen nie in `metrics`, Einsatzauswertungen, Export oder VG-Gesamtansicht ein.
"""
import datetime as dt
import json
import re

from app.timeutil import normalize_iso, parse_iso

KINDS = {"einsatz": "Einsatz", "uebung": "Übung", "strecke": "Streckendurchgang"}
SOURCE_KINDS = {"incident": "einsatz", "training": "uebung"}
REMINDER_DAYS = (60, 30, 14)         # zwei Monate, ein Monat, zwei Wochen vor Ablauf der G26.3
MAX_BAR = 400
MAX_ENTRIES = 5000                   # je Person (Schutz vor Fluten)
MAX_MEDICAL = 100
LIMITS = {"place": 120, "keyword": 120, "organisation": 120, "notes": 1000}
# Funktionen, die über mehrere Personen lesen dürfen (Allowlist für den Quelltexttest)
SUMMARY_FUNCTIONS = ("summary", "summary_years", "reminder_candidates")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class Stale(ValueError):
    """Der Eintrag wurde seit dem Öffnen geändert."""


class NotFound(LookupError):
    """Kein solcher Eintrag bei dieser Person (auch für Einträge anderer Personen – kein Existenz-Orakel)."""


def member_for(con, email):
    """ID der Person, deren E-Mail im Personenstamm die angemeldete ist (aktiv); sonst None. Die einzige Stelle, an der
    aus einer Anmeldung eine Person wird."""
    email = (email or "").strip().lower()
    if not email:
        return None
    row = con.execute("SELECT id FROM member WHERE lower(email) = ? AND active = 1", (email,)).fetchone()
    return row["id"] if row else None


def audit(con, email, action, member_id=None):
    """Zugriffsprotokoll (nur anhängbar, ohne Werte)."""
    con.execute("INSERT INTO agt_audit (email, action, member_id) VALUES (?, ?, ?)", (email or "lokal", action, member_id))


def _text(fields, name):
    value = (fields.get(name) or "").strip() or None
    if value and len(value) > LIMITS[name]:
        raise ValueError(f"Zu lang: {name} (höchstens {LIMITS[name]} Zeichen).")
    return value


def _bar(value, label):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= MAX_BAR:
        raise ValueError(f"{label}: ganze Zahl von 0 bis {MAX_BAR} bar.")
    return value


def clean_entry(fields):
    """Geprüfte Felder eines Eintrags; Ende = Beginn + Dauer."""
    kind = fields.get("kind")
    if kind not in KINDS:
        raise ValueError("Art: Einsatz, Übung oder Streckendurchgang.")
    try:
        started = parse_iso(fields.get("started_at"))
    except ValueError:
        started = None
    if not started:
        raise ValueError("Bitte den Beginn mit Datum und Uhrzeit angeben.")
    minutes = fields.get("duration_min")
    if isinstance(minutes, bool) or not isinstance(minutes, int) or not 1 <= minutes <= 1440:
        raise ValueError("Dauer: 1 bis 1440 Minuten.")
    start_bar, end_bar = _bar(fields.get("start_bar"), "Startdruck"), _bar(fields.get("end_bar"), "Enddruck")
    if (start_bar is None) != (end_bar is None):
        raise ValueError("Start- und Enddruck bitte beide angeben oder beide leer lassen.")
    if end_bar is not None and end_bar > start_bar:
        raise ValueError("Der Enddruck kann nicht höher sein als der Startdruck.")
    external = bool(fields.get("external"))
    organisation = _text(fields, "organisation")
    if external and not organisation:
        raise ValueError("Bei einem Fremdeintrag bitte die Organisation angeben (z. B. Werkfeuerwehr).")
    return {"kind": kind, "started_at": normalize_iso(fields["started_at"]),
            "ended_at": (started + dt.timedelta(minutes=minutes)).isoformat(timespec="seconds"),
            "duration_min": minutes, "place": _text(fields, "place"), "keyword": _text(fields, "keyword"),
            "start_bar": start_bar, "end_bar": end_bar, "external": int(external),
            "organisation": organisation if external else None, "notes": _text(fields, "notes")}


def _day(value, label):
    if not isinstance(value, str) or not DATE.match(value):
        raise ValueError(f"{label}: Datum im Format JJJJ-MM-TT.")
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{label}: kein gültiges Datum.")


def entry_json(row):
    r = dict(row)
    r.pop("member_id", None)
    r["used_bar"] = r["start_bar"] - r["end_bar"] if r["start_bar"] is not None and r["end_bar"] is not None else None
    r["external"] = bool(r["external"])
    return r


class Own:
    """Zugriff auf die Atemschutz-Daten genau einer Person. Alle Methoden binden `member_id` in jede Abfrage."""

    def __init__(self, con, member_id, email=None):
        if not isinstance(member_id, int) or isinstance(member_id, bool):
            raise TypeError("member_id fehlt")
        self.con, self.member_id, self.email = con, member_id, email

    def _log(self, action):
        audit(self.con, self.email, action, self.member_id)

    # ------------------------------------------------------------ Einträge
    def years(self):
        rows = self.con.execute("SELECT DISTINCT substr(started_at, 1, 4) AS y FROM agt_entry WHERE member_id = ? "
                                "ORDER BY y DESC", (self.member_id,))
        years = [int(r["y"]) for r in rows]
        today = dt.date.today().year
        return years if today in years else [today] + years

    def entries(self, year):
        rows = self.con.execute("SELECT * FROM agt_entry WHERE member_id = ? AND substr(started_at, 1, 4) = ? "
                                "ORDER BY started_at DESC, id DESC", (self.member_id, f"{year:04d}"))
        return [entry_json(r) for r in rows]

    def totals(self, year):
        """Minuten und Anzahl je Art im Jahr (nur diese Person)."""
        result = {k: {"count": 0, "minutes": 0} for k in KINDS}
        for r in self.con.execute("SELECT kind, COUNT(*) AS n, SUM(duration_min) AS m FROM agt_entry "
                                  "WHERE member_id = ? AND substr(started_at, 1, 4) = ? GROUP BY kind",
                                  (self.member_id, f"{year:04d}")):
            result[r["kind"]] = {"count": r["n"], "minutes": r["m"] or 0}
        return result

    def entry(self, entry_id):
        row = self.con.execute("SELECT * FROM agt_entry WHERE id = ? AND member_id = ?",
                               (entry_id, self.member_id)).fetchone()
        if not row:
            raise NotFound
        return entry_json(row)

    def _guard_count(self, table, limit):
        # table kommt nur aus dem Code (zwei feste Namen)
        if self.con.execute(f"SELECT COUNT(*) FROM {table} WHERE member_id = ?", (self.member_id,)).fetchone()[0] >= limit:
            raise ValueError("Es sind zu viele Einträge vorhanden.")

    def create(self, fields, source=None):
        """Neuer Eintrag. source = (Art, ID) übernimmt Stichwort/Beginn/Ort aus einem Einsatz bzw. einer Übung, an dem die
        Person laut Anwesenheit teilgenommen hat; Dauer und Druck kommen vom Benutzer (sonst Dauer der Quelle)."""
        self._guard_count("agt_entry", MAX_ENTRIES)
        source_kind = source_id = None
        if source:
            source_kind, source_id = source
            origin = self.source_fields(source_kind, source_id)
            fields = {**origin, **{k: v for k, v in fields.items() if k in ("duration_min", "start_bar", "end_bar", "notes")
                                   and v is not None},
                      "kind": SOURCE_KINDS[source_kind], "external": False,
                      "duration_min": fields.get("duration_min") or origin.get("duration_min")}
        clean = clean_entry(fields)
        try:
            entry_id = self.con.execute(
                "INSERT INTO agt_entry (member_id, kind, started_at, ended_at, duration_min, place, keyword, start_bar, "
                "end_bar, external, organisation, notes, source_kind, source_id) VALUES (:member_id, :kind, :started_at, "
                ":ended_at, :duration_min, :place, :keyword, :start_bar, :end_bar, :external, :organisation, :notes, "
                ":source_kind, :source_id)",
                {**clean, "member_id": self.member_id, "source_kind": source_kind, "source_id": source_id}).lastrowid
        except Exception as e:
            if "UNIQUE" in str(e):
                raise ValueError("Diese Teilnahme ist schon übernommen.")
            raise
        self._log("agt.entry.create")
        return self.entry(entry_id)

    def update(self, entry_id, revision, fields):
        current = self.entry(entry_id)
        if current["revision"] != revision:
            raise Stale("Der Eintrag wurde zwischenzeitlich geändert. Bitte neu laden.")
        if current["source_kind"]:
            # Herkunft bleibt: Art und Beginn stammen aus der Statistik, angepasst werden Dauer, Druck und Notizen
            fields = {**current, **{k: v for k, v in fields.items() if k in ("duration_min", "start_bar", "end_bar", "notes",
                                                                           "place")}}
        clean = clean_entry(fields)
        cursor = self.con.execute(
            "UPDATE agt_entry SET kind = :kind, started_at = :started_at, ended_at = :ended_at, duration_min = :duration_min, "
            "place = :place, keyword = :keyword, start_bar = :start_bar, end_bar = :end_bar, external = :external, "
            "organisation = :organisation, notes = :notes, revision = revision + 1, modified = datetime('now', 'localtime') "
            "WHERE id = :id AND member_id = :member_id AND revision = :revision",
            {**clean, "id": entry_id, "member_id": self.member_id, "revision": revision})
        if cursor.rowcount != 1:
            raise Stale("Der Eintrag wurde zwischenzeitlich geändert. Bitte neu laden.")
        self._log("agt.entry.update")
        return self.entry(entry_id)

    def delete(self, entry_id, revision):
        cursor = self.con.execute("DELETE FROM agt_entry WHERE id = ? AND member_id = ? AND revision = ?",
                                  (entry_id, self.member_id, revision))
        if cursor.rowcount != 1:
            self.entry(entry_id)                  # fremd oder unbekannt → NotFound
            raise Stale("Der Eintrag wurde zwischenzeitlich geändert. Bitte neu laden.")
        self._log("agt.entry.delete")

    # ------------------------------------------------------------ Übernahme aus der Statistik
    def source_fields(self, kind, source_id):
        """Felder aus einem Einsatz bzw. einer Übung – nur wenn diese Person dort teilgenommen hat, sonst NotFound."""
        if kind == "incident":
            row = self.con.execute(
                "SELECT i.started_at, i.ended_at, i.keyword, i.place FROM incident i JOIN attendance a ON a.incident_id = i.id "
                "WHERE i.id = ? AND a.member_id = ?", (source_id, self.member_id)).fetchone()
        elif kind == "training":
            row = self.con.execute(
                "SELECT t.started_at, t.ended_at, t.topic AS keyword, t.place FROM training t "
                "JOIN training_attendance a ON a.training_id = t.id WHERE t.id = ? AND a.member_id = ?",
                (source_id, self.member_id)).fetchone()
        else:
            raise NotFound
        if not row:
            raise NotFound
        origin = dict(row)
        if origin["started_at"] and origin["ended_at"]:
            try:
                minutes = round((parse_iso(origin["ended_at"]) - parse_iso(origin["started_at"])).total_seconds() / 60)
                origin["duration_min"] = minutes if 1 <= minutes <= 1440 else None
            except (ValueError, TypeError):
                origin["duration_min"] = None
        else:
            origin["duration_min"] = None
        return origin

    def candidates(self, year):
        """Einsätze und Übungen des Jahres, an denen die Person teilgenommen hat (nur öffentliche Felder, keine Namen
        anderer), mit Kennzeichen, ob schon übernommen."""
        taken = {(r["source_kind"], r["source_id"]) for r in self.con.execute(
            "SELECT source_kind, source_id FROM agt_entry WHERE member_id = ? AND source_kind IS NOT NULL",
            (self.member_id,))}
        result = []
        for r in self.con.execute(
                "SELECT i.id, i.number, i.started_at, i.ended_at, i.keyword, i.place FROM incident i "
                "JOIN attendance a ON a.incident_id = i.id WHERE a.member_id = ? AND i.year = ? "
                "ORDER BY i.started_at DESC", (self.member_id, year)):
            result.append({**dict(r), "source": "incident", "taken": ("incident", r["id"]) in taken})
        for r in self.con.execute(
                "SELECT t.id, t.started_at, t.ended_at, t.topic AS keyword, t.place FROM training t "
                "JOIN training_attendance a ON a.training_id = t.id WHERE a.member_id = ? AND t.year = ? "
                "ORDER BY t.started_at DESC", (self.member_id, year)):
            result.append({**dict(r), "number": None, "source": "training", "taken": ("training", r["id"]) in taken})
        return sorted(result, key=lambda c: c["started_at"] or "", reverse=True)

    # ------------------------------------------------------------ G26.3
    def medical(self):
        return [{k: r[k] for k in ("id", "examined_on", "valid_until", "revision")} for r in self.con.execute(
            "SELECT id, examined_on, valid_until, revision FROM agt_medical WHERE member_id = ? "
            "ORDER BY valid_until DESC, id DESC", (self.member_id,))]

    def add_medical(self, examined_on, valid_until):
        self._guard_count("agt_medical", MAX_MEDICAL)
        examined, valid = _day(examined_on, "Untersuchung"), _day(valid_until, "Nächste Prüfung")
        if valid < examined:
            raise ValueError("Die nächste Prüfung liegt vor der Untersuchung.")
        if valid > examined + dt.timedelta(days=366 * 5):
            raise ValueError("Die nächste Prüfung liegt mehr als fünf Jahre nach der Untersuchung.")
        self.con.execute("INSERT INTO agt_medical (member_id, examined_on, valid_until) VALUES (?, ?, ?)",
                         (self.member_id, examined.isoformat(), valid.isoformat()))
        self._log("agt.medical.create")
        return self.medical()

    def delete_medical(self, medical_id):
        if self.con.execute("DELETE FROM agt_medical WHERE id = ? AND member_id = ?",
                            (medical_id, self.member_id)).rowcount != 1:
            raise NotFound
        self._log("agt.medical.delete")
        return self.medical()

    # ------------------------------------------------------------ Wehrwechsel
    def export_anonymous(self):
        """Alles dieser Person für den Wechsel in eine andere Wehr – anonymisiert: ohne Verweise auf Einsätze und Übungen der
        bisherigen Wehr (Quelle) und ohne Notizen (Freitext kann Dritte nennen)."""
        entries = [dict(r) for r in self.con.execute(
            "SELECT kind, started_at, ended_at, duration_min, place, keyword, start_bar, end_bar, external, organisation "
            "FROM agt_entry WHERE member_id = ? ORDER BY started_at", (self.member_id,))]
        medical = [dict(r) for r in self.con.execute(
            "SELECT examined_on, valid_until FROM agt_medical WHERE member_id = ? ORDER BY valid_until",
            (self.member_id,))]
        return {"entries": entries, "medical": medical, "reminder": self.reminder()}

    def absorb(self, data):
        """Daten aus export_anonymous übernehmen (schon vorhandene identische Zeilen werden nicht doppelt angelegt)."""
        for e in data["entries"]:
            if not self.con.execute(
                    "SELECT 1 FROM agt_entry WHERE member_id = ? AND kind = ? AND started_at = ? AND duration_min = ?",
                    (self.member_id, e["kind"], e["started_at"], e["duration_min"])).fetchone():
                self._guard_count("agt_entry", MAX_ENTRIES)
                self.con.execute(
                    "INSERT INTO agt_entry (member_id, kind, started_at, ended_at, duration_min, place, keyword, start_bar, "
                    "end_bar, external, organisation) VALUES (:member_id, :kind, :started_at, :ended_at, :duration_min, "
                    ":place, :keyword, :start_bar, :end_bar, :external, :organisation)", {**e, "member_id": self.member_id})
        for m in data["medical"]:
            if not self.con.execute("SELECT 1 FROM agt_medical WHERE member_id = ? AND examined_on = ? AND valid_until = ?",
                                    (self.member_id, m["examined_on"], m["valid_until"])).fetchone():
                self._guard_count("agt_medical", MAX_MEDICAL)
                self.con.execute("INSERT INTO agt_medical (member_id, examined_on, valid_until) VALUES (?, ?, ?)",
                                 (self.member_id, m["examined_on"], m["valid_until"]))
        if data["reminder"] and not self.reminder():
            self.set_reminder(data["reminder"])
        self._log("agt.transfer.in")

    def erase(self):
        """Alle Atemschutz-Daten dieser Person löschen (nach dem Wechsel in eine andere Wehr)."""
        self._log("agt.transfer.out")
        for table in ("agt_entry", "agt_medical", "agt_reminder_sent", "agt_reminder"):
            self.con.execute(f"DELETE FROM {table} WHERE member_id = ?", (self.member_id,))

    # ------------------------------------------------------------ Erinnerung
    def reminder(self):
        row = self.con.execute("SELECT offsets FROM agt_reminder WHERE member_id = ?", (self.member_id,)).fetchone()
        return sorted(json.loads(row["offsets"]), reverse=True) if row else []

    def set_reminder(self, offsets):
        offsets = sorted({int(o) for o in offsets})
        if set(offsets) - set(REMINDER_DAYS):
            raise ValueError("Erinnerung: 2 Monate, 1 Monat oder 2 Wochen vor Ablauf.")
        if offsets:
            self.con.execute("INSERT INTO agt_reminder (member_id, offsets) VALUES (?, ?) "
                             "ON CONFLICT(member_id) DO UPDATE SET offsets = excluded.offsets",
                             (self.member_id, json.dumps(offsets)))
        else:
            self.con.execute("DELETE FROM agt_reminder WHERE member_id = ?", (self.member_id,))
        self._log("agt.reminder.set")
        return self.reminder()


# ---------------------------------------------------------------- Auswertung der Wehrführung (nur Summen)
def summary(con, year):
    """Je aktiver Person Minuten und Anzahl im Jahr (nach Art) und G26.3 gültig bis. Keine Einzeleinträge, Drücke, Orte
    oder Notizen."""
    people = {r["id"]: {"id": r["id"], "name": r["name"], "linked": bool(r["email"]),
                        "kinds": {k: {"count": 0, "minutes": 0} for k in KINDS}, "minutes": 0, "valid_until": None}
              for r in con.execute("SELECT id, name, email FROM member WHERE active = 1 ORDER BY name")}
    for r in con.execute("SELECT member_id, kind, COUNT(*) AS n, SUM(duration_min) AS m FROM agt_entry "
                         "WHERE substr(started_at, 1, 4) = ? GROUP BY member_id, kind", (f"{year:04d}",)):
        person = people.get(r["member_id"])
        if person:
            person["kinds"][r["kind"]] = {"count": r["n"], "minutes": r["m"] or 0}
            person["minutes"] += r["m"] or 0
    for r in con.execute("SELECT member_id, MAX(valid_until) AS valid_until FROM agt_medical GROUP BY member_id"):
        if r["member_id"] in people:
            people[r["member_id"]]["valid_until"] = r["valid_until"]
    return list(people.values())


def summary_years(con):
    """Jahre mit Einträgen (nur Jahreszahlen) und das laufende Jahr, neueste zuerst."""
    years = {int(r["y"]) for r in con.execute("SELECT DISTINCT substr(started_at, 1, 4) AS y FROM agt_entry")}
    return sorted(years | {dt.date.today().year}, reverse=True)


def reminder_candidates(con):
    """Personen mit Erinnerungswunsch, aktiver E-Mail und letzter G26.3 -> [(member_id, email, valid_until, offsets)]."""
    rows = con.execute(
        "SELECT m.id, m.email, r.offsets, (SELECT MAX(valid_until) FROM agt_medical WHERE member_id = m.id) AS valid_until "
        "FROM agt_reminder r JOIN member m ON m.id = r.member_id WHERE m.active = 1 AND m.email IS NOT NULL")
    return [(r["id"], r["email"], r["valid_until"], json.loads(r["offsets"])) for r in rows if r["valid_until"]]
