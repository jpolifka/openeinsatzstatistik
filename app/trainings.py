# -*- coding: utf-8 -*-
"""Übungsdienste ohne BKS-Bericht (Datum, Thema, Zeitraum, Teilnehmer aus dem Personenstamm).

Eigene Tabellen (training, training_attendance), nie in incident: Übungen fließen deshalb in keine Auswertung, keinen
Excel-Export der Einsätze und keine VG-Gesamtansicht ein. Gemeinsam ist nur der Personenstamm (member).
"""
import datetime as dt

from app import names, store
from app.timeutil import normalize_iso, parse_iso

MAX_DAYS = 14                       # längste Übung (z. B. Lehrgang); darüber ist es vermutlich ein Tippfehler
OPTIONAL = ("trainer", "place", "category", "notes")
LIMITS = {"topic": 200, "trainer": 120, "place": 120, "category": 80, "notes": 2000}


class Stale(ValueError):
    """Die Übung wurde seit dem Öffnen geändert."""


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


def create(con, fields, member_ids=(), new_members=()):
    clean = _clean(fields)
    ids = _participants(con, member_ids, new_members)
    training_id = con.execute(
        "INSERT INTO training (year, started_at, ended_at, topic, trainer, place, category, notes) "
        "VALUES (:year, :started_at, :ended_at, :topic, :trainer, :place, :category, :notes)", clean).lastrowid
    _set_participants(con, training_id, ids)
    return training_id


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


def load(con, year=None, training_id=None):
    """Übungen (neueste zuerst) mit Teilnehmern [{id, name}] und Dauer in Minuten."""
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
    for row in rows:
        row["duration_min"] = duration_min(row)
        row["participants"] = sorted(people.get(row["id"], []), key=lambda p: names.sort_key(p["name"]))
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

