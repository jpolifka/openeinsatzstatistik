# -*- coding: utf-8 -*-
"""Verwaltung: Zuordnungen von Personen zu Rollen und Bereichen, Protokoll.
"""
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app import rbac, tenancy
from app.rbac import USERS_VIEW

from app.admin.common import _invalid, access, log

router = APIRouter()


# ---------------------------------------------------------------- Benutzer und Rollen
def _scope_row(con, scope, slug):
    """(scope_id, vg_id, name) eines Bereichs; 404, wenn es ihn nicht gibt."""
    if scope == "tenant":
        row = con.execute("SELECT id, vg_id, name FROM tenant WHERE slug = ?", (slug,)).fetchone()
    elif scope == "vg":
        row = con.execute("SELECT id, id AS vg_id, name FROM vg WHERE slug = ?", (slug,)).fetchone()
    else:
        row = None
    if not row:
        raise HTTPException(404, "Wehr bzw. VG nicht gefunden.")
    return row["id"], row["vg_id"], row["name"]


def _sees_users(a, scope, scope_id, vg_id):
    """Darf die Zuordnungen dieses Bereichs sehen: Superadmin, USERS_VIEW in der VG oder in dieser Wehr."""
    if a.vg_can(vg_id, USERS_VIEW):
        return True
    return scope == "tenant" and any(t.id == scope_id and t.can(USERS_VIEW) for t in a.tenants.values())


def _not_self(a, email):
    if email == a.email and not a.superadmin:
        raise tenancy.Forbidden("Eigene Zuordnungen ändert jemand anderes (Wehrleiter oder Superadmin) – "
                                "nicht man selbst.")


def _areas(con):
    """Alle Bereiche zum Vergeben: VGs, dann ihre aktiven Wehren -> [(scope, id, vg_id, slug, Bezeichnung)]."""
    result = []
    for v in con.execute("SELECT id, slug, name FROM vg ORDER BY name").fetchall():
        result.append(("vg", v["id"], v["id"], v["slug"], f"{v['name']} (alle Wehren)"))
        result += [("tenant", t["id"], v["id"], t["slug"], t["name"]) for t in con.execute(
            "SELECT id, slug, name FROM tenant WHERE vg_id = ? AND active ORDER BY name", (v["id"],))]
    return result


@router.get("/api/admin/memberships")
def get_memberships(a: tenancy.Access = Depends(access)):
    """Zuordnungen in allen Bereichen, die der Benutzer sehen oder vergeben darf, und je Bereich die
    Rollen, die er dort vergeben darf."""
    with tenancy.central() as con:
        roles = rbac.Roles(con)
        rows = con.execute(
            "SELECT m.email, m.scope, m.scope_id, m.role_id, COALESCE(t.slug, v.slug) AS slug, "
            "COALESCE(t.name, v.name) AS name, COALESCE(t.vg_id, v.id) AS vg_id, a.last_login, "
            "(SELECT slug FROM vg WHERE id = COALESCE(t.vg_id, v.id)) AS vg_slug "
            "FROM membership m JOIN account a ON a.email = m.email "
            "LEFT JOIN tenant t ON m.scope = 'tenant' AND t.id = m.scope_id "
            "LEFT JOIN vg v ON m.scope = 'vg' AND v.id = m.scope_id ORDER BY name, m.email").fetchall()
        areas = _areas(con)
    grantable = {}

    def granted(scope, scope_id, vg_id):
        if (scope, scope_id) not in grantable:
            grantable[scope, scope_id] = a.grantable(roles, scope, scope_id, vg_id)
        return grantable[scope, scope_id]

    result = []
    for r in rows:
        role = roles.get(r["role_id"])
        allowed = granted(r["scope"], r["scope_id"], r["vg_id"])
        if role and (allowed or _sees_users(a, r["scope"], r["scope_id"], r["vg_id"])):
            result.append({"email": r["email"], "scope": r["scope"], "slug": r["slug"], "name": r["name"],
                           "role": role.key, "label": role.label, "last_login": r["last_login"], "vg": r["vg_slug"],
                           "editable": role.id in allowed and (r["email"] != a.email or a.superadmin)})
    scopes = []
    for scope, scope_id, vg_id, slug, label in areas:
        ids = granted(scope, scope_id, vg_id)
        if ids:
            scopes.append({"key": f"{scope}:{slug}", "label": label,
                           "roles": [{"key": r.key, "label": r.label} for r in roles.visible(vg_id) if r.id in ids]})
    return {"memberships": result, "scopes": scopes}


class MembershipIn(BaseModel):
    email: str
    scope: str            # 'tenant' oder 'vg'
    slug: str
    role: str             # Schlüssel der Rolle


@router.post("/api/admin/memberships")
def grant_membership(m: MembershipIn, a: tenancy.Access = Depends(access)):
    """Rolle zuordnen (zusätzlich zu vorhandenen Rollen im selben Bereich)."""
    email = tenancy.normalize_email(m.email)
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        _invalid("Bitte eine gültige E-Mail-Adresse angeben.")
    with tenancy.central() as con:
        scope_id, vg_id, name = _scope_row(con, m.scope, m.slug)
        roles = rbac.Roles(con)
        role = roles.find(m.role, vg_id)
        if not role or role.scope != m.scope:
            _invalid("Diese Rolle passt nicht zum Bereich.")
        _not_self(a, email)
        if role.id not in a.grantable(roles, m.scope, scope_id, vg_id):
            raise tenancy.Forbidden("Diese Rolle darfst du hier nicht vergeben.")
        tenancy.add_account(con, email)
        con.execute("INSERT OR IGNORE INTO membership (email, scope, scope_id, role_id) VALUES (?, ?, ?, ?)",
                    (email, m.scope, scope_id, role.id))
        rbac.log(con, a.email, "Rolle vergeben", f"{role.label} für {email} in {name}", vg_id,
                 scope_id if m.scope == "tenant" else None)
    log.info("Rolle %s für %s in %s %s vergeben durch %s", role.key, email, m.scope, m.slug, a.email or "lokal")
    return get_memberships(a)


@router.delete("/api/admin/memberships")
def revoke_membership(email: str, scope: str, slug: str, role: str, a: tenancy.Access = Depends(access)):
    email = tenancy.normalize_email(email)
    with tenancy.central() as con:
        scope_id, vg_id, name = _scope_row(con, scope, slug)
        roles = rbac.Roles(con)
        found = roles.find(role, vg_id)
        if not found or not con.execute("SELECT 1 FROM membership WHERE email = ? AND scope = ? AND scope_id = ? "
                                        "AND role_id = ?", (email, scope, scope_id, found.id)).fetchone():
            raise HTTPException(404, "Zuordnung nicht gefunden.")
        _not_self(a, email)
        if found.id not in a.grantable(roles, scope, scope_id, vg_id):
            raise tenancy.Forbidden("Diese Rolle darfst du hier nicht entziehen.")
        con.execute("DELETE FROM membership WHERE email = ? AND scope = ? AND scope_id = ? AND role_id = ?",
                    (email, scope, scope_id, found.id))
        con.execute("DELETE FROM account WHERE email = ? AND NOT EXISTS (SELECT 1 FROM membership WHERE email = ?)",
                    (email, email))
        rbac.log(con, a.email, "Rolle entzogen", f"{found.label} für {email} in {name}", vg_id,
                 scope_id if scope == "tenant" else None)
    log.info("Rolle %s für %s in %s %s entzogen durch %s", found.key, email, scope, slug, a.email or "lokal")
    return get_memberships(a)


@router.get("/api/admin/users/effective")
def effective_permissions(email: str, a: tenancy.Access = Depends(access)):
    """Was eine Person darf: je VG bzw. Wehr ihre Rechte mit Herkunft (Rolle und Bereich) – nur in Bereichen,
    deren Zuordnungen der Benutzer sehen darf."""
    email = tenancy.normalize_email(email)
    with tenancy.central() as con:
        roles = rbac.Roles(con)
        rows = con.execute(
            "SELECT m.scope, m.scope_id, m.role_id, COALESCE(t.name, v.name) AS name, COALESCE(t.vg_id, v.id) AS vg_id "
            "FROM membership m LEFT JOIN tenant t ON m.scope = 'tenant' AND t.id = m.scope_id "
            "LEFT JOIN vg v ON m.scope = 'vg' AND v.id = m.scope_id WHERE m.email = ?", (email,)).fetchall()
        areas = _areas(con)
    result = []
    for scope, scope_id, vg_id, _, label in areas:
        if not _sees_users(a, scope, scope_id, vg_id):
            continue
        sources = [m for m in rows if (m["scope"] == scope and m["scope_id"] == scope_id) or
                   (scope == "tenant" and m["scope"] == "vg" and m["scope_id"] == vg_id)]
        origins = {}
        for m in sources:
            for p in roles.permissions(m["role_id"]):
                if scope in rbac.PERMISSIONS[p].scopes:
                    origins.setdefault(p, []).append(f"{roles.get(m['role_id']).label} ({m['name']})")
        if origins:
            result.append({"scope": scope, "name": label,
                           "permissions": [{"key": key, "label": p.label, "group": p.group, "from": origins[key]}
                                           for key, p in rbac.PERMISSIONS.items() if key in origins]})
    return {"email": email, "superadmin": email in tenancy.ADMIN_EMAILS, "areas": result}


@router.get("/api/admin/role-events")
def role_events(a: tenancy.Access = Depends(access)):
    """Protokoll der Vergaben und Rollenänderungen in den Bereichen, die der Benutzer sehen darf."""
    with tenancy.central() as con:
        rows = con.execute("SELECT e.at, e.email, e.action, e.detail, e.vg_id, e.tenant_id FROM role_event e "
                           "ORDER BY e.id DESC LIMIT 1000").fetchall()
    events = [{key: r[key] for key in ("at", "email", "action", "detail")} for r in rows
              if a.superadmin or (r["vg_id"] is not None and _sees_users(
                  a, "tenant" if r["tenant_id"] else "vg", r["tenant_id"] or r["vg_id"], r["vg_id"]))]
    return {"events": events[:200]}


