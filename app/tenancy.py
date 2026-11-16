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
import hashlib
import json
import logging
import os
import re
import threading

from app import db, domain, rbac
from app.tenant_config import UNIT_MARKER, TenantConfig, Vehicle, prefixes_of

ADMIN_EMAILS = {e.strip().lower() for e in os.environ.get("ADMIN_EMAILS", "").replace(";", ",").split(",")
                if e.strip()}

log = logging.getLogger("openeinsatzstatistik")

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
    from app import tenant_lifecycle
    tenant_lifecycle.recover()
    with central() as con:
        slugs = [r["slug"] for r in con.execute("SELECT slug FROM tenant WHERE slug NOT IN (SELECT slug FROM tenant_archive)")]
    for slug in slugs:
        db.setup(tenant_path(slug))
    _configs.clear()
    lift_vg_defaults()


# ---------------------------------------------------------------- Fachkonfiguration
# Vorgaben der VG (Tabelle vg_setting in der Zentrale), von denen eine Wehr abweichen kann: Eine Zeile in
# ihrer Tabelle setting ist eine Abweichung, ohne Zeile gilt der Wert der VG, ohne den der Standard.
# bks_code ist die Kennung der VG im BKS-Bericht (NR#.ABC in „FW NR#.ABC 02“).
INHERITED = ("bks_code", "control_center", "places", "plan_min_level", "response_limits", "default_limit",
             "second_limit", "day_hours", "numbering", "colors")
# Nur je Wehr: station ist die Standortnummer (02 in „FW NR#.ABC 02“). unit_prefix, own_prefix und unit_marker
# stehen nur bei älteren Einrichtungen, deren Präfixe sich nicht aus Kennung und Standort ergeben.
TENANT_ONLY = ("station", "plan_places", "substitutes", "response_plan_public", "unit_prefix", "own_prefix",
               "unit_marker")
_TUPLES = {"places", "plan_places", "response_limits", "day_hours"}
_DEFAULTS = {f.name: f.default_factory() if f.default_factory is not dataclasses.MISSING else f.default
             for f in dataclasses.fields(TenantConfig)}
_DEFAULTS["bks_code"] = None

_configs = {}
_configs_lock = threading.Lock()


def _same(a, b):
    """Gleicher Wert unabhängig von Tupel/Liste (JSON aus der Datenbank)."""
    return json.dumps(a, ensure_ascii=False, sort_keys=True) == json.dumps(b, ensure_ascii=False, sort_keys=True)


def _template_keywords():
    return [{"code": c, "name": n, "terms": t, "active": True} for c, n, t in domain.KEYWORD_CATALOG]


@dataclasses.dataclass(frozen=True)
class VgLayer:
    """Vorgaben einer VG für ihre Wehren: settings {Schlüssel aus INHERITED: Wert}, keywords [{code, name,
    terms, active}] oder None, solange die Vorlage aus domain.py gilt."""
    settings: dict = dataclasses.field(default_factory=dict)
    keywords: tuple = None

    def value(self, key):
        return self.settings.get(key, _DEFAULTS[key])

    @property
    def keyword_list(self):
        return [dict(k) for k in self.keywords] if self.keywords is not None else _template_keywords()


NO_LAYER = VgLayer()


def load_vg_layer(con, vg_id):
    """Vorgaben der VG aus der Zentrale (con)."""
    settings = {r["key"]: json.loads(r["value"])
                for r in con.execute("SELECT key, value FROM vg_setting WHERE vg_id = ?", (vg_id,))}
    rows = con.execute("SELECT code, name, terms, active FROM vg_keyword WHERE vg_id = ? ORDER BY sort_order, code",
                       (vg_id,)).fetchall()
    return VgLayer(settings, tuple({**dict(r), "active": bool(r["active"])} for r in rows) if rows else None)


def save_vg_settings(con, vg_id, values):
    """Vorgaben der VG speichern {Schlüssel aus INHERITED: Wert}; None bzw. der Standard löscht die Vorgabe."""
    for key, value in values.items():
        if key not in INHERITED:
            raise KeyError(key)
        if value is None or _same(value, _DEFAULTS[key]):
            con.execute("DELETE FROM vg_setting WHERE vg_id = ? AND key = ?", (vg_id, key))
        else:
            con.execute("INSERT INTO vg_setting (vg_id, key, value) VALUES (?, ?, ?) "
                        "ON CONFLICT(vg_id, key) DO UPDATE SET value = excluded.value",
                        (vg_id, key, json.dumps(value, ensure_ascii=False)))


def save_vg_keywords(con, vg_id, entries):
    """Stichwortkatalog der VG durch [{code, name, terms, active}] ersetzen; None = zurück zur Vorlage."""
    con.execute("DELETE FROM vg_keyword WHERE vg_id = ?", (vg_id,))
    con.executemany("INSERT INTO vg_keyword (vg_id, code, name, terms, active, sort_order) VALUES (?, ?, ?, ?, ?, ?)",
                    [(vg_id, k["code"], k["name"], k["terms"], int(k["active"]), i)
                     for i, k in enumerate(entries or [], 1)])


def _tenant_keyword_rows(con):
    return [{**dict(r), "active": bool(r["active"])}
            for r in con.execute("SELECT code, name, terms, active FROM keyword ORDER BY sort_order, code")]


def merge_keywords(inherited, rows):
    """Katalog einer Wehr: Stichworte der VG mit den Abweichungen der Wehr (eigene Bezeichnung, „gilt hier
    nicht“ = inaktiv), dahinter die eigenen Zusatz-Stichworte. Jeder Eintrag mit source vg/changed/own."""
    own = {r["code"]: r for r in rows}
    result = [{**own[k["code"]], "source": "changed"} if k["code"] in own else {**k, "source": "vg"}
              for k in inherited]
    known = {k["code"] for k in inherited}
    return result + [{**r, "source": "own"} for r in rows if r["code"] not in known]


def tenant_keywords(con, layer):
    """Wirksamer Stichwortkatalog einer Wehr (siehe merge_keywords)."""
    return merge_keywords(layer.keyword_list, _tenant_keyword_rows(con))


def save_tenant_keywords(con, desired, layer):
    """Katalog der Wehr so speichern, dass er wirksam desired [{code, name, terms, active}] ergibt: nur die
    Abweichungen von der VG. Stichworte der VG, die fehlen, gelten in der Wehr nicht (inaktiv)."""
    inherited = {k["code"]: k for k in layer.keyword_list}
    wanted = {k["code"]: k for k in desired}
    rows = []
    for k in desired:
        base = inherited.get(k["code"])
        if not base or (base["name"], base["terms"], bool(base["active"])) != (k["name"], k["terms"], bool(k["active"])):
            rows.append(k)
    rows += [{**k, "active": False} for code, k in inherited.items() if code not in wanted and k["active"]]
    con.execute("DELETE FROM keyword")
    con.executemany("INSERT INTO keyword (code, name, terms, active, sort_order) VALUES (?, ?, ?, ?, ?)",
                    [(k["code"], k["name"], k["terms"], int(k["active"]), i) for i, k in enumerate(rows, 1)])


def _setting_values(cfg):
    """Werte einer TenantConfig, wie sie gespeichert werden: Kennung und Standort statt der Präfixe, wenn sich
    diese daraus ergeben."""
    values = {key: getattr(cfg, key) for key in (*INHERITED, *TENANT_ONLY) if key not in ("bks_code", "station")}
    m = UNIT_MARKER.fullmatch(cfg.unit_marker.strip())
    if m and prefixes_of(cfg.unit_marker) == (cfg.unit_prefix, cfg.own_prefix):
        values.update(bks_code=m.group(1), station=m.group(2))
        for key in ("unit_prefix", "own_prefix", "unit_marker"):
            del values[key]
    for key in ("unit_prefix", "own_prefix", "unit_marker"):
        if not values.get(key, True):
            del values[key]
    return values


def _write_settings(con, values, layer):
    """Vorgaben der VG nur als Abweichung speichern, Werte der Wehr immer."""
    for key in INHERITED + TENANT_ONLY:
        value = values.get(key)
        if value is None or (key in INHERITED and _same(value, layer.value(key))):
            con.execute("DELETE FROM setting WHERE key = ?", (key,))
        else:
            con.execute("INSERT INTO setting (key, value) VALUES (?, ?) "
                        "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, json.dumps(value, ensure_ascii=False)))


def load_config(con, name, layer=NO_LAYER):
    """TenantConfig aus der Wehr-Datenbank und den Vorgaben ihrer VG (layer). Fehlende Werte nehmen die
    Standardwerte, ein fehlender Stichwortkatalog die Vorlage aus domain.py."""
    own = {r["key"]: json.loads(r["value"]) for r in con.execute("SELECT key, value FROM setting")}
    values = {**layer.settings, **{k: v for k, v in own.items() if k in INHERITED or k in TENANT_ONLY}}
    code, station = values.pop("bks_code", None), values.pop("station", None)
    if code and station:
        values["unit_marker"] = f"FW {code} {station}"
        values["unit_prefix"], values["own_prefix"] = prefixes_of(values["unit_marker"])
    elif code and not values.get("unit_prefix"):
        values["unit_prefix"] = f"FL {code} "         # ohne Standort: Fahrzeuge der VG erkennbar
    for key in _TUPLES & set(values):
        values[key] = tuple(tuple(v) if isinstance(v, list) else v for v in values[key])
    if "places" in values:                     # früher (Name, Namensanfang)
        values["places"] = tuple(p[0] if isinstance(p, tuple) else p for p in values["places"])
    fleet = tuple(Vehicle(r["call_sign"], r["label"], r["in_service_from"], r["in_service_until"], r["replaced_by"],
                          bool(r["in_plan_crew"]), r["name"])
                  for r in con.execute("SELECT * FROM fleet ORDER BY sort_order, call_sign"))
    catalog = tenant_keywords(con, layer)
    keywords = tuple((k["code"], k["name"], k["terms"]) for k in catalog if k["active"])
    inactive = tuple((k["code"], k["name"], k["terms"]) for k in catalog if not k["active"])
    return TenantConfig(name=name, fleet=fleet, keywords=keywords, inactive_keywords=inactive, **values)


def prune_overrides(con, layer):
    """Abweichungen löschen, die (nach einer Änderung der VG) der Vorgabe entsprechen."""
    for key, value in [(r[0], json.loads(r[1])) for r in con.execute("SELECT key, value FROM setting")]:
        if key in INHERITED and _same(value, layer.value(key)):
            con.execute("DELETE FROM setting WHERE key = ?", (key,))


def save_tenant_values(con, values):
    """Werte nur der Wehr (TENANT_ONLY) setzen; None löscht. Mit Standort gelten die alten Präfixe nicht mehr."""
    for key, value in values.items():
        if key not in TENANT_ONLY:
            raise KeyError(key)
        if value is None:
            con.execute("DELETE FROM setting WHERE key = ?", (key,))
        else:
            con.execute("INSERT INTO setting (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET "
                        "value = excluded.value", (key, json.dumps(value, ensure_ascii=False)))
    if values.get("station"):
        con.execute("DELETE FROM setting WHERE key IN ('unit_prefix', 'own_prefix', 'unit_marker')")


def config_sources(con):
    """Schlüssel aus INHERITED, in denen die Wehr von der VG abweicht."""
    return {r[0] for r in con.execute("SELECT key FROM setting")} & set(INHERITED)


def fleet_version(con):
    """Stand der Fahrzeugliste: Einstellungen, die auf einem älteren Stand bearbeitet wurden, würden Fahrzeuge
    überschreiben, die inzwischen (Import, Fahrzeuge der VG) dazugekommen sind."""
    rows = [tuple(r) for r in con.execute("SELECT * FROM fleet ORDER BY sort_order, call_sign")]
    return hashlib.sha1(json.dumps(rows, ensure_ascii=False).encode()).hexdigest()[:16]


def save_config(con, cfg, layer=NO_LAYER, keywords=False):
    """Fachkonfiguration und Fahrzeuge speichern – Vorgaben der VG (layer) nur, wo die Wehr abweicht; den
    Stichwortkatalog nur mit keywords=True."""
    _write_settings(con, _setting_values(cfg), layer)
    con.execute("DELETE FROM fleet")
    for order, v in enumerate(cfg.fleet, start=1):
        con.execute("INSERT INTO fleet (call_sign, name, label, sort_order, in_service_from, in_service_until, "
                    "replaced_by, in_plan_crew) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (v.call_sign, v.name, v.label, order, v.in_service_from, v.in_service_until, v.replaced_by,
                     int(v.in_plan_crew)))
    if keywords:
        save_tenant_keywords(con, [{"code": c, "name": n, "terms": t, "active": True} for c, n, t in cfg.keywords] +
                             [{"code": c, "name": n, "terms": t, "active": False} for c, n, t in cfg.inactive_keywords],
                             layer)


# ---------------------------------------------------------------- Übernahme in die Vorgaben der VG
def _majority(values):
    """Häufigster Wert; bei Gleichstand der zuerst genannte."""
    counts = []
    for v in values:
        for entry in counts:
            if _same(entry[0], v):
                entry[1] += 1
                break
        else:
            counts.append([v, 1])
    return max(counts, key=lambda e: e[1])[0] if counts else None


def lift_vg_defaults():
    """Einmalig je VG: was ihre Wehren bisher einzeln gespeichert haben, wird Vorgabe der VG – je Wert der
    häufigste unter den eingerichteten Wehren. Diese behalten jeden Wert genau so (anderer Wert = Abweichung).
    Wehren, die noch nichts eingestellt haben (alles Standard), übernehmen künftig die Vorgaben."""
    with central() as con:
        vgs = [r[0] for r in con.execute("SELECT id FROM vg WHERE NOT defaults_lifted")]
    for vg_id in vgs:
        with central() as con:
            rows = con.execute("SELECT slug, name FROM tenant WHERE vg_id = ? AND slug NOT IN "
                               "(SELECT slug FROM tenant_archive) ORDER BY name", (vg_id,)).fetchall()
        tenants = []
        for r in rows:
            with db.connection(tenant_path(r["slug"])) as con:
                tenants.append((r["slug"], load_config(con, r["name"]), _tenant_keyword_rows(con)))
        values = {slug: _setting_values(cfg) for slug, cfg, _ in tenants}
        configured = [slug for slug, v in values.items()
                      if any(not _same(v.get(key), _DEFAULTS[key]) for key in INHERITED)]
        settings = {key: _majority([values[slug].get(key) for slug in configured]) for key in INHERITED}
        settings = {key: v for key, v in settings.items() if v is not None and not _same(v, _DEFAULTS[key])}
        catalogs = [kw for _, _, kw in tenants if kw]
        keywords = None
        if catalogs:
            codes = list(dict.fromkeys(k["code"] for kw in catalogs for k in kw))
            keywords = []
            for code in codes:
                entries = [k for kw in catalogs for k in kw if k["code"] == code]
                if 2 * len(entries) >= len(catalogs):
                    keywords.append(_majority([{key: k[key] for key in ("code", "name", "terms", "active")}
                                               for k in entries]))
        layer = VgLayer(settings, tuple(keywords) if keywords is not None else None)
        with central() as con:
            save_vg_settings(con, vg_id, settings)
            save_vg_keywords(con, vg_id, keywords)
            for slug, cfg, kw in tenants:
                own = values[slug]
                if slug not in configured:         # nichts eingestellt: künftig die Vorgaben
                    own = {key: v for key, v in own.items() if key not in INHERITED}
                elif "bks_code" not in own:        # ohne Kennung bisher: nicht die der VG erben
                    own["bks_code"] = ""
                with db.connection(tenant_path(slug)) as tenant_con:
                    _write_settings(tenant_con, own, layer)
                    if kw:                         # bisher: eigener Katalog vollständig in der Wehr
                        save_tenant_keywords(tenant_con, kw, layer)
                    else:
                        tenant_con.execute("DELETE FROM keyword")
                forget_config(slug)
            con.execute("UPDATE vg SET defaults_lifted = 1 WHERE id = ?", (vg_id,))
        log.info("Vorgaben der VG %s aus %d Wehren übernommen: %s", vg_id, len(tenants), ", ".join(settings) or "keine")


def forget_config(slug):
    """Nach dem Speichern: Konfiguration beim nächsten Zugriff neu laden."""
    with _configs_lock:
        _configs.pop(slug, None)


def forget_vg_config(vg_id):
    """Nach dem Ändern der Vorgaben einer VG: Konfiguration aller ihrer Wehren neu laden."""
    with central() as con:
        slugs = [r[0] for r in con.execute("SELECT slug FROM tenant WHERE vg_id = ?", (vg_id,))]
    for slug in slugs:
        forget_config(slug)


# ---------------------------------------------------------------- Verbandsgemeinden, Wehren, Zuordnungen
def check_slug(slug):
    if not SLUG.fullmatch(slug or ""):
        raise ValueError("Kurzname: nur Kleinbuchstaben, Ziffern und Bindestrich (2–40 Zeichen).")
    return slug


def suggest_slug(con, name, vg_slug=""):
    """Freier Kurzname für eine Wehr aus ihrem Namen („Feuerwehr Altenau“ → altenau). Kurznamen gelten für alle
    VGs gemeinsam (Ordner, Cookie, Einsatz-IDs); ist er vergeben – gleicher Ortsname in einer anderen VG –, hängt
    die VG an (altenau-musterstadt), danach eine Nummer."""
    text = (name or "").lower()
    for old, new in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        text = text.replace(old, new)
    words = [w for w in re.sub(r"[^a-z0-9]+", " ", text).split()
             if w not in ("feuerwehr", "freiwillige", "ff", "wehr", "der", "von")]
    base = "-".join(words)[:30].strip("-") or "wehr"
    vg_part = re.sub(r"^vg-?", "", vg_slug or "")[:8].strip("-")
    candidates = [base] + ([f"{base}-{vg_part}"] if vg_part else [])
    candidates += [f"{base}-{n}" for n in range(2, 100)]
    for candidate in candidates:
        if (SLUG.fullmatch(candidate) and not con.execute("SELECT 1 FROM tenant WHERE slug = ?", (candidate,)).fetchone()
                and not os.path.exists(tenant_path(candidate))):
            return candidate
    raise ValueError("Kein freier Kurzname gefunden – bitte einen eigenen eintragen.")


def create_vg(con, slug, name, kind="vg"):
    """Neue VG (Aufgabenträger der Art kind, siehe rbac.KINDS): ohne Wehren gibt es nichts in ihre Vorgaben
    zu übernehmen (defaults_lifted)."""
    if kind not in rbac.KINDS:
        raise ValueError("Unbekannte Art des Aufgabenträgers.")
    return con.execute("INSERT INTO vg (slug, name, defaults_lifted, kind) VALUES (?, ?, 1, ?)",
                       (check_slug(slug), name.strip(), kind)).lastrowid


def set_vg_kind(con, vg_id, kind):
    """Art einer VG ändern – nur, wenn keine Zuordnung der VG (und ihrer Wehren) eine Rolle nutzt, die zur neuen
    Art nicht passt."""
    if kind not in rbac.KINDS:
        raise ValueError("Unbekannte Art des Aufgabenträgers.")
    roles = rbac.Roles(con)
    used = {r[0] for r in con.execute(
        "SELECT m.role_id FROM membership m LEFT JOIN tenant t ON m.scope = 'tenant' AND t.id = m.scope_id "
        "WHERE (m.scope = 'vg' AND m.scope_id = ?) OR (m.scope = 'tenant' AND t.vg_id = ?)", (vg_id, vg_id))}
    unfit = sorted({roles.get(i).label for i in used if roles.get(i) and not roles.get(i).fits(kind)})
    if unfit:
        raise ValueError(f"Nicht möglich: diese Rollen sind zugeordnet und gelten dort nicht: {', '.join(unfit)}.")
    con.execute("UPDATE vg SET kind = ? WHERE id = ?", (kind, vg_id))


def create_tenant(con, slug, name, vg_id, cfg=None):
    """Wehr anlegen: Eintrag in der Zentrale, eigene Datenbank. Ohne cfg übernimmt sie alle Vorgaben der VG,
    mit cfg werden abweichende Werte als Abweichung gespeichert."""
    check_slug(slug)
    path = tenant_path(slug)
    if os.path.exists(path):
        raise ValueError(f"Für „{slug}“ gibt es schon eine Datenbank.")
    # IDs gelöschter Wehren nicht wiederverwenden: das Rollen-Protokoll verweist weiter auf sie
    tenant_id = con.execute("SELECT MAX(id) FROM (SELECT MAX(id) AS id FROM tenant "
                            "UNION ALL SELECT MAX(tenant_id) FROM role_event)").fetchone()[0] or 0
    tenant_id = con.execute("INSERT INTO tenant (id, slug, name, vg_id) VALUES (?, ?, ?, ?)",
                            (tenant_id + 1, slug, name.strip(), vg_id)).lastrowid
    from app.tenant_lifecycle import CREATE_MARKER
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=False)
    with open(os.path.join(directory, CREATE_MARKER), "x") as marker:
        marker.write(slug)
        marker.flush()
        os.fsync(marker.fileno())
    db.setup(path)
    with db.connection(path) as tenant_con:
        if cfg:
            save_config(tenant_con, cfg, load_vg_layer(con, vg_id))
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
    def layer(self):
        """Vorgaben der VG dieser Wehr."""
        with central() as con:
            return load_vg_layer(con, self.vg_id)

    @property
    def config(self):
        with _configs_lock:
            cfg = _configs.get(self.slug)
        if cfg is None or cfg.name != self.name:
            layer = self.layer
            with db.connection(self.db_path) as con:
                cfg = load_config(con, self.name, layer)
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
    vg_kinds: dict = dataclasses.field(default_factory=dict)   # slug -> Art (rbac.KINDS) der VGs mit Gesamtansicht
    vg_permissions: dict = dataclasses.field(default_factory=dict)   # VG-ID -> Rechte aus Rollen der VG
    selected: Tenant = None
    vg: str = None             # Slug der ausgewählten VG
    blocked: list = dataclasses.field(default_factory=list)   # [{slug, name}] VGs, deren Wehren der AVV fehlt
    blocked_ids: frozenset = frozenset()                       # IDs dieser VGs

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
        if vg_id in self.blocked_ids:
            return set()
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
        """Auswahlmöglichkeiten für die Kopfzeile: je VG die Verbandsgemeinde (Gesamtansicht aller Wehren), dann die Wehren."""
        result = []
        for vg_slug, vg_name in self.vgs.items():
            kind = rbac.KINDS.get(self.vg_kinds.get(vg_slug), "Verbandsgemeinde").split(" /")[0]
            result.append({"key": f"vg:{vg_slug}", "name": f"{kind} · {vg_name}", "vg": vg_name})
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
        vg_names = {r[0]: (r[1], r[2]) for r in con.execute("SELECT id, slug, name FROM vg")}
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
    if not superadmin:                         # auch die Rechte auf Ebene der VG ruhen bis zum AVV
        for vg_id in [vg_id for vg_id in vg_permissions if vg_id not in signed]:
            del vg_permissions[vg_id]
            blocked.setdefault(*vg_names[vg_id])
    blocked_ids = frozenset(vg_id for vg_id, (slug, _) in vg_names.items() if slug in blocked)
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
    vg_kinds = {slug: roles.vg_kind.get(vg_id) for vg_id, (slug, _) in vg_names.items() if slug in vgs}
    access = Access(email, superadmin, tenants, own, vgs, vg_kinds, {k: frozenset(v) for k, v in vg_permissions.items()},
                    blocked=[{"slug": slug, "name": name} for slug, name in blocked.items()], blocked_ids=blocked_ids)
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
