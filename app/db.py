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


def _add_bks_ids(con):
    """Datensätze des BKS-Portals (eigener Bericht und Stammdatensatz des Einsatzes), Alarmierung und
    Einsatzende je Fahrzeug, manuell ergänzte Fahrzeuge/Personen; Zeitgrenze 8 Min. entfällt."""
    con.execute("ALTER TABLE incident ADD COLUMN bks_report_id TEXT")
    con.execute("ALTER TABLE incident ADD COLUMN bks_record_id TEXT")
    con.execute("CREATE UNIQUE INDEX incident_bks_report ON incident(bks_report_id) WHERE bks_report_id IS NOT NULL")
    con.execute("CREATE INDEX incident_bks_record ON incident(bks_record_id) WHERE bks_record_id IS NOT NULL")
    con.execute("ALTER TABLE vehicle ADD COLUMN alerted TEXT")
    con.execute("ALTER TABLE vehicle ADD COLUMN finished TEXT")
    con.execute("ALTER TABLE vehicle ADD COLUMN manual INTEGER NOT NULL DEFAULT 0")
    con.execute("ALTER TABLE attendance ADD COLUMN manual INTEGER NOT NULL DEFAULT 0")
    con.execute("UPDATE setting SET value = '[10]' WHERE key = 'response_limits'")
    con.execute("UPDATE setting SET value = '10' WHERE key = 'default_limit'")


def _add_pending_reports(con):
    """Berichte, die jemand aus einer anderen Wehr eingelesen hat, bis zur Übernahme durch diese Wehr."""
    con.execute("CREATE TABLE pending_report (id INTEGER PRIMARY KEY, bks_report_id TEXT UNIQUE, bks_record_id TEXT, "
                "number_text TEXT, first_alarm TEXT, keyword TEXT, reported_as TEXT, filename TEXT NOT NULL, "
                "pdf BLOB NOT NULL, uploaded_by TEXT, uploaded TEXT NOT NULL DEFAULT (datetime('now', 'localtime')))")


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


def _add_dpa(con):
    """Auftragsverarbeitungsvertrag je VG (siehe dpa.py) und sein Protokoll, an das nur angehängt wird.
    Die VG der früheren Einzel-Installation (Eigenbetrieb) braucht keinen AVV."""
    con.execute("CREATE TABLE dpa (vg_id INTEGER PRIMARY KEY REFERENCES vg(id) ON DELETE CASCADE, "
                "status TEXT NOT NULL DEFAULT 'pending', template_version INTEGER, client_data TEXT NOT NULL DEFAULT '{}', "
                "generated_hash TEXT, signed_on TEXT, document_link TEXT, document_file TEXT, document_hash TEXT, "
                "confirmed_by TEXT, confirmed_at TEXT, updated TEXT NOT NULL DEFAULT (datetime('now', 'localtime')))")
    con.execute("CREATE TABLE dpa_event (id INTEGER PRIMARY KEY, vg_id INTEGER NOT NULL, "
                "at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')), email TEXT, action TEXT NOT NULL, detail TEXT)")
    for change in ("UPDATE", "DELETE"):
        con.execute(f"CREATE TRIGGER dpa_event_no_{change.lower()} BEFORE {change} ON dpa_event "
                    "BEGIN SELECT RAISE(ABORT, 'Das AVV-Protokoll wird nur ergänzt.'); END")
    for (vg_id,) in con.execute("SELECT id FROM vg WHERE slug = 'bad-hoenningen'").fetchall():
        con.execute("INSERT INTO dpa (vg_id, status) VALUES (?, 'not_required')", (vg_id,))
        con.execute("INSERT INTO dpa_event (vg_id, email, action, detail) VALUES (?, 'System', ?, ?)",
                    (vg_id, "Status: nicht erforderlich (Eigenbetrieb)", "Bestand der früheren Einzel-Installation"))


def _add_records(con):
    """Stammdatensätze des BKS-Portals je VG und Verzeichnis der eingelesenen Berichte – ohne Personen."""
    con.execute("CREATE TABLE master_record (bks_record_id TEXT PRIMARY KEY, "
                "vg_id INTEGER NOT NULL REFERENCES vg(id) ON DELETE CASCADE, dispatch_number TEXT, first_alarm TEXT, "
                "keyword TEXT, subcode TEXT, reported_as TEXT, town TEXT, district TEXT, street TEXT, "
                "vehicles TEXT NOT NULL DEFAULT '[]', filename TEXT, imported_by TEXT, "
                "imported TEXT NOT NULL DEFAULT (datetime('now', 'localtime')))")
    con.execute("CREATE TABLE record_report (bks_report_id TEXT PRIMARY KEY, bks_record_id TEXT, "
                "tenant_id INTEGER NOT NULL REFERENCES tenant(id) ON DELETE CASCADE, unit TEXT, kind TEXT, "
                "number_text TEXT, imported_by TEXT, imported TEXT NOT NULL DEFAULT (datetime('now', 'localtime')))")
    con.execute("CREATE INDEX record_report_record ON record_report(bks_record_id)")


def _add_notices(con):
    """Hinweise an Wehren (Import durch andere, Abweichungen, weitergegebene Berichte) und
    Prüfvermerke des Wehrleiters je Stammdatensatz. Texte ohne Personennamen."""
    con.execute("CREATE TABLE notice (id INTEGER PRIMARY KEY, "
                "tenant_id INTEGER NOT NULL REFERENCES tenant(id) ON DELETE CASCADE, kind TEXT NOT NULL, "
                "bks_record_id TEXT, incident_key TEXT, year INTEGER, text TEXT NOT NULL, created_by TEXT, "
                "created TEXT NOT NULL DEFAULT (datetime('now', 'localtime')), done_by TEXT, done TEXT)")
    con.execute("CREATE INDEX notice_open ON notice(tenant_id) WHERE done IS NULL")
    con.execute("CREATE TABLE record_review (bks_record_id TEXT PRIMARY KEY, "
                "vg_id INTEGER NOT NULL REFERENCES vg(id) ON DELETE CASCADE, findings_hash TEXT NOT NULL, "
                "reviewed_by TEXT, reviewed TEXT NOT NULL DEFAULT (datetime('now', 'localtime')))")


def _add_fee_schedules(con):
    """Gebührenordnungen (Kostenersatz) je VG in Fassungen mit Gültigkeitsbeginn; die VG der früheren
    Einzel-Installation bekommt die Satzung vom 16.05.2024 (legacy.FEE_SCHEDULE_2024)."""
    con.execute("CREATE TABLE fee_schedule (id INTEGER PRIMARY KEY, "
                "vg_id INTEGER NOT NULL REFERENCES vg(id) ON DELETE CASCADE, name TEXT NOT NULL, "
                "valid_from TEXT NOT NULL, rates TEXT NOT NULL, modified_by TEXT, "
                "modified TEXT NOT NULL DEFAULT (datetime('now', 'localtime')))")
    from app import legacy    # erst hier: legacy braucht db
    for (vg_id,) in con.execute("SELECT id FROM vg WHERE slug = ?", (legacy.VG_SLUG,)).fetchall():
        legacy.seed_fee_schedule(con, vg_id)


def _add_fleet_names(con):
    """Voller Funkrufname je Fahrzeug der Fahrzeugliste (wie im BKS-Bericht, z. B. „RP WW 01/23-06“),
    vorbelegt mit dem häufigsten Namen aus den Einsätzen; ohne solchen bleibt er leer (Zuordnung dann
    weiter über unit_prefix)."""
    con.execute("ALTER TABLE fleet ADD COLUMN name TEXT NOT NULL DEFAULT ''")
    # Nur Namen, die den Kurznamen enthalten – nicht ein Ersatzfahrzeug, das oft in dieser Spalte stand
    con.execute("UPDATE fleet SET name = COALESCE((SELECT v.name FROM vehicle v WHERE v.call_sign = fleet.call_sign "
                "AND v.name <> '' AND v.name NOT IN (SELECT name FROM fleet) "
                "AND (v.name LIKE '%' || fleet.call_sign || '-%' OR v.name LIKE '% ' || fleet.call_sign) "
                "GROUP BY v.name ORDER BY COUNT(*) DESC, v.name LIMIT 1), '')")


def _add_roles(con):
    """Rollen und Rechte in die Datenbank (siehe rbac.py): Startbestand aus rbac.SYSTEM_ROLES, Zuordnungen
    verweisen auf role.id, mehrere Rollen je Person und Bereich; Protokoll nur anhängbar."""
    from app import rbac    # erst hier, wie legacy
    con.execute("CREATE TABLE role (id INTEGER PRIMARY KEY, key TEXT NOT NULL, "
                "vg_id INTEGER REFERENCES vg(id) ON DELETE CASCADE, "
                "scope TEXT NOT NULL CHECK (scope IN ('vg', 'tenant')), label TEXT NOT NULL, "
                "description TEXT NOT NULL DEFAULT '', parent_id INTEGER REFERENCES role(id), "
                "system INTEGER NOT NULL DEFAULT 0, created TEXT NOT NULL DEFAULT (datetime('now', 'localtime')))")
    con.execute("CREATE UNIQUE INDEX role_key ON role(COALESCE(vg_id, 0), key)")
    con.execute("CREATE TABLE role_permission (role_id INTEGER NOT NULL REFERENCES role(id) ON DELETE CASCADE, "
                "permission TEXT NOT NULL, PRIMARY KEY (role_id, permission))")
    con.execute("CREATE TABLE role_grant (role_id INTEGER NOT NULL REFERENCES role(id) ON DELETE CASCADE, "
                "grantable_role_id INTEGER NOT NULL REFERENCES role(id) ON DELETE CASCADE, "
                "PRIMARY KEY (role_id, grantable_role_id))")
    con.execute("CREATE TABLE role_event (id INTEGER PRIMARY KEY, at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')), "
                "email TEXT, vg_id INTEGER, tenant_id INTEGER, action TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '')")
    for change in ("UPDATE", "DELETE"):
        con.execute(f"CREATE TRIGGER role_event_no_{change.lower()} BEFORE {change} ON role_event "
                    "BEGIN SELECT RAISE(ABORT, 'Das Rollen-Protokoll wird nur ergänzt.'); END")
    rbac.seed(con)
    con.execute("CREATE TABLE membership_new (email TEXT NOT NULL REFERENCES account(email) ON DELETE CASCADE, "
                "scope TEXT NOT NULL CHECK (scope IN ('vg', 'tenant')), scope_id INTEGER NOT NULL, "
                "role_id INTEGER NOT NULL REFERENCES role(id), "
                "created TEXT NOT NULL DEFAULT (datetime('now', 'localtime')), "
                "PRIMARY KEY (email, scope, scope_id, role_id))")
    con.execute("INSERT INTO membership_new (email, scope, scope_id, role_id, created) "
                "SELECT m.email, m.scope, m.scope_id, r.id, m.created FROM membership m "
                "JOIN role r ON r.key = m.role AND r.vg_id IS NULL AND r.scope = m.scope")
    con.execute("DROP TABLE membership")
    con.execute("ALTER TABLE membership_new RENAME TO membership")
    con.execute("CREATE INDEX membership_scope ON membership(scope, scope_id)")


def _records_per_vg(con):
    """Stammdatensätze und Prüfvermerke je VG: Schlüssel (bks_record_id, vg_id) statt nur bks_record_id,
    damit eine VG weder den Stammdatensatz noch den Prüfvermerk einer anderen belegt oder überschreibt."""
    for table, columns in (
            ("master_record", "bks_record_id TEXT NOT NULL, "
                              "vg_id INTEGER NOT NULL REFERENCES vg(id) ON DELETE CASCADE, dispatch_number TEXT, "
                              "first_alarm TEXT, keyword TEXT, subcode TEXT, reported_as TEXT, town TEXT, "
                              "district TEXT, street TEXT, vehicles TEXT NOT NULL DEFAULT '[]', filename TEXT, "
                              "imported_by TEXT, imported TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))"),
            ("record_review", "bks_record_id TEXT NOT NULL, "
                              "vg_id INTEGER NOT NULL REFERENCES vg(id) ON DELETE CASCADE, findings_hash TEXT NOT NULL, "
                              "reviewed_by TEXT, reviewed TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))")):
        con.execute(f"CREATE TABLE {table}_new ({columns}, PRIMARY KEY (bks_record_id, vg_id))")
        con.execute(f"INSERT INTO {table}_new SELECT * FROM {table}")
        con.execute(f"DROP TABLE {table}")
        con.execute(f"ALTER TABLE {table}_new RENAME TO {table}")


def _add_incident_revision(con):
    con.execute("ALTER TABLE incident ADD COLUMN revision INTEGER NOT NULL DEFAULT 0")


def _add_consumed_magic_links(con):
    con.execute("CREATE TABLE consumed_magic_link (token_hash TEXT PRIMARY KEY, expires REAL NOT NULL)")


def _add_sessions(con):
    """Serverseitige Sitzungen: im Cookie liegt nur ein Zufallswert, hier steht sein SHA-256."""
    con.execute("CREATE TABLE session (id INTEGER PRIMARY KEY AUTOINCREMENT, token_hash TEXT NOT NULL UNIQUE, "
                "email TEXT NOT NULL, created REAL NOT NULL, last_seen REAL NOT NULL, expires REAL NOT NULL, "
                "user_agent TEXT NOT NULL DEFAULT '')")
    con.execute("CREATE INDEX session_email ON session (email)")


def _add_import_jobs(con):
    con.execute("CREATE TABLE import_job (id TEXT PRIMARY KEY, incident_id INTEGER NOT NULL "
                "REFERENCES incident(id) ON DELETE CASCADE, report TEXT NOT NULL, email TEXT, "
                "is_member INTEGER NOT NULL, updated INTEGER NOT NULL)")


def _add_completed_imports(con):
    con.execute("CREATE TABLE completed_import (id TEXT PRIMARY KEY)")


def _add_tenant_archive(con):
    con.execute("CREATE TABLE tenant_archive (slug TEXT PRIMARY KEY, target TEXT NOT NULL, email TEXT)")


def _add_vg_defaults(con):
    """Vorgaben der VG für die Fachkonfiguration ihrer Wehren (siehe tenancy.load_config); eine Wehr speichert
    nur noch, wo sie abweicht. defaults_lifted: Werte der Wehren schon übernommen (tenancy.lift_vg_defaults)."""
    con.execute("CREATE TABLE vg_setting (vg_id INTEGER NOT NULL REFERENCES vg(id) ON DELETE CASCADE, "
                "key TEXT NOT NULL, value TEXT NOT NULL, PRIMARY KEY (vg_id, key))")
    con.execute("CREATE TABLE vg_keyword (vg_id INTEGER NOT NULL REFERENCES vg(id) ON DELETE CASCADE, "
                "code TEXT NOT NULL, name TEXT NOT NULL, terms TEXT NOT NULL DEFAULT '', "
                "active INTEGER NOT NULL DEFAULT 1, sort_order INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (vg_id, code))")
    con.execute("ALTER TABLE vg ADD COLUMN defaults_lifted INTEGER NOT NULL DEFAULT 0")


def _settings_for_fee_roles(con):
    """Fahrzeuge der VG pflegt jetzt, wer in der VG das Recht tenant.settings hat (vg.fees nur noch für die
    Gebührenordnung): Rollen der VG mit vg.fees bekommen es dazu, damit niemand die Fahrzeugpflege verliert."""
    con.execute("INSERT OR IGNORE INTO role_permission (role_id, permission) "
                "SELECT rp.role_id, 'tenant.settings' FROM role_permission rp JOIN role r ON r.id = rp.role_id "
                "WHERE rp.permission = 'vg.fees' AND r.scope = 'vg'")


# Neue Schemaänderungen nur hinten anfügen; PRAGMA user_version zählt die erledigten Schritte.
TENANT_MIGRATIONS = [_create_legacy_schema, _rename_to_english, _add_tenant_tables, _add_bks_ids,
                     _add_pending_reports, _add_fleet_names, _add_incident_revision, _add_import_jobs]
CENTRAL_MIGRATIONS = [_create_central_schema, _add_dpa, _add_records, _add_notices, _add_fee_schedules, _add_roles,
                      _records_per_vg, _add_consumed_magic_links, _add_completed_imports, _add_tenant_archive,
                      _add_vg_defaults, _settings_for_fee_roles, _add_sessions]


def migrate(con, steps=TENANT_MIGRATIONS):
    done = con.execute("PRAGMA user_version").fetchone()[0]
    if done > len(steps):
        raise RuntimeError("Datenbankschema ist neuer als diese Anwendung – kein Downgrade möglich")
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
