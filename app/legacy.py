# -*- coding: utf-8 -*-
"""
Übernahme der Einzel-Installation der FF Rheinbrohl in die mandantenfähige Ablage.

Bis zur Mandantenfähigkeit lag der ganze Bestand in DATA_DIR/einsaetze.db, die Fachkonstanten
standen im Code (rheinbrohl_config) und berechtigt waren die Adressen aus AUTH_EMAILS.
migrate_single_install() macht daraus beim ersten Start einmalig die VG Bad Hönningen mit der
Wehr Rheinbrohl. Danach liegen die Werte nur noch in deren Datenbank.
"""
import json
import logging
import os
import shutil
import sqlite3

from app import db, tenancy
from app.tenant_config import TenantConfig, Vehicle

log = logging.getLogger("pdf2einsatz")

LEGACY_FILE = "einsaetze.db"
BACKUP_FILE = "einsaetze-vor-mandanten.db"
VG_SLUG, VG_NAME = "bad-hoenningen", "VG Bad Hönningen"
TENANT_SLUG = "rheinbrohl"
ASSET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "legacy_assets")
# Logos der bisherigen Oberfläche -> Assets der Wehr (Name: Datei, Typ)
LOGOS = {"logo-light": ("logo-weiss.png", "image/png"), "logo-dark": ("logo-schwarz.png", "image/png"),
         "icon": ("logo.svg", "image/svg+xml")}


def rheinbrohl_config():
    return TenantConfig(
        name="Feuerwehr Rheinbrohl",
        # Reihenfolge der Einsatzübersicht; 01/10 fehlt in der Gesamtstärke des Bedarfsplans (Excel-Spalte AU)
        fleet=(Vehicle("02/45"), Vehicle("02/24"), Vehicle("02/71"), Vehicle("02/19"),
               Vehicle("01/10", in_plan_crew=False)),
        substitutes={"01/23": "02/45"},
        unit_prefix="FL NR#.BHÖ ",            # Fahrzeuge der Verbandsgemeinde Bad Hönningen
        own_prefix="02/",                     # Fahrzeuge des Löschzugs Rheinbrohl
        unit_marker="FW NR#.BHÖ 02",
        control_center="FL NR#.LIN",
        places=(("Rheinbrohl", "rhein"), ("Arienheller", "arienh"), ("Hammerstein", "hammer"),
                ("Ariendorf", "ariend"), ("Bad Hönningen", "bad hönn"), ("Leutesdorf", "leutes")),
        # Ausrückebereich laut Feuerwehrbedarfsplan Pos. 8.4
        plan_places=("Rheinbrohl", "Hammerstein", "Arienheller"),
    )


# Satzung über den Kostenersatz und die Gebührenerhebung für Hilfe- und Dienstleistungen der Feuerwehr
# der VG Bad Hönningen vom 16.05.2024, Anlage „Verzeichnis der Kostensätze“ (Euro je Stunde)
FEE_SCHEDULE_2024 = {
    "name": "Satzung vom 16.05.2024", "valid_from": "2024-08-10",
    "rates": {
        "personnel": 33.45, "personnel_bma": 33.45, "fire_watch": 12.00, "bma_flat_max": 400.00,
        "admin_surcharge": 10,
        "vehicles": [
            {"code": "TSF", "name": "Tragkraftspritzenfahrzeug", "rate": 67.00},
            {"code": "LF 8/6", "name": "Löschgruppenfahrzeug 8/6", "rate": 110.00},
            {"code": "LF 10", "name": "Löschgruppenfahrzeug 10", "rate": 313.00},
            {"code": "HLF 10", "name": "Hilfeleistungs-Löschgruppenfahrzeug 10", "rate": 341.00},
            {"code": "HLF 20", "name": "Hilfeleistungs-Löschgruppenfahrzeug 20", "rate": 447.00},
            {"code": "TLF 16/25", "name": "Tanklöschfahrzeug 16/25", "rate": 106.00},
            {"code": "GTLF 20/40", "name": "Großtanklöschfahrzeug 20/40", "rate": 102.00},
            {"code": "DLK 23/12", "name": "Drehleiter mit Korb 23/12", "rate": 366.00},
            {"code": "ELW 1", "name": "Einsatzleitwagen 1", "rate": 102.00},
            {"code": "MZB", "name": "Mehrzweckboot", "rate": 97.50},
            {"code": "RTB 1", "name": "Rettungsboot 1", "rate": 37.00},
            {"code": "RTB 2", "name": "Rettungsboot 2", "rate": 59.00},
            {"code": "HWK", "name": "Hochwasserkahn", "rate": 3.00},
            {"code": "MZF 1", "name": "Mehrzweckfahrzeug", "rate": 61.00},
            {"code": "MTF", "name": "Mannschaftstransportfahrzeug", "rate": 37.00},
            {"code": "KdoW", "name": "Kommandowagen", "rate": 43.00},
            {"code": "Anhänger", "name": "Anhänger (Logistik)", "rate": 2.00},
            {"code": "Rollcontainer", "name": "Rollcontainer (TS, Schlauch, Unwetter)", "rate": 1.50},
            {"code": "PFPN 10-1000", "name": "Tragkraftspritze", "rate": 9.75},
            {"code": "NEA 17 kVA", "name": "Netzersatzanlage 17 kVA", "rate": 10.56},
        ],
    },
}


def seed_fee_schedule(con, vg_id):
    """Gebührenordnung der VG Bad Hönningen anlegen (nur wenn die VG noch keine hat)."""
    if not con.execute("SELECT 1 FROM fee_schedule WHERE vg_id = ?", (vg_id,)).fetchone():
        s = FEE_SCHEDULE_2024
        con.execute("INSERT INTO fee_schedule (vg_id, name, valid_from, rates, modified_by) VALUES (?, ?, ?, ?, 'System')",
                    (vg_id, s["name"], s["valid_from"], json.dumps(s["rates"], ensure_ascii=False)))


def legacy_emails():
    return [tenancy.normalize_email(e) for e in os.environ.get("AUTH_EMAILS", "").replace(";", ",").split(",")
            if e.strip()]


def needs_migration(data_dir):
    return not os.path.exists(os.path.join(data_dir, "app.db")) and \
        os.path.exists(os.path.join(data_dir, LEGACY_FILE))


def _copy_database(source, target):
    """Konsistente Kopie auch im WAL-Modus (SQLite-Backup statt Dateikopie)."""
    src, dst = sqlite3.connect(source), sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def migrate_single_install(data_dir):
    """Einmalig: DATA_DIR/einsaetze.db wird zur Wehr Rheinbrohl. Die alte Datei bleibt als
    einsaetze-vor-mandanten.db liegen. Bricht der Ablauf ab, beginnt er beim nächsten Start neu."""
    legacy, central = os.path.join(data_dir, LEGACY_FILE), os.path.join(data_dir, "app.db")
    staging = central + ".neu"
    target = tenancy.tenant_path(TENANT_SLUG)
    for leftover in (staging, staging + "-wal", staging + "-shm"):
        if os.path.exists(leftover):
            os.remove(leftover)
    shutil.rmtree(os.path.dirname(target), ignore_errors=True)
    os.makedirs(os.path.dirname(target))

    # WAL der alten Datei zurückschreiben, damit die umbenannte Sicherung vollständig ist
    con = sqlite3.connect(legacy)
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    con.close()
    _copy_database(legacy, target)
    db.setup(target)
    cfg = rheinbrohl_config()
    with db.connection(target) as con:
        tenancy.save_config(con, cfg)
        for name, (filename, content_type) in LOGOS.items():
            with open(os.path.join(ASSET_DIR, filename), "rb") as f:
                con.execute("INSERT OR REPLACE INTO asset (name, content_type, data) VALUES (?, ?, ?)",
                            (name, content_type, f.read()))
        incidents = con.execute("SELECT COUNT(*) FROM incident").fetchone()[0]

    db.setup(staging, db.CENTRAL_MIGRATIONS)
    with db.connection(staging) as con:
        vg_id = tenancy.create_vg(con, VG_SLUG, VG_NAME)
        tenant_id = con.execute("INSERT INTO tenant (slug, name, vg_id) VALUES (?, ?, ?)",
                                (TENANT_SLUG, cfg.name, vg_id)).lastrowid
        emails = legacy_emails()
        for email in emails:
            tenancy.grant(con, email, "lead", tenant_id)
        # Eigenbetrieb der eigenen Wehr: kein AVV nötig (siehe dpa.py)
        con.execute("INSERT INTO dpa (vg_id, status) VALUES (?, 'not_required')", (vg_id,))
        seed_fee_schedule(con, vg_id)
        con.execute("INSERT INTO dpa_event (vg_id, email, action, detail) VALUES (?, 'System', ?, ?)",
                    (vg_id, "Status: nicht erforderlich (Eigenbetrieb)", "Übernahme der Einzel-Installation"))
    con = sqlite3.connect(staging)
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    con.close()
    os.replace(staging, central)
    os.replace(legacy, os.path.join(data_dir, BACKUP_FILE))
    for suffix in ("-wal", "-shm"):
        for path in (legacy + suffix, staging + suffix):
            if os.path.exists(path):
                os.remove(path)
    log.info("Mandanten: %s mit %d Einsätzen als Wehr '%s' in der %s übernommen, %d Adressen aus AUTH_EMAILS "
             "als Wehrführer zugeordnet. Die alte Datei liegt als %s im Datenordner.",
             LEGACY_FILE, incidents, TENANT_SLUG, VG_NAME, len(emails), BACKUP_FILE)
