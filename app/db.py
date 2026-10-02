# -*- coding: utf-8 -*-
"""
SQLite-Datenbanken mit schrittweisen Migrationen (liegen im Docker-Volume /daten).

  DATA_DIR/app.db                      zentral: Verbandsgemeinden, Wehren, Benutzer, Zuordnungen
  DATA_DIR/tenants/<slug>/einsaetze.db je Wehr: Einsätze, Kameraden, Fachkonfiguration, Logos

Jede Datei zählt ihre erledigten Schritte über PRAGMA user_version.
"""
import contextlib
import os
import sqlite3

# Früher zeigte DB_PATH direkt auf die einzige Datenbank; ihr Ordner ist dann der Datenordner.
DATA_DIR = os.environ.get("DATA_DIR") or os.path.dirname(os.environ.get("DB_PATH", ""))

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


def _add_tenant_tables(con):
    """Fachkonfiguration, Logos, Fahrzeuge mit Dienstzeitraum und Stichwortkatalog der Wehr;
    Einsatznummer der Leitstelle für gemeinsame Einsätze mehrerer Wehren."""
    con.execute("CREATE TABLE setting (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    con.execute("CREATE TABLE asset (name TEXT PRIMARY KEY, content_type TEXT NOT NULL, data BLOB NOT NULL, "
                "modified TEXT NOT NULL DEFAULT (datetime('now', 'localtime')))")
    con.execute("CREATE TABLE fleet (call_sign TEXT PRIMARY KEY, label TEXT NOT NULL DEFAULT '', "
                "sort_order INTEGER NOT NULL, in_service_from TEXT, in_service_until TEXT, replaced_by TEXT, "
                "in_plan_crew INTEGER NOT NULL DEFAULT 1)")
    con.execute("CREATE TABLE keyword (code TEXT PRIMARY KEY, name TEXT NOT NULL, terms TEXT NOT NULL DEFAULT '', "
                "active INTEGER NOT NULL DEFAULT 1, sort_order INTEGER NOT NULL)")
    con.execute("ALTER TABLE incident ADD COLUMN dispatch_number TEXT")
    con.execute("ALTER TABLE incident ADD COLUMN modified_by TEXT")
    con.execute("CREATE INDEX incident_dispatch_number ON incident(dispatch_number) WHERE dispatch_number IS NOT NULL")


def _create_central_schema(con):
    con.execute("CREATE TABLE vg (id INTEGER PRIMARY KEY, slug TEXT NOT NULL UNIQUE, name TEXT NOT NULL, "
                "created TEXT NOT NULL DEFAULT (datetime('now', 'localtime')))")
    con.execute("CREATE TABLE tenant (id INTEGER PRIMARY KEY, slug TEXT NOT NULL UNIQUE, name TEXT NOT NULL, "
                "vg_id INTEGER NOT NULL REFERENCES vg(id), active INTEGER NOT NULL DEFAULT 1, "
                "created TEXT NOT NULL DEFAULT (datetime('now', 'localtime')))")
    con.execute("CREATE TABLE account (email TEXT PRIMARY KEY, last_login TEXT, "
                "created TEXT NOT NULL DEFAULT (datetime('now', 'localtime')))")
    # scope 'vg' -> scope_id = vg.id, scope 'tenant' -> scope_id = tenant.id
    con.execute("CREATE TABLE membership (email TEXT NOT NULL REFERENCES account(email) ON DELETE CASCADE, "
                "scope TEXT NOT NULL CHECK (scope IN ('vg', 'tenant')), scope_id INTEGER NOT NULL, "
                "role TEXT NOT NULL, created TEXT NOT NULL DEFAULT (datetime('now', 'localtime')), "
                "PRIMARY KEY (email, scope, scope_id))")


# Neue Schemaänderungen nur hinten anfügen; PRAGMA user_version zählt die erledigten Schritte.
TENANT_MIGRATIONS = [_create_legacy_schema, _rename_to_english, _add_tenant_tables]
CENTRAL_MIGRATIONS = [_create_central_schema]


def migrate(con, steps=TENANT_MIGRATIONS):
    done = con.execute("PRAGMA user_version").fetchone()[0]
    for number, step in enumerate(steps[done:], start=done + 1):
        # sqlite3 öffnet vor DDL keine Transaktion von selbst – ohne BEGIN wäre ein Schritt nicht atomar
        con.execute("BEGIN")
        try:
            step(con)
            con.execute(f"PRAGMA user_version = {number}")
            con.commit()
        except Exception:
            con.rollback()
            raise


def connect(path):
    if path != ":memory:":
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    con = sqlite3.connect(path, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    return con


@contextlib.contextmanager
def connection(path):
    """Verbindung mit Transaktion: Commit am Ende, Rollback bei Fehler."""
    con = connect(path)
    try:
        with con:
            yield con
    finally:
        con.close()


def setup(path, steps=TENANT_MIGRATIONS):
    con = connect(path)
    try:
        migrate(con, steps)
    finally:
        con.close()
