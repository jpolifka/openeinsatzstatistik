# -*- coding: utf-8 -*-
"""
Mandanten: Verbandsgemeinden (VG), ihre Wehren, Benutzer und ihre Zuordnungen (Rollen).

Jede Wehr hat eine eigene Datenbank (tenants/<slug>/einsaetze.db) mit Einsätzen und ihrer
Fachkonfiguration. Die zentrale Datenbank (app.db) kennt VGs, Wehren, Rollen und Zuordnungen.

Rollen und Rechte stehen in rbac.py (Startbestand: Wehrleiter und Statistik VG für die VG, Wehrführer,
Erfasser und Benutzer für eine Wehr). Eine Zuordnung zur VG gilt in allen ihren Wehren. Superadmins
(ADMIN_EMAILS) dürfen alles. Ohne ADMIN_EMAILS ist die Anmeldung aus (lokaler Betrieb): dann gilt
jeder Aufruf als Superadmin.
"""
import dataclasses
import json
import os
import re
import threading

from app import db, domain, rbac
from app.tenant_config import TenantConfig, Vehicle

ADMIN_EMAILS = {e.strip().lower() for e in os.environ.get("ADMIN_EMAILS", "").replace(";", ",").split(",")
                if e.strip()}

SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,38}[a-z0-9]")

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
             "plan_min_level", "response_limits", "default_limit", "second_limit", "day_hours", "colors",
             "numbering", "response_plan_public")
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
                          bool(r["in_plan_crew"]), r["name"])
                  for r in con.execute("SELECT * FROM fleet ORDER BY sort_order, call_sign"))
    rows = con.execute("SELECT code, name, terms, active FROM keyword ORDER BY sort_order, code").fetchall()
    keywords = tuple((r["code"], r["name"], r["terms"]) for r in rows if r["active"])
    inactive = tuple((r["code"], r["name"], r["terms"]) for r in rows if not r["active"])
    return TenantConfig(name=name, fleet=fleet, keywords=keywords if rows else domain.KEYWORD_CATALOG,
                        inactive_keywords=inactive, **kwargs)


def save_config(con, cfg, keywords=False):
    """Fachkonfiguration und Fahrzeuge speichern; den Stichwortkatalog nur mit keywords=True
    (solange keine eigene Liste gespeichert ist, gilt die Vorlage)."""
    for key in _SETTINGS:
        con.execute("INSERT INTO setting (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, json.dumps(getattr(cfg, key), ensure_ascii=False)))
    con.execute("DELETE FROM fleet")
    for order, v in enumerate(cfg.fleet, start=1):
        con.execute("INSERT INTO fleet (call_sign, name, label, sort_order, in_service_from, in_service_until, "
                    "replaced_by, in_plan_crew) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (v.call_sign, v.name, v.label, order, v.in_service_from, v.in_service_until, v.replaced_by,
                     int(v.in_plan_crew)))
    if keywords:
        con.execute("DELETE FROM keyword")
        con.executemany("INSERT INTO keyword (code, name, terms, sort_order) VALUES (?, ?, ?, ?)",
                        [(code, name, terms, order) for order, (code, name, terms) in enumerate(cfg.keywords, 1)])


# ---------------------------------------------------------------- Stichwortkatalog der Wehr
def keywords(con):
    """Eigener Katalog [{code, name, terms, active}] oder None, solange die Vorlage gilt."""
    rows = con.execute("SELECT code, name, terms, active FROM keyword ORDER BY sort_order, code").fetchall()
    return [{**dict(r), "active": bool(r["active"])} for r in rows] or None


def _own_keywords(con):
    """Vor der ersten Änderung die Vorlage als eigenen Katalog übernehmen."""
    if not con.execute("SELECT 1 FROM keyword LIMIT 1").fetchone():
        add_template_keywords(con)


def add_template_keywords(con):
    """Stichworte der Vorlage ergänzen, die im eigenen Katalog fehlen -> Anzahl."""
    known = {r[0] for r in con.execute("SELECT code FROM keyword")}
    order = con.execute("SELECT COALESCE(MAX(sort_order), 0) FROM keyword").fetchone()[0]
    missing = [k for k in domain.KEYWORD_CATALOG if k[0] not in known]
    con.executemany("INSERT INTO keyword (code, name, terms, sort_order) VALUES (?, ?, ?, ?)",
                    [(code, name, terms, order + i) for i, (code, name, terms) in enumerate(missing, 1)])
    return len(missing)


def save_keyword(con, code, name, terms="", active=True):
    _own_keywords(con)
    order = con.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 FROM keyword").fetchone()[0]
    con.execute("INSERT INTO keyword (code, name, terms, active, sort_order) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(code) DO UPDATE SET name = excluded.name, terms = excluded.terms, active = excluded.active",
                (code, name, terms, int(active), order))


def delete_keyword(con, code):
    _own_keywords(con)
    con.execute("DELETE FROM keyword WHERE code = ?", (code,))


def replace_keywords(con, entries):
    """Katalog durch [(code, name, terms)] ersetzen; leer = zurück zur Vorlage."""
    con.execute("DELETE FROM keyword")
    con.executemany("INSERT INTO keyword (code, name, terms, sort_order) VALUES (?, ?, ?, ?)",
                    [(code, name, terms, i) for i, (code, name, terms) in enumerate(entries, 1)])


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
    # IDs gelöschter Wehren nicht wiederverwenden: das Rollen-Protokoll verweist weiter auf sie
    tenant_id = con.execute("SELECT MAX(id) FROM (SELECT MAX(id) AS id FROM tenant "
                            "UNION ALL SELECT MAX(tenant_id) FROM role_event)").fetchone()[0] or 0
    tenant_id = con.execute("INSERT INTO tenant (id, slug, name, vg_id) VALUES (?, ?, ?, ?)",
                            (tenant_id + 1, slug, name.strip(), vg_id)).lastrowid
    db.setup(path)
    with db.connection(path) as tenant_con:
        save_config(tenant_con, cfg or TenantConfig(name=name))
    return tenant_id


def add_account(con, email):
    email = normalize_email(email)
    con.execute("INSERT OR IGNORE INTO account (email) VALUES (?)", (email,))
    return email


def scope_vg(con, scope, scope_id):
    """VG-ID eines Bereichs (die VG selbst bzw. die VG der Wehr) oder None."""
    if scope == "vg":
        row = con.execute("SELECT id FROM vg WHERE id = ?", (scope_id,)).fetchone()
    else:
        row = con.execute("SELECT vg_id FROM tenant WHERE id = ?", (scope_id,)).fetchone()
    return row[0] if row else None


def find_role(con, key, scope, scope_id):
    """Rolle mit diesem Schlüssel, die im Bereich gilt (System-, globale oder eigene Rolle der VG), sonst None."""
    role = rbac.Roles(con).find(key, scope_vg(con, scope, scope_id))
    return role if role and role.scope == scope else None


def grant(con, email, role, scope_id):
    """Rolle zuordnen (zusätzlich zu vorhandenen); role ist der Schlüssel, scope_id die VG- bzw. Wehr-ID
    passend zum Bereich der Rolle."""
    for scope in ("tenant", "vg"):
        found = find_role(con, role, scope, scope_id)
        if found:
            break
    else:
        raise ValueError(f"Rolle „{role}“ gibt es in diesem Bereich nicht.")
    email = add_account(con, email)
    con.execute("INSERT OR IGNORE INTO membership (email, scope, scope_id, role_id) VALUES (?, ?, ?, ?)",
                (email, found.scope, scope_id, found.id))
    return found


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
    tenants: dict              # slug -> Tenant, nur aktive Wehren mit mindestens einem Recht (und AVV)
    roles: list                # [{role, role_id, scope, scope_id, vg_id, label}] eigene Zuordnungen
    vgs: dict = dataclasses.field(default_factory=dict)   # slug -> Name der VGs mit Gesamtansicht
    vg_permissions: dict = dataclasses.field(default_factory=dict)   # VG-ID -> Rechte aus Rollen der VG
    selected: Tenant = None
    vg: str = None             # Slug der ausgewählten VG
    blocked: list = dataclasses.field(default_factory=list)   # [{slug, name}] VGs, deren Wehren der AVV fehlt

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

    def vg_can(self, vg_id, permission):
        """Recht auf Ebene der VG (aus Rollen der VG): Gesamtansicht, Prüfprotokoll, Gebühren, Rollen."""
        return self.superadmin or permission in self.vg_permissions.get(vg_id, ())

    def grantable(self, roles, scope, scope_id, vg_id):
        """IDs der Rollen, die der Benutzer in diesem Bereich vergeben und entziehen darf: nach der Verteilung
        seiner Rollen der VG und – bei einer Wehr – seiner Rollen dieser Wehr."""
        visible = {r.id for r in roles.visible(vg_id) if r.scope == scope}
        if self.superadmin:
            return visible
        result = set()
        for r in self.roles:
            if (r["scope"] == "vg" and r["scope_id"] == vg_id) or \
                    (scope == "tenant" and r["scope"] == "tenant" and r["scope_id"] == scope_id):
                result |= roles.grants(r["role_id"])
        return result & visible

    def is_member(self, tenant):
        """Hat eine eigene Rolle in dieser Wehr (nicht nur über VG-Rolle oder als Superadmin)."""
        return any(r["scope"] == "tenant" and r["scope_id"] == tenant.id for r in self.roles)

    @property
    def scope_key(self):
        return f"vg:{self.vg}" if self.vg else f"t:{self.selected.slug}" if self.selected else None

    def scopes(self):
        """Auswahlmöglichkeiten für die Kopfzeile: je VG die Wehrleitung (Gesamtansicht aller Wehren), dann die Wehren."""
        result = []
        for vg_slug, vg_name in self.vgs.items():
            result.append({"key": f"vg:{vg_slug}", "name": f"Wehrleitung · {vg_name}", "vg": vg_name})
        result += [{"key": f"t:{t.slug}", "name": t.name, "vg": t.vg_name}
                   for t in sorted(self.tenants.values(), key=lambda t: (t.vg_name, t.name))]
        return result


def vg_tenants(vg_id):
    """Alle aktiven Wehren einer VG, ohne Rechte eines Benutzers – für Abgleich, Hinweise und Weitergabe
    von Berichten zwischen den Wehren (keine Ausgabe von Einsatzdaten an den Aufrufer)."""
    with central() as con:
        rows = con.execute("SELECT t.id, t.slug, t.name, t.vg_id, v.slug AS vg_slug, v.name AS vg_name "
                           "FROM tenant t JOIN vg v ON v.id = t.vg_id WHERE t.active AND t.vg_id = ? ORDER BY t.name",
                           (vg_id,)).fetchall()
    return [Tenant(r["id"], r["slug"], r["name"], r["vg_id"], r["vg_slug"], r["vg_name"], frozenset()) for r in rows]


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
        # Ohne AVV (fehlende Zeile = ausstehend) sind die Wehren einer VG gesperrt – außer für Superadmins
        signed = {r[0] for r in con.execute("SELECT vg_id FROM dpa WHERE status IN ('signed', 'not_required')")}
        roles = rbac.Roles(con)
        memberships = con.execute(
            "SELECT m.scope, m.scope_id, m.role_id, COALESCE(t.vg_id, m.scope_id) AS vg_id FROM membership m "
            "LEFT JOIN tenant t ON m.scope = 'tenant' AND t.id = m.scope_id WHERE m.email = ?",
            (email,)).fetchall() if email else []
    permissions = {r["slug"]: rbac.allowed(rbac.ALL_PERMISSIONS, "tenant") if superadmin else set() for r in rows}
    vg_permissions = {}
    for m in memberships:
        granted = roles.permissions(m["role_id"])
        if m["scope"] == "vg":
            vg_permissions.setdefault(m["scope_id"], set()).update(granted)
        for r in rows:
            if (m["scope"] == "tenant" and r["id"] == m["scope_id"]) or (m["scope"] == "vg" and r["vg_id"] == m["scope_id"]):
                permissions[r["slug"]] |= rbac.allowed(granted, "tenant")     # ohne reine VG-Rechte
    blocked = {} if superadmin else {r["vg_slug"]: r["vg_name"] for r in rows
                                     if permissions[r["slug"]] and r["vg_id"] not in signed}
    tenants = {r["slug"]: Tenant(r["id"], r["slug"], r["name"], r["vg_id"], r["vg_slug"], r["vg_name"],
                                 frozenset(permissions[r["slug"]]))
               for r in rows if permissions[r["slug"]] and r["vg_slug"] not in blocked}
    own = [{"role": role.key, "role_id": role.id, "scope": m["scope"], "scope_id": m["scope_id"], "vg_id": m["vg_id"],
            "label": role.label} for m in memberships if (role := roles.get(m["role_id"]))]
    overview = {vg_id for vg_id, granted in vg_permissions.items() if rbac.VG_OVERVIEW in granted}
    vgs = {}
    for r in rows:
        if r["slug"] in tenants and (superadmin or r["vg_id"] in overview):
            vgs.setdefault(r["vg_slug"], r["vg_name"])
    access = Access(email, superadmin, tenants, own, vgs, {k: frozenset(v) for k, v in vg_permissions.items()},
                    blocked=[{"slug": slug, "name": name} for slug, name in blocked.items()])
    kind, _, wanted = (scope or "").partition(":")
    if kind == "t" and wanted in tenants:
        access.selected = tenants[wanted]
    elif kind == "vg" and wanted in vgs:
        access.vg = wanted
    elif any(m["scope"] == "vg" for m in memberships) and vgs and not superadmin:
        access.vg = next(iter(vgs))
    else:
        access.selected = next(iter(tenants.values()), None)
    return access
