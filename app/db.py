# -*- coding: utf-8 -*-
"""SQLite-Datenbank der Einsätze (liegt im Docker-Volume /daten) mit schrittweisen Migrationen."""
import contextlib
import os
import sqlite3

PATH = os.environ.get("DB_PATH", "")

# Ursprüngliches Schema (deutsche Bezeichner). Bleibt unverändert, damit bestehende
# Datenbanken und neue denselben Migrationsweg gehen.
_LEGACY_SCHEMA = """
CREATE TABLE IF NOT EXISTS einsatz (
    id INTEGER PRIMARY KEY, jahr INTEGER NOT NULL, nr INTEGER, beginn TEXT, ende TEXT,
    stichwort TEXT, stufe TEXT, einsatz TEXT, ort TEXT, ehf TEXT,
    personen_gh INTEGER NOT NULL DEFAULT 0, wochenende INTEGER NOT NULL DEFAULT 0,
    quelle TEXT NOT NULL, datei TEXT, hinweise TEXT NOT NULL DEFAULT '[]',
    erstellt TEXT NOT NULL DEFAULT (datetime('now', 'localtime')), geaendert TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS einsatz_jahr_nr ON einsatz(jahr, nr) WHERE nr IS NOT NULL;
CREATE TABLE IF NOT EXISTS fahrzeug (
    einsatz_id INTEGER NOT NULL REFERENCES einsatz(id) ON DELETE CASCADE,
    block TEXT NOT NULL, name TEXT, staerke INTEGER, aus TEXT, ein TEXT,
    PRIMARY KEY (einsatz_id, block)
);
CREATE TABLE IF NOT EXISTS kamerad (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, nachname TEXT NOT NULL, vorname TEXT NOT NULL,
    reihenfolge INTEGER
);
CREATE TABLE IF NOT EXISTS anwesenheit (
    einsatz_id INTEGER NOT NULL REFERENCES einsatz(id) ON DELETE CASCADE,
    kamerad_id INTEGER NOT NULL REFERENCES kamerad(id),
    funktion TEXT, fahrzeug TEXT,
    PRIMARY KEY (einsatz_id, kamerad_id)
);
"""

# Englische Bezeichner. Ergebnis-Schema (Excel-Spalte der Einsatzübersicht in Klammern):
#   incident   year, number (A), started_at (B+E), ended_at, keyword (H, z. B. B2), subcode (I, z. B. 07),
#              description (J), place (K), unit_leader (L), station_staff (AL), weekend_or_holiday (AV),
#              source ('excel'/'pdf'), filename, warnings (JSON), created, modified
#   vehicle    incident_id, call_sign (02/45 …), name, crew, departed, arrived (HH:MM:SS)
#   member     id, name (wie im Kopf des Blatts Anwesenheit), last_name, first_name, sort_order
#   attendance incident_id, member_id, role, vehicle
_RENAMES = {
    "einsatz": ("incident", {"jahr": "year", "nr": "number", "beginn": "started_at", "ende": "ended_at",
                             "stichwort": "keyword", "stufe": "subcode", "einsatz": "description", "ort": "place",
                             "ehf": "unit_leader", "personen_gh": "station_staff",
                             "wochenende": "weekend_or_holiday", "quelle": "source", "datei": "filename",
                             "hinweise": "warnings", "erstellt": "created", "geaendert": "modified"}),
    "fahrzeug": ("vehicle", {"einsatz_id": "incident_id", "block": "call_sign", "staerke": "crew",
                             "aus": "departed", "ein": "arrived"}),
    "kamerad": ("member", {"nachname": "last_name", "vorname": "first_name", "reihenfolge": "sort_order"}),
    "anwesenheit": ("attendance", {"einsatz_id": "incident_id", "kamerad_id": "member_id",
                                   "funktion": "role", "fahrzeug": "vehicle"}),
}


def _create_legacy_schema(con):
    for statement in _LEGACY_SCHEMA.split(";"):
        if statement.strip():
            con.execute(statement)


def _rename_to_english(con):
    for old_table, (new_table, columns) in _RENAMES.items():
        for old, new in columns.items():
            con.execute(f"ALTER TABLE {old_table} RENAME COLUMN {old} TO {new}")
        con.execute(f"ALTER TABLE {old_table} RENAME TO {new_table}")
    con.execute("DROP INDEX IF EXISTS einsatz_jahr_nr")
    con.execute("CREATE UNIQUE INDEX incident_year_number ON incident(year, number) WHERE number IS NOT NULL")


# Neue Schemaänderungen nur hinten anfügen; PRAGMA user_version zählt die erledigten Schritte.
MIGRATIONS = [_create_legacy_schema, _rename_to_english]


def migrate(con):
    done = con.execute("PRAGMA user_version").fetchone()[0]
    for number, step in enumerate(MIGRATIONS[done:], start=done + 1):
        # sqlite3 öffnet vor DDL keine Transaktion von selbst – ohne BEGIN wäre ein Schritt nicht atomar
        con.execute("BEGIN")
        try:
            step(con)
            con.execute(f"PRAGMA user_version = {number}")
            con.commit()
        except Exception:
            con.rollback()
            raise


def connect(path=None):
    path = path or PATH
    if path != ":memory:":
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    con = sqlite3.connect(path, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    return con


@contextlib.contextmanager
def connection():
    """Verbindung mit Transaktion: Commit am Ende, Rollback bei Fehler."""
    con = connect()
    try:
        with con:
            yield con
    finally:
        con.close()


def setup():
    con = connect()
    try:
        migrate(con)
    finally:
        con.close()
