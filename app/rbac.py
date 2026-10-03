# -*- coding: utf-8 -*-
"""
Rollen und Rechte (RBAC).

Die Rechte stehen fest im Code (PERMISSIONS), die Rollen in der Zentral-DB:
  role             Rolle eines Bereichs ('vg' oder 'tenant'); vg_id NULL = in allen VGs (System- und globale
                   Rollen, gepflegt vom Superadmin), sonst eigene Rolle dieser VG (gepflegt mit ROLES_MANAGE)
  role_permission  eigene Rechte einer Rolle
  role_grant       Verteilung: wer role_id hat (und USERS_GRANT), darf grantable_role_id vergeben
  role_event       Protokoll der Vergaben und Rollenänderungen, nur anhängbar

Vererbung: eine VG-Rolle gilt in allen Wehren der VG; eine Rolle mit parent_id erbt Rechte und Verteilung
ihres Elternteils (gleicher Bereich, keine Zyklen). Mehrere Rollen je Person und Bereich addieren sich.

Leitplanken (nicht konfigurierbar): Anwesenheit und Kameraden (PEOPLE*) gibt es nur für Rollen einer Wehr –
der Wehrleiter sieht keine Namen. Eigene Zuordnungen und Rollen, die man selbst (auch über Vererbung) hat,
ändert nur jemand anderes. Superadmins (ADMIN_EMAILS) stehen außerhalb und dürfen alles.
"""
import dataclasses
import re
import unicodedata

# ---------------------------------------------------------------- Rechte
STATS = "stats.view"
PLAN_VIEW = "plan.view"
PLAN_RELEASE = "plan.release"
INCIDENTS = "incidents.view"
EXPORT = "incidents.export"
IMPORT = "reports.import"
WRITE = "incidents.edit"
DELETE = "incidents.delete"
PEOPLE = "people.view"
PEOPLE_EDIT = "people.edit"
SETTINGS = "tenant.settings"
KEYWORDS = "tenant.keywords"
VG_OVERVIEW = "vg.overview"
VG_RECORDS = "vg.records"
VG_FEES = "vg.fees"
DPA_VIEW = "dpa.view"
DPA_EDIT = "dpa.edit"
USERS_VIEW = "users.view"
USERS_GRANT = "users.grant"
ROLES_MANAGE = "roles.manage"

BOTH, VG, TENANT = ("vg", "tenant"), ("vg",), ("tenant",)


@dataclasses.dataclass(frozen=True)
class Permission:
    key: str
    group: str
    label: str
    scopes: tuple            # Bereiche, für deren Rollen das Recht zulässig ist
    requires: tuple = ()     # wird beim Speichern einer Rolle mit gesetzt


PERMISSIONS = {p.key: p for p in (
    Permission(STATS, "Auswertung", "Auswertung ansehen", BOTH),
    Permission(PLAN_VIEW, "Auswertung", "Bedarfsplan ohne Freigabe sehen", BOTH, (STATS,)),
    Permission(PLAN_RELEASE, "Auswertung", "Bedarfsplan freigeben", BOTH, (PLAN_VIEW,)),
    Permission(INCIDENTS, "Einsätze", "Einsätze ansehen", BOTH, (STATS,)),
    Permission(EXPORT, "Einsätze", "Excel-Export", BOTH, (INCIDENTS,)),
    Permission(IMPORT, "Einsätze", "Berichte einlesen", BOTH, (INCIDENTS,)),
    Permission(WRITE, "Einsätze", "Einsätze bearbeiten", BOTH, (INCIDENTS,)),
    Permission(DELETE, "Einsätze", "Einsätze löschen", BOTH, (WRITE,)),
    Permission(PEOPLE, "Personen", "Anwesenheit und Kameraden sehen", TENANT, (INCIDENTS,)),
    Permission(PEOPLE_EDIT, "Personen", "Anwesenheit bearbeiten", TENANT, (PEOPLE, WRITE)),
    Permission(SETTINGS, "Wehr", "Einstellungen, Fahrzeuge, Farben und Logos", BOTH),
    Permission(KEYWORDS, "Wehr", "Stichwortkatalog", BOTH),
    Permission(VG_OVERVIEW, "Verbandsgemeinde", "Gesamtansicht der VG", VG, (STATS,)),
    Permission(VG_RECORDS, "Verbandsgemeinde", "Prüfprotokoll und Kostenersatz", VG, (VG_OVERVIEW, INCIDENTS)),
    Permission(VG_FEES, "Verbandsgemeinde", "Gebührenordnung der VG", VG),
    Permission(DPA_VIEW, "Verbandsgemeinde", "Auftragsverarbeitung ansehen", BOTH),
    Permission(DPA_EDIT, "Verbandsgemeinde", "Auftragsverarbeitung ausfüllen", BOTH, (DPA_VIEW,)),
    Permission(USERS_VIEW, "Benutzer", "Zuordnungen sehen", BOTH),
    Permission(USERS_GRANT, "Benutzer", "Rollen vergeben", BOTH, (USERS_VIEW,)),
    Permission(ROLES_MANAGE, "Benutzer", "Rollen der VG anlegen und ändern", VG, (USERS_VIEW,)),
)}
ALL_PERMISSIONS = frozenset(PERMISSIONS)

# Startbestand beim Einführen des RBAC (Migration): (Schlüssel, Bereich, Bezeichnung, erbt von, Rechte, vergibt)
# Entspricht den früher fest verdrahteten Rollen; danach gelten die Rollen in der Datenbank.
SYSTEM_ROLES = (
    ("viewer", "tenant", "Benutzer", None, {STATS, DPA_VIEW}, ()),
    ("editor", "tenant", "Erfasser", "viewer", {INCIDENTS, EXPORT, IMPORT, WRITE, DELETE, PEOPLE, PEOPLE_EDIT}, ()),
    ("lead", "tenant", "Wehrführer", "editor",
     {PLAN_VIEW, PLAN_RELEASE, SETTINGS, KEYWORDS, USERS_VIEW, USERS_GRANT, DPA_EDIT}, ("editor", "viewer")),
    ("vg_stats", "vg", "Statistik VG", None, {STATS, VG_OVERVIEW, DPA_VIEW, DPA_EDIT}, ()),
    ("vg_lead", "vg", "Wehrleiter", "vg_stats",
     {PLAN_VIEW, PLAN_RELEASE, INCIDENTS, EXPORT, IMPORT, WRITE, DELETE, SETTINGS, KEYWORDS, VG_RECORDS, VG_FEES,
      USERS_VIEW, USERS_GRANT, ROLES_MANAGE}, ("vg_lead", "vg_stats", "lead", "editor", "viewer")),
)
SCOPES = {"vg": "VG", "tenant": "Wehr"}


class Invalid(ValueError):
    """Ungültige Rolle oder Vergabe (wird zu 422)."""


def close(permissions):
    """Rechte samt allen vorausgesetzten Rechten."""
    result, todo = set(), list(permissions)
    while todo:
        key = todo.pop()
        if key not in result and key in PERMISSIONS:
            result.add(key)
            todo += PERMISSIONS[key].requires
    return result


def allowed(permissions, scope):
    """Nur die Rechte, die für Rollen dieses Bereichs zulässig sind (Leitplanke PEOPLE nur für Wehr-Rollen)."""
    return {p for p in permissions if p in PERMISSIONS and scope in PERMISSIONS[p].scopes}


# ---------------------------------------------------------------- Rollen
@dataclasses.dataclass
class Role:
    id: int
    key: str
    vg_id: int
    scope: str
    label: str
    description: str
    parent_id: int
    system: bool
    own: frozenset           # eigene Rechte
    own_grants: frozenset    # Rollen-IDs, die Inhaber vergeben dürfen (ohne Vererbung)


class Roles:
    """Alle Rollen mit Rechten und Verteilung, einmal je Anfrage geladen (wenige Zeilen)."""

    def __init__(self, con):
        perms, grants = {}, {}
        for r in con.execute("SELECT role_id, permission FROM role_permission"):
            perms.setdefault(r[0], set()).add(r[1])
        for r in con.execute("SELECT role_id, grantable_role_id FROM role_grant"):
            grants.setdefault(r[0], set()).add(r[1])
        self.by_id = {r["id"]: Role(r["id"], r["key"], r["vg_id"], r["scope"], r["label"], r["description"],
                                    r["parent_id"], bool(r["system"]), frozenset(perms.get(r["id"], ())),
                                    frozenset(grants.get(r["id"], ())))
                      for r in con.execute("SELECT * FROM role ORDER BY system DESC, scope DESC, id")}

    def __iter__(self):
        return iter(self.by_id.values())

    def get(self, role_id):
        return self.by_id.get(role_id)

    def chain(self, role_id):
        """Die Rolle und ihre Vorfahren (Abbruch bei einem Zyklus)."""
        seen = []
        while role_id in self.by_id and role_id not in seen:
            seen.append(role_id)
            role_id = self.by_id[role_id].parent_id
        return seen

    def permissions(self, role_id):
        role = self.by_id.get(role_id)
        if not role:
            return frozenset()
        # Voraussetzungen über die ganze Kette: gespeichert ist nur, was die Elternrolle beim Speichern nicht
        # schon hatte – verliert sie später ein Recht, bleibt es für die erbende Rolle, die es voraussetzt
        return frozenset(allowed(close(set().union(*(self.by_id[i].own for i in self.chain(role_id)))), role.scope))

    def grants(self, role_id):
        """Vergebbare Rollen – nur mit USERS_GRANT."""
        if USERS_GRANT not in self.permissions(role_id):
            return frozenset()
        return frozenset().union(*(self.by_id[i].own_grants for i in self.chain(role_id)))

    def visible(self, vg_id):
        """Rollen, die in einer VG gelten: System- und globale Rollen sowie die eigenen der VG."""
        return [r for r in self if r.vg_id is None or r.vg_id == vg_id]

    def find(self, key, vg_id):
        return next((r for r in self.visible(vg_id) if r.key == key), None)

    def descendants(self, role_id):
        return [r for r in self if r.id != role_id and role_id in self.chain(r.id)]


def make_key(con, label, vg_id):
    """Schlüssel aus der Bezeichnung, eindeutig unter den Rollen, die in derselben VG gelten können."""
    text = label.lower()
    for umlaut, ascii_ in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        text = text.replace(umlaut, ascii_)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-z0-9]+", "_", text).strip("_")[:30] or "rolle"
    taken = {r[0] for r in con.execute("SELECT key FROM role WHERE vg_id IS NULL OR ? IS NULL OR vg_id = ?",
                                       (vg_id, vg_id))}
    key, n = base, 1
    while key in taken:
        n += 1
        key = f"{base}_{n}"
    return key


def seed(con):
    """Startbestand der Rollen (Migration)."""
    ids, effective = {}, {}
    for key, scope, label, parent, permissions, _ in SYSTEM_ROLES:
        ids[key] = con.execute("INSERT INTO role (key, scope, label, parent_id, system) VALUES (?, ?, ?, ?, 1)",
                               (key, scope, label, ids.get(parent))).lastrowid
        inherited = effective.get(parent, set())
        effective[key] = inherited | close(permissions)
        con.executemany("INSERT INTO role_permission (role_id, permission) VALUES (?, ?)",
                        [(ids[key], p) for p in sorted(close(permissions) - inherited)])
    for key, *_, grants in SYSTEM_ROLES:
        con.executemany("INSERT INTO role_grant (role_id, grantable_role_id) VALUES (?, ?)",
                        [(ids[key], ids[g]) for g in grants])
    return ids


def save_role(con, roles, role_id, *, vg_id, scope, label, description, parent_id, permissions, granted_by, grants):
    """Rolle anlegen (role_id None) oder ändern -> ID. Prüft Bereich, Elternrolle, Rechte und Verteilung:
    granted_by = Rollen, die diese Rolle vergeben dürfen; grants = Rollen, die Inhaber dieser Rolle vergeben."""
    label = (label or "").strip()
    if not 2 <= len(label) <= 60:
        raise Invalid("Die Bezeichnung braucht 2 bis 60 Zeichen.")
    if scope not in SCOPES:
        raise Invalid("Bereich: VG oder Wehr.")
    unknown = set(permissions) - ALL_PERMISSIONS
    if unknown:
        raise Invalid(f"Unbekanntes Recht: {', '.join(sorted(unknown))}.")
    if set(permissions) - set(allowed(permissions, scope)):
        raise Invalid("Anwesenheit und Kameraden gibt es nur für Rollen einer Wehr; "
                      "Gesamtansicht, Prüfprotokoll, Gebühren und Rollenpflege nur für Rollen der VG.")
    if parent_id is not None:
        parent = roles.get(parent_id)
        if not parent or parent.scope != scope or (parent.vg_id is not None and parent.vg_id != vg_id):
            raise Invalid("Erben geht nur von einer Rolle desselben Bereichs, die in dieser VG gilt.")
        if role_id is not None and role_id in roles.chain(parent_id):
            raise Invalid("Eine Rolle kann nicht von sich selbst erben (auch nicht über Umwege).")
    granters, grantable = [roles.get(g) for g in granted_by], [roles.get(g) for g in grants]
    if any(g is None or (g.vg_id is not None and g.vg_id != vg_id) for g in granters + grantable):
        raise Invalid("Bei der Verteilung gehen nur Rollen, die in dieser VG gelten.")
    if vg_id is None and any(g.vg_id is not None for g in granters + grantable):
        raise Invalid("Globale Rollen verteilen nur globale Rollen.")
    if role_id is None:
        role_id = con.execute("INSERT INTO role (key, vg_id, scope, label, description, parent_id) "
                              "VALUES (?, ?, ?, ?, ?, ?)", (make_key(con, label, vg_id), vg_id, scope, label,
                                                            description or "", parent_id)).lastrowid
    else:
        con.execute("UPDATE role SET label = ?, description = ?, parent_id = ? WHERE id = ?",
                    (label, description or "", parent_id, role_id))
        con.execute("DELETE FROM role_permission WHERE role_id = ?", (role_id,))
        # Verteilung neu setzen; bei globalen Rollen nur gegenüber globalen – Einträge eigener VG-Rollen bleiben
        other = "" if vg_id is not None else " AND {} IN (SELECT id FROM role WHERE vg_id IS NULL)"
        con.execute("DELETE FROM role_grant WHERE grantable_role_id = ?" + other.format("role_id"), (role_id,))
        con.execute("DELETE FROM role_grant WHERE role_id = ?" + other.format("grantable_role_id"), (role_id,))
    # Eigene Rechte samt Voraussetzungen, ohne das, was schon geerbt ist
    inherited = roles.permissions(parent_id) if parent_id is not None else frozenset()
    con.executemany("INSERT INTO role_permission (role_id, permission) VALUES (?, ?)",
                    [(role_id, p) for p in sorted(allowed(close(permissions), scope) - inherited)])
    con.executemany("INSERT INTO role_grant (role_id, grantable_role_id) VALUES (?, ?)",
                    sorted({(g.id, role_id) for g in granters} | {(role_id, g.id) for g in grantable}))
    return role_id


def delete_role(con, roles, role_id):
    role = roles.get(role_id)
    if role.system:
        raise Invalid("Systemrollen lassen sich nicht löschen.")
    members = con.execute("SELECT COUNT(*) FROM membership WHERE role_id = ?", (role_id,)).fetchone()[0]
    children = [r.label for r in roles if r.parent_id == role_id]
    if members or children:
        reasons = ([f"{members} Zuordnung(en)"] if members else []) + \
                  ([f"erbende Rollen: {', '.join(children)}"] if children else [])
        raise Invalid(f"„{role.label}“ wird noch genutzt ({'; '.join(reasons)}).")
    con.execute("DELETE FROM role WHERE id = ?", (role_id,))


# ---------------------------------------------------------------- Protokoll
def log(con, email, action, detail="", vg_id=None, tenant_id=None):
    con.execute("INSERT INTO role_event (email, vg_id, tenant_id, action, detail) VALUES (?, ?, ?, ?, ?)",
                (email or "lokal", vg_id, tenant_id, action, detail))


def member_permissions(con, email, vg_id):
    """Rechte einer Adresse aus allen Zuordnungen in einer VG (VG und ihre Wehren) – auch wenn die VG
    gesperrt ist (Auftragsverarbeitung)."""
    roles = Roles(con)
    rows = con.execute(
        "SELECT m.role_id FROM membership m LEFT JOIN tenant t ON m.scope = 'tenant' AND t.id = m.scope_id "
        "WHERE m.email = ? AND ((m.scope = 'vg' AND m.scope_id = ?) OR (m.scope = 'tenant' AND t.vg_id = ?))",
        (email, vg_id, vg_id)).fetchall()
    return set().union(*(roles.permissions(r[0]) for r in rows)) if rows else set()
