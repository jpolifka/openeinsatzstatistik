# -*- coding: utf-8 -*-
"""Signatur von Einsätzen und Übungen durch die Wehrführung (oder Stellvertretung) und das Prüfprotokoll dazu.

Die Signatur gilt nur für die Revision, die beim Signieren geprüft wurde: Jede spätere Änderung (Bearbeiten, neu
Einlesen, Nummerierung, bestätigte QR-Anmeldungen) erhöht die Revision und macht sie ungültig – sie bleibt als
„veraltet“ sichtbar. Jede Handlung steht in `audit_event` (nur anhängbar, ohne Namen von Personen)."""

KINDS = ("incident", "training")
TABLES = {"incident": "incident", "training": "training"}


class Stale(ValueError):
    """Der Datensatz wurde seit dem Öffnen geändert."""


def audit(con, email, action, kind=None, ref_id=None, detail=None):
    con.execute("INSERT INTO audit_event (email, action, kind, ref_id, detail) VALUES (?, ?, ?, ?, ?)",
                (email or "lokal", action, kind, ref_id, detail))


def attach(con, kind, items):
    """Hängt jedem Datensatz `signature` an: None (nicht signiert) oder {at, valid} (valid = die Signatur gilt für
    den aktuellen Stand). Die Unterzeichnenden stehen nur im Protokoll."""
    given = {r["ref_id"]: r for r in con.execute("SELECT ref_id, revision, at FROM signoff WHERE kind = ?", (kind,))}
    for item in items:
        row = given.get(item["id"])
        item["signature"] = {"at": row["at"], "valid": row["revision"] == item["revision"]} if row else None
    return items


def sign(con, kind, ref_id, revision, email):
    """Datensatz in der geprüften Revision signieren (eine bestehende Signatur wird ersetzt)."""
    current = con.execute(f"SELECT revision FROM {TABLES[kind]} WHERE id = ?", (ref_id,)).fetchone()
    if not current:
        raise KeyError(ref_id)
    if current["revision"] != revision:
        raise Stale("Der Datensatz wurde inzwischen geändert. Bitte neu laden, prüfen und erneut signieren.")
    con.execute("INSERT INTO signoff (kind, ref_id, revision, email) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(kind, ref_id) DO UPDATE SET revision = excluded.revision, email = excluded.email, "
                "at = datetime('now', 'localtime')", (kind, ref_id, revision, email or "lokal"))
    audit(con, email, "sign", kind, ref_id, f"Revision {revision}")


def unsign(con, kind, ref_id, email):
    if not con.execute("DELETE FROM signoff WHERE kind = ? AND ref_id = ?", (kind, ref_id)).rowcount:
        raise KeyError(ref_id)
    audit(con, email, "unsign", kind, ref_id)


def events(con, limit=200):
    """Neueste Einträge des Protokolls (Unterzeichnende, Handlung, Datensatz)."""
    return [dict(r) for r in con.execute(
        "SELECT id, email, action, kind, ref_id, detail, at FROM audit_event ORDER BY id DESC LIMIT ?", (limit,))]
