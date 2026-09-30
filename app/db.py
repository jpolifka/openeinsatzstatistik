# -*- coding: utf-8 -*-
"""SQLite-Datenbank der Einsätze (liegt im Docker-Volume /daten)."""
import contextlib, os, sqlite3

PFAD = os.environ.get("DB_PFAD", "/daten/einsaetze.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS einsatz (
    id          INTEGER PRIMARY KEY,
    jahr        INTEGER NOT NULL,
    nr          INTEGER,
    beginn      TEXT,               -- ISO-Datum/Zeit Einsatzbeginn (Spalte B+E)
    ende        TEXT,               -- ISO-Datum/Zeit Einsatzende
    stichwort   TEXT,               -- Spalte H, z. B. B2
    stufe       TEXT,               -- Spalte I, z. B. 07
    einsatz     TEXT,               -- Spalte J
    ort         TEXT,               -- Spalte K
    ehf         TEXT,               -- Spalte L
    personen_gh INTEGER NOT NULL DEFAULT 0,  -- Spalte AL
    wochenende  INTEGER NOT NULL DEFAULT 0,  -- Spalte AV
    quelle      TEXT NOT NULL,      -- 'excel' oder 'pdf'
    datei       TEXT,
    hinweise    TEXT NOT NULL DEFAULT '[]',
    erstellt    TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    geaendert   TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS einsatz_jahr_nr ON einsatz(jahr, nr) WHERE nr IS NOT NULL;

CREATE TABLE IF NOT EXISTS fahrzeug (
    einsatz_id  INTEGER NOT NULL REFERENCES einsatz(id) ON DELETE CASCADE,
    block       TEXT NOT NULL,      -- 02/45, 02/24, 02/71, 02/19, 01/10
    name        TEXT,
    staerke     INTEGER,
    aus         TEXT,               -- HH:MM:SS
    ein         TEXT,               -- HH:MM:SS
    PRIMARY KEY (einsatz_id, block)
);

CREATE TABLE IF NOT EXISTS kamerad (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,   -- wie im Kopf des Blatts Anwesenheit
    nachname    TEXT NOT NULL,
    vorname     TEXT NOT NULL,
    reihenfolge INTEGER
);

CREATE TABLE IF NOT EXISTS anwesenheit (
    einsatz_id  INTEGER NOT NULL REFERENCES einsatz(id) ON DELETE CASCADE,
    kamerad_id  INTEGER NOT NULL REFERENCES kamerad(id),
    funktion    TEXT,
    fahrzeug    TEXT,
    PRIMARY KEY (einsatz_id, kamerad_id)
);
"""


def verbinden():
    os.makedirs(os.path.dirname(PFAD), exist_ok=True)
    con = sqlite3.connect(PFAD, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    return con


@contextlib.contextmanager
def verbindung():
    con = verbinden()
    try:
        with con:
            yield con
    finally:
        con.close()


def einrichten():
    with verbindung() as con:
        con.executescript(SCHEMA)
