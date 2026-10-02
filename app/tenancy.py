# -*- coding: utf-8 -*-
"""
Mandanten: Verbandsgemeinden (VG), ihre Wehren, Benutzer und Rollen.

Jede Wehr hat eine eigene Datenbank (tenants/<slug>/einsaetze.db) mit Einsätzen und ihrer
Fachkonfiguration. Die zentrale Datenbank (app.db) kennt nur VGs, Wehren und Zuordnungen.

Rollen (Bereich, Rechte):
  vg_lead   Wehrleiter      VG    Statistik, Einsätze + Personal, Erfassen, Verwaltung, vergibt alle Rollen der VG
  vg_stats  Statistik VG    VG    nur Statistik (z. B. Bürgermeister)
  lead      Wehrführer      Wehr  Statistik, Einsätze + Personal, Erfassen, Verwaltung, vergibt Erfasser/Benutzer
  editor    Erfasser        Wehr  Statistik, Einsätze + Personal, Erfassen
  viewer    Benutzer        Wehr  nur Statistik
Superadmins (ADMIN_EMAILS) dürfen alles. Ohne ADMIN_EMAILS ist die Anmeldung aus (lokaler Betrieb):
dann gilt jeder Aufruf als Superadmin.
"""
import dataclasses
import json
import os
import re
import threading

from app import db, domain
from app.tenant_config import TenantConfig, Vehicle

ADMIN_EMAILS = {e.strip().lower() for e in os.environ.get("ADMIN_EMAILS", "").replace(";", ",").split(",")
                if e.strip()}

SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,38}[a-z0-9]")

# Rechte
STATS = "stats"            # Auswertung ohne Personenbezug
INCIDENTS = "incidents"    # Einsatzliste, Namen, Anwesenheit, Export
WRITE = "write"            # PDF einlesen, Einsätze bearbeiten und löschen
ADMIN = "admin"            # Fachkonfiguration und Branding der Wehr, Benutzer zuordnen

ROLES = {  # Rolle -> (Bereich, Bezeichnung, Rechte)
    "vg_lead": ("vg", "Wehrleiter", {STATS, INCIDENTS, WRITE, ADMIN}),
    "vg_stats": ("vg", "Statistik VG", {STATS}),
    "lead": ("tenant", "Wehrführer", {STATS, INCIDENTS, WRITE, ADMIN}),
    "editor": ("tenant", "Erfasser", {STATS, INCIDENTS, WRITE}),
    "viewer": ("tenant", "Benutzer", {STATS}),
}
ALL_PERMISSIONS = frozenset({STATS, INCIDENTS, WRITE, ADMIN})
# Welche Rollen eine Rolle vergeben darf (innerhalb ihres Bereichs)
GRANTABLE = {"vg_lead": set(ROLES), "lead": {"editor", "viewer"}}


def auth_enabled():
    return bool(ADMIN_EMAILS)


def central_path():
    return os.path.join(db.DATA_DIR, "app.db")


def tenant_path(slug):
    return os.path.join(db.DATA_DIR, "tenants", slug, "einsaetze.db")


def central():
    return db.connection(central_path())


def setup():
    """Zentrale Datenbank und alle Wehr-Datenbanken auf den aktuellen Stand bringen."""
    db.setup(central_path(), db.CENTRAL_MIGRATIONS)
    with central() as con:
        slugs = [r["slug"] for r in con.execute("SELECT slug FROM tenant")]
    for slug in slugs:
        db.setup(tenant_path(slug))
    _configs.clear()


# ---------------------------------------------------------------- Fachkonfiguration
# Schlüssel in der Tabelle setting; Fahrzeuge und Stichworte haben eigene Tabellen
_SETTINGS = ("substitutes", "unit_prefix", "own_prefix", "unit_marker", "control_center", "places", "plan_places",
             "plan_min_level", "response_limits", "default_limit", "second_limit", "day_hours")
_TUPLES = {"places", "plan_places", "response_limits", "day_hours"}

_configs = {}
_configs_lock = threading.Lock()


def load_config(con, name):
    """TenantConfig aus der Wehr-Datenbank. Fehlende Werte nehmen die Standardwerte, ein leerer
    Stichwortkatalog die Vorlage aus domain.py."""
    values = {r["key"]: json.loads(r["value"]) for r in con.execute("SELECT key, value FROM setting")}
    kwargs = {key: values[key] for key in _SETTINGS if key in values}
    for key in _TUPLES & set(kwargs):
        kwargs[key] = tuple(tuple(v) if isinstance(v, list) else v for v in kwargs[key])
    fleet = tuple(Vehicle(r["call_sign"], r["label"], r["in_service_from"], r["in_service_until"], r["replaced_by"],
                          bool(r["in_plan_crew"]))
                  for r in con.execute("SELECT * FROM fleet ORDER BY sort_order, call_sign"))
    keywords = tuple((r["code"], r["name"], r["terms"]) for r in con.execute(
        "SELECT code, name, terms FROM keyword WHERE active ORDER BY sort_order, code"))
    return TenantConfig(name=name, fleet=fleet, keywords=keywords or domain.KEYWORD_CATALOG, **kwargs)


def save_config(con, cfg, keywords=False):
    """Fachkonfiguration und Fahrzeuge speichern; den Stichwortkatalog nur mit keywords=True
    (solange keine eigene Liste gespeichert ist, gilt die Vorlage)."""
    for key in _SETTINGS:
        con.execute("INSERT INTO setting (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, json.dumps(getattr(cfg, key), ensure_ascii=False)))
    con.execute("DELETE FROM fleet")
    for order, v in enumerate(cfg.fleet, start=1):
        con.execute("INSERT INTO fleet (call_sign, label, sort_order, in_service_from, in_service_until, replaced_by, "
                    "in_plan_crew) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (v.call_sign, v.label, order, v.in_service_from, v.in_service_until, v.replaced_by,
                     int(v.in_plan_crew)))
    if keywords:
        con.execute("DELETE FROM keyword")
        con.executemany("INSERT INTO keyword (code, name, terms, sort_order) VALUES (?, ?, ?, ?)",
                        [(code, name, terms, order) for order, (code, name, terms) in enumerate(cfg.keywords, 1)])


def forget_config(slug):
    """Nach dem Speichern: Konfiguration beim nächsten Zugriff neu laden."""
    with _configs_lock:
        _configs.pop(slug, None)


# ---------------------------------------------------------------- Verbandsgemeinden, Wehren, Zuordnungen
def check_slug(slug):
    if not SLUG.fullmatch(slug or ""):
        raise ValueError("Kurzname: nur Kleinbuchstaben, Ziffern und Bindestrich (2–40 Zeichen).")
    return slug


def create_vg(con, slug, name):
    return con.execute("INSERT INTO vg (slug, name) VALUES (?, ?)", (check_slug(slug), name.strip())).lastrowid


def create_tenant(con, slug, name, vg_id, cfg=None):
    """Wehr anlegen: Eintrag in der Zentrale, eigene Datenbank mit Fachkonfiguration."""
    check_slug(slug)
    path = tenant_path(slug)
    if os.path.exists(path):
        raise ValueError(f"Für „{slug}“ gibt es schon eine Datenbank.")
    tenant_id = con.execute("INSERT INTO tenant (slug, name, vg_id) VALUES (?, ?, ?)",
                            (slug, name.strip(), vg_id)).lastrowid
    db.setup(path)
    with db.connection(path) as tenant_con:
        save_config(tenant_con, cfg or TenantConfig(name=name))
    return tenant_id


def add_account(con, email):
    email = normalize_email(email)
    con.execute("INSERT OR IGNORE INTO account (email) VALUES (?)", (email,))
    return email


def grant(con, email, role, scope_id):
    """Rolle zuordnen; scope_id ist die VG- bzw. Wehr-ID passend zum Bereich der Rolle."""
    scope = ROLES[role][0]
    email = add_account(con, email)
    con.execute("INSERT INTO membership (email, scope, scope_id, role) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(email, scope, scope_id) DO UPDATE SET role = excluded.role", (email, scope, scope_id, role))


def normalize_email(email):
    return (email or "").strip().lower()


def is_allowed(email):
    """Darf sich anmelden: Superadmin oder mindestens eine Zuordnung zu einer aktiven Wehr bzw. VG."""
    email = normalize_email(email)
    if email in ADMIN_EMAILS:
        return True
    if not email or not os.path.exists(central_path()):
        return False
    with central() as con:
        return con.execute(
            "SELECT 1 FROM membership m WHERE m.email = ? AND ("
            " (m.scope = 'tenant' AND EXISTS (SELECT 1 FROM tenant t WHERE t.id = m.scope_id AND t.active)) OR"
            " (m.scope = 'vg' AND EXISTS (SELECT 1 FROM tenant t WHERE t.vg_id = m.scope_id AND t.active)))",
            (email,)).fetchone() is not None


def record_login(email):
    with central() as con:
        con.execute("UPDATE account SET last_login = datetime('now', 'localtime') WHERE email = ?",
                    (normalize_email(email),))


# ---------------------------------------------------------------- Zugriff
@dataclasses.dataclass
class Tenant:
    id: int
    slug: str
    name: str
    vg_id: int
    vg_slug: str
    vg_name: str
    permissions: frozenset

    @property
    def db_path(self):
        return tenant_path(self.slug)

    @property
    def config(self):
        with _configs_lock:
            cfg = _configs.get(self.slug)
        if cfg is None or cfg.name != self.name:
            with db.connection(self.db_path) as con:
                cfg = load_config(con, self.name)
            with _configs_lock:
                _configs[self.slug] = cfg
        return cfg

    def connection(self):
        return db.connection(self.db_path)

    def can(self, permission):
        return permission in self.permissions

    def json(self):
        return {"slug": self.slug, "name": self.name, "vg": {"slug": self.vg_slug, "name": self.vg_name},
                "permissions": sorted(self.permissions)}


class Forbidden(Exception):
    """Kein Recht für diese Wehr bzw. Aktion (wird in main.py zu 403)."""


@dataclasses.dataclass
class Access:
    """Was ein Benutzer sehen und tun darf, und was gerade ausgewählt ist: eine Wehr
    (selected) oder alle sichtbaren Wehren einer VG (vg, für Wehrleiter, Statistik VG, Superadmin)."""
    email: str
    superadmin: bool
    tenants: dict              # slug -> Tenant, nur aktive Wehren mit mindestens einem Recht
    roles: list                # [{role, scope, scope_id, label}] für die Anzeige
    vgs: dict = dataclasses.field(default_factory=dict)   # slug -> Name der VGs mit Gesamtansicht
    selected: Tenant = None
    vg: str = None             # Slug der ausgewählten VG

    @property
    def selection(self):
        """Ausgewählte Wehren: die eine Wehr oder alle sichtbaren der VG."""
        if self.vg:
            return [t for t in self.tenants.values() if t.vg_slug == self.vg]
        return [self.selected] if self.selected else []

    def selection_with(self, permission):
        """Ausgewählte Wehren mit dem verlangten Recht; keine heißt Forbidden."""
        tenants = [t for t in self.selection if t.can(permission)]
        if not tenants:
            raise Forbidden("Keine Berechtigung für diese Auswahl.")
        return tenants

    def tenant(self, slug, permission):
        """Wehr mit dem verlangten Recht, sonst Forbidden – auch für unbekannte Kurznamen."""
        tenant = self.tenants.get(slug)
        if not tenant or not tenant.can(permission):
            raise Forbidden("Keine Berechtigung für diese Wehr.")
        return tenant

    def current(self, permission):
        """Die eine ausgewählte Wehr mit dem verlangten Recht (Endpunkte ohne VG-Gesamtansicht)."""
        if self.vg:
            raise Forbidden("Bitte oben eine einzelne Wehr auswählen.")
        if not self.selected:
            raise Forbidden("Keine Wehr zugeordnet.")
        return self.tenant(self.selected.slug, permission)

    @property
    def scope_key(self):
        return f"vg:{self.vg}" if self.vg else f"t:{self.selected.slug}" if self.selected else None

    def scopes(self):
        """Auswahlmöglichkeiten für die Kopfzeile: je VG mit Gesamtansicht „alle Wehren“, dann die Wehren."""
        result = []
        for vg_slug, vg_name in self.vgs.items():
            result.append({"key": f"vg:{vg_slug}", "name": f"Alle Wehren · {vg_name}", "vg": vg_name})
        result += [{"key": f"t:{t.slug}", "name": t.name, "vg": t.vg_name}
                   for t in sorted(self.tenants.values(), key=lambda t: (t.vg_name, t.name))]
        return result


def access_for(email, scope=None):
    """Zugriff für eine (angemeldete) Adresse. email=None heißt Anmeldung aus: Superadmin.

    scope (Cookie) wählt eine Wehr ("t:<slug>") oder die Gesamtansicht einer VG ("vg:<slug>").
    Unbekannte oder nicht erlaubte Werte werden ignoriert; dann gilt die Gesamtansicht der eigenen
    VG (Rollen auf VG-Ebene) bzw. die erste sichtbare Wehr.
    """
    email = normalize_email(email) if email else None
    superadmin = email is None or email in ADMIN_EMAILS
    with central() as con:
        rows = con.execute("SELECT t.id, t.slug, t.name, t.vg_id, v.slug AS vg_slug, v.name AS vg_name "
                           "FROM tenant t JOIN vg v ON v.id = t.vg_id WHERE t.active ORDER BY v.name, t.name").fetchall()
        memberships = con.execute("SELECT scope, scope_id, role FROM membership WHERE email = ?",
                                  (email,)).fetchall() if email else []
    permissions = {r["slug"]: set(ALL_PERMISSIONS) if superadmin else set() for r in rows}
    for m in memberships:
        if m["role"] not in ROLES:
            continue
        for r in rows:
            if (m["scope"] == "tenant" and r["id"] == m["scope_id"]) or (m["scope"] == "vg" and r["vg_id"] == m["scope_id"]):
                permissions[r["slug"]] |= ROLES[m["role"]][2]
    tenants = {r["slug"]: Tenant(r["id"], r["slug"], r["name"], r["vg_id"], r["vg_slug"], r["vg_name"],
                                 frozenset(permissions[r["slug"]])) for r in rows if permissions[r["slug"]]}
    roles = [{"role": m["role"], "scope": m["scope"], "scope_id": m["scope_id"], "label": ROLES[m["role"]][1]}
             for m in memberships if m["role"] in ROLES]
    vg_role_ids = {m["scope_id"] for m in memberships if m["scope"] == "vg" and m["role"] in ROLES}
    vgs = {}
    for r in rows:
        if r["slug"] in tenants and (superadmin or r["vg_id"] in vg_role_ids):
            vgs.setdefault(r["vg_slug"], r["vg_name"])
    access = Access(email, superadmin, tenants, roles, vgs)
    kind, _, wanted = (scope or "").partition(":")
    if kind == "t" and wanted in tenants:
        access.selected = tenants[wanted]
    elif kind == "vg" and wanted in vgs:
        access.vg = wanted
    elif vg_role_ids and vgs and not superadmin:
        access.vg = next(iter(vgs))
    else:
        access.selected = next(iter(tenants.values()), None)
    return access
