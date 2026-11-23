# -*- coding: utf-8 -*-
"""Übungsdienste ohne BKS-Bericht (Datum, Thema, Zeitraum, Teilnehmer aus dem Personenstamm).

Eigene Tabellen (training, training_attendance), nie in incident: Übungen fließen deshalb in keine Auswertung, keinen
Excel-Export der Einsätze und keine VG-Gesamtansicht ein. Gemeinsam ist nur der Personenstamm (member).
"""
import datetime as dt
import json
import secrets
import threading

from app import names, store
from app.timeutil import normalize_iso, parse_iso

MAX_DAYS = 14                       # längste Übung (z. B. Lehrgang); darüber ist es vermutlich ein Tippfehler
OPTIONAL = ("trainer", "place", "category", "notes")
PIN_LENGTH = 6
MAX_QUEUE = 200                     # offene Anmeldungen je Übung (Schutz vor Fluten über den öffentlichen Link)
MAX_PIN_FAILS = 30                  # falsche PINs je Wehr und Tag, danach ist die Anmeldung für den Tag gesperrt
LIMITS = {"topic": 200, "trainer": 120, "place": 120, "category": 80, "notes": 2000}


class Stale(ValueError):
    """Die Übung wurde seit dem Öffnen geändert."""


class Locked(ValueError):
    """Zu viele falsche PINs: Die Anmeldung per QR-Code ist für heute gesperrt."""


def _clean(fields):
    """Geprüfte Felder: Thema, Beginn/Ende (ISO) und die optionalen Texte (leer = None)."""
    topic = (fields.get("topic") or "").strip()
    if not topic:
        raise ValueError("Bitte ein Thema angeben.")
    try:
        started, ended = parse_iso(fields.get("started_at")), parse_iso(fields.get("ended_at"))
    except ValueError:
        started = ended = None
    if not started or not ended:
        raise ValueError("Bitte Beginn und Ende mit Datum und Uhrzeit angeben.")
    if ended <= started:
        raise ValueError("Das Ende muss nach dem Beginn liegen.")
    if ended - started > dt.timedelta(days=MAX_DAYS):
        raise ValueError(f"Eine Übung dauert höchstens {MAX_DAYS} Tage.")
    clean = {"topic": topic, "started_at": normalize_iso(fields["started_at"]),
             "ended_at": normalize_iso(fields["ended_at"]), "year": started.year}
    for name in OPTIONAL:
        clean[name] = (fields.get(name) or "").strip() or None
    for name, limit in LIMITS.items():
        if len(clean[name] or "") > limit:
            raise ValueError(f"Zu lang: {name} (höchstens {limit} Zeichen).")
    return clean


def _participants(con, member_ids, new_members):
    """Mitglieder-IDs der Teilnehmer: vorhandene prüfen, neue Personen im Personenstamm anlegen (Dubletten werden
    über den Namensabgleich erkannt und wiederverwendet; ausgeschiedene Personen werden wieder aktiv)."""
    ids = list(dict.fromkeys(member_ids or []))
    known = {r["id"] for r in con.execute("SELECT id FROM member")}
    if set(ids) - known:
        raise ValueError("Unbekannte Person in der Teilnehmerliste.")
    directory = store.MemberDirectory(con)
    for person in new_members or []:
        last, first = (person.get("last_name") or "").strip(), (person.get("first_name") or "").strip()
        if not last:
            raise ValueError("Neue Personen brauchen einen Nachnamen.")
        member_id = directory.find_or_create(last, first)
        con.execute("UPDATE member SET active = 1 WHERE id = ?", (member_id,))
        if member_id not in ids:
            ids.append(member_id)
    return ids


def _set_participants(con, training_id, ids):
    con.execute("DELETE FROM training_attendance WHERE training_id = ?", (training_id,))
    con.executemany("INSERT INTO training_attendance (training_id, member_id) VALUES (?, ?)",
                    [(training_id, i) for i in ids])


def _free_pin(con, started_at):
    """Zufällige PIN, die am selben Starttag noch keine andere Übung hat (die PIN allein wählt die Übung)."""
    taken = {r[0] for r in con.execute("SELECT checkin_pin FROM training WHERE substr(started_at, 1, 10) = ?",
                                       (started_at[:10],))}
    while True:
        pin = f"{secrets.randbelow(10 ** PIN_LENGTH):0{PIN_LENGTH}d}"
        if pin not in taken:
            return pin


def create(con, fields, member_ids=(), new_members=()):
    clean = _clean(fields)
    ids = _participants(con, member_ids, new_members)
    clean["checkin_pin"] = _free_pin(con, clean["started_at"])
    training_id = con.execute(
        "INSERT INTO training (year, started_at, ended_at, topic, trainer, place, category, notes, checkin_pin) "
        "VALUES (:year, :started_at, :ended_at, :topic, :trainer, :place, :category, :notes, :checkin_pin)",
        clean).lastrowid
    _set_participants(con, training_id, ids)
    return training_id


_checkin_lock = threading.Lock()      # nur ein Worker: Zähler der falschen PINs und Obergrenze der Warteschlange


def _fails(con, day):
    row = con.execute("SELECT value FROM setting WHERE key = 'checkin_fails'").fetchone()
    data = json.loads(row[0]) if row else {}
    return data.get("n", 0) if data.get("day") == day else 0


def check_in(con, pin, last_name, first_name, now):
    """Anmeldung einer Person zur Übung des Tages (QR-Code, ohne Benutzerkonto) – nur mit der PIN dieser Übung.

    Die Anmeldung landet in der Warteschlange `training_checkin` (Quarantäne): weder Personenstamm noch Teilnahme
    werden angefasst, bis die Übungsleitung sie bestätigt. Eine Übung entsteht nie hierdurch. Die PIN gilt nur an den
    Tagen der Übung; falsche PINs werden je Wehr und Tag gezählt (dauerhaft, `setting`). Rückgabe: Übungs-ID, bei
    falscher PIN None (der Fehlversuch wird gespeichert, deshalb keine Ausnahme); `Locked` bei Sperre."""
    last, first = " ".join((last_name or "").split()), " ".join((first_name or "").split())
    pin = "".join(c for c in (pin or "") if c.isdigit())
    day = now.date().isoformat()
    with _checkin_lock:
        fails = _fails(con, day)
        if fails >= MAX_PIN_FAILS:
            raise Locked("Zu viele falsche PINs. Die Anmeldung ist für heute gesperrt – bitte die Übungsleitung "
                         "ansprechen.")
        row = con.execute("SELECT id FROM training WHERE checkin_pin = ? AND substr(started_at, 1, 10) <= ? "
                          "AND substr(ended_at, 1, 10) >= ? ORDER BY started_at, id LIMIT 1",
                          (pin, day, day)).fetchone() if len(pin) == PIN_LENGTH else None
        if not row:
            con.execute("INSERT INTO setting (key, value) VALUES ('checkin_fails', ?) ON CONFLICT(key) DO UPDATE "
                        "SET value = excluded.value", (json.dumps({"day": day, "n": fails + 1}),))
            return None
        if not last:
            raise ValueError("Bitte den Nachnamen angeben.")
        if len(last) > 60 or len(first) > 60:
            raise ValueError("Der Name ist zu lang.")
        if con.execute("SELECT COUNT(*) FROM training_checkin WHERE training_id = ?", (row["id"],)).fetchone()[0] \
                >= MAX_QUEUE:
            raise ValueError("Für diese Übung liegen schon sehr viele Anmeldungen vor. Bitte die Übungsleitung ansprechen.")
        con.execute("INSERT OR IGNORE INTO training_checkin (training_id, last_name, first_name) VALUES (?, ?, ?)",
                    (row["id"], last, first))
    return row["id"]


def new_pin(con, training_id):
    """Neue PIN für die Übung (die bisherige gilt nicht mehr, auch für ältere Übungen ohne PIN)."""
    row = con.execute("SELECT started_at FROM training WHERE id = ?", (training_id,)).fetchone()
    if not row:
        raise KeyError(training_id)
    pin = _free_pin(con, row["started_at"])
    con.execute("UPDATE training SET checkin_pin = ? WHERE id = ?", (pin, training_id))
    return pin


def accept_checkins(con, training_id, checkin_id=None):
    """Wartende Anmeldungen bestätigen (eine oder alle): Person im Personenstamm finden oder anlegen, Teilnahme
    eintragen. Erhöht die Revision, damit eine geöffnete Bearbeitung nichts überschreibt. Rückgabe: Anzahl."""
    if not con.execute("SELECT 1 FROM training WHERE id = ?", (training_id,)).fetchone():
        raise KeyError(training_id)
    sql, params = "SELECT * FROM training_checkin WHERE training_id = ?", [training_id]
    if checkin_id is not None:
        sql, params = sql + " AND id = ?", params + [checkin_id]
    rows = con.execute(sql, params).fetchall()
    if checkin_id is not None and not rows:
        raise KeyError(checkin_id)
    directory = store.MemberDirectory(con)
    for r in rows:
        member_id = directory.find_or_create(r["last_name"], r["first_name"])
        con.execute("UPDATE member SET active = 1 WHERE id = ?", (member_id,))
        con.execute("INSERT OR IGNORE INTO training_attendance (training_id, member_id) VALUES (?, ?)",
                    (training_id, member_id))
        con.execute("DELETE FROM training_checkin WHERE id = ?", (r["id"],))
    if rows:
        con.execute("UPDATE training SET revision = revision + 1, modified = datetime('now', 'localtime') "
                    "WHERE id = ?", (training_id,))
    return len(rows)


def reject_checkin(con, training_id, checkin_id):
    if not con.execute("DELETE FROM training_checkin WHERE id = ? AND training_id = ?",
                       (checkin_id, training_id)).rowcount:
        raise KeyError(checkin_id)


def update(con, training_id, fields, revision, member_ids=(), new_members=()):
    clean = _clean(fields)
    ids = _participants(con, member_ids, new_members)
    cursor = con.execute(
        "UPDATE training SET year = :year, started_at = :started_at, ended_at = :ended_at, topic = :topic, "
        "trainer = :trainer, place = :place, category = :category, notes = :notes, revision = revision + 1, "
        "modified = datetime('now', 'localtime') WHERE id = :id AND revision = :revision",
        {**clean, "id": training_id, "revision": revision})
    if not cursor.rowcount:
        if not con.execute("SELECT 1 FROM training WHERE id = ?", (training_id,)).fetchone():
            raise KeyError(training_id)
        raise Stale("Die Übung wurde inzwischen geändert. Bitte neu laden und erneut prüfen.")
    _set_participants(con, training_id, ids)


def delete(con, training_id, revision):
    cursor = con.execute("DELETE FROM training WHERE id = ? AND revision = ?", (training_id, revision))
    if not cursor.rowcount:
        if not con.execute("SELECT 1 FROM training WHERE id = ?", (training_id,)).fetchone():
            raise KeyError(training_id)
        raise Stale("Die Übung wurde inzwischen geändert. Bitte neu laden und erneut prüfen.")


def duration_min(row):
    return round((parse_iso(row["ended_at"]) - parse_iso(row["started_at"])).total_seconds() / 60)


def load(con, year=None, training_id=None, with_checkin=False):
    """Übungen (neueste zuerst) mit Teilnehmern [{id, name}] und Dauer in Minuten. Nur mit `with_checkin` (Recht zum
    Ändern) auch die PIN und die wartenden Anmeldungen [{id, name, match}] (match = Name der erkannten Person)."""
    sql, params = "SELECT * FROM training", []
    if training_id is not None:
        sql, params = sql + " WHERE id = ?", [training_id]
    elif year is not None:
        sql, params = sql + " WHERE year = ?", [year]
    rows = [dict(r) for r in con.execute(sql + " ORDER BY started_at DESC, id DESC", params)]
    people = {}
    for r in con.execute("SELECT a.training_id, m.id, m.name FROM training_attendance a "
                         "JOIN member m ON m.id = a.member_id"):
        people.setdefault(r["training_id"], []).append({"id": r["id"], "name": r["name"]})
    waiting = {}
    if with_checkin:
        queue = con.execute("SELECT id, training_id, last_name, first_name FROM training_checkin ORDER BY id").fetchall()
        directory = store.MemberDirectory(con) if queue else None
        for r in queue:
            found = directory.find(r["last_name"], r["first_name"])
            waiting.setdefault(r["training_id"], []).append({
                "id": r["id"], "name": f"{r['last_name']}, {r['first_name']}".strip(", "),
                "match": directory.names[found] if found is not None else None})
    for row in rows:
        row["duration_min"] = duration_min(row)
        row["participants"] = sorted(people.get(row["id"], []), key=lambda p: names.sort_key(p["name"]))
        if with_checkin:
            row["checkins"] = waiting.get(row["id"], [])
        else:
            row.pop("checkin_pin", None)
    return rows


def years(con):
    return sorted({r[0] for r in con.execute("SELECT DISTINCT year FROM training")} | {dt.date.today().year},
                  reverse=True)


def summary(trainings):
    """Teilnahmen je Person im Jahr: Anzahl, Stunden, Beteiligung (Anteil der Übungen) und letzte Teilnahme."""
    people = {}
    for t in trainings:
        for p in t["participants"]:
            row = people.setdefault(p["id"], {"id": p["id"], "name": p["name"], "trainings": 0, "minutes": 0,
                                              "last": None})
            row["trainings"] += 1
            row["minutes"] += t["duration_min"]
            row["last"] = max(row["last"] or "", t["started_at"])
    total = len(trainings)
    return {"count": total, "minutes": sum(t["duration_min"] for t in trainings),
            "members": sorted(({**r, "hours": round(r["minutes"] / 60, 1),
                                "rate": r["trainings"] / total if total else 0} for r in people.values()),
                              key=lambda r: (-r["trainings"], r["name"]))}


def directory(con):
    """Personenstamm für die Teilnehmerwahl (auch Ausgeschiedene, mit Kennzeichen)."""
    rows = [{"id": r["id"], "name": r["name"], "active": bool(r["active"])}
            for r in con.execute("SELECT id, name, active FROM member")]
    return sorted(rows, key=lambda r: names.sort_key(r["name"]))

