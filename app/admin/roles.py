# -*- coding: utf-8 -*-
"""Verwaltung: Rollen anlegen, ändern, löschen.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app import rbac, tenancy
from app.rbac import ROLES_MANAGE, USERS_VIEW

from app.admin.common import _invalid, access, log

router = APIRouter()


# ---------------------------------------------------------------- Rollen
def _held(a, roles):
    """Eigene Rollen samt Vorfahren – die ändert man nicht selbst."""
    return set().union(*(roles.chain(r["role_id"]) for r in a.roles)) if a.roles else set()


def _ceiling(a, vg_id, scope):
    """Rechte, die der Benutzer in dieser VG selbst hat. Eine Wehr-Rolle gilt in allen Wehren der VG, daher
    zählen auch die Rechte aus Rollen einer Wehr."""
    held = set(a.vg_permissions.get(vg_id, ()))
    if scope == "tenant":
        for tenant in a.tenants.values():
            if tenant.vg_id == vg_id:
                held |= tenant.permissions
    return held


def _reachable(a, roles, vg_id):
    """Rollen, die der Benutzer selbst innehat oder sich (über eine zweite Adresse) verschaffen kann: seine eigenen,
    die er vergeben darf, und alles, was deren Inhaber wiederum vergeben dürfen."""
    found = set(_held(a, roles))
    scopes = [("vg", vg_id)] + [("tenant", t.id) for t in a.tenants.values() if t.vg_id == vg_id]
    for scope, scope_id in scopes:
        found |= a.grantable(roles, scope, scope_id, vg_id)
    todo = list(found)
    while todo:
        for role_id in roles.grants(todo.pop()):
            if role_id not in found:
                found.add(role_id)
                todo.append(role_id)
    return found


def _check_ceiling(a, roles, vg_id, scope, r):
    """403, wenn die Rolle dem Benutzer (oder einer zweiten Adresse von ihm) Rechte verschaffen würde, die er selbst
    nicht hat. Wer nur Rollen pflegt, könnte sonst eine Rolle mit allen Rechten anlegen, sich als Vergeber eintragen
    und sie an eine andere Adresse vergeben. Rollen, die er nicht erreichen kann, darf er frei definieren – das ist
    die Aufgabenteilung der VG: die Wehrführer, die sie vergeben, haben die Rechte selbst."""
    reach = _reachable(a, roles, vg_id)
    if a.superadmin or not set(r.granted_by) & reach:
        return
    # Mehr als das, was er selbst hat oder sich schon über seine Verteilung verschaffen kann, ist neu
    reachable = set().union(*(roles.permissions(role_id) for role_id in reach)) if reach else set()
    ceiling = lambda role_scope: _ceiling(a, vg_id, role_scope) | reachable        # noqa: E731
    excess = rbac.allowed(rbac.close(r.permissions), scope) - ceiling(scope)
    if r.parent is not None:
        excess |= roles.permissions(r.parent) - ceiling(scope)
    for role_id in r.grants:        # wer diese Rolle hat, darf die genannten vergeben
        granted = roles.get(role_id)
        if granted:
            excess |= roles.permissions(role_id) - ceiling(granted.scope)
    if excess:
        labels = ", ".join(rbac.PERMISSIONS[p].label for p in rbac.PERMISSIONS if p in excess)
        raise tenancy.Forbidden(f"Du darfst dir und anderen über deine Verteilung keine Rechte verschaffen, die du "
                                f"selbst nicht hast: {labels}.")


def _may_edit(a, role, roles):
    if a.superadmin:
        return True
    return role.vg_id is not None and a.vg_can(role.vg_id, ROLES_MANAGE) and role.id not in _held(a, roles)


def _role_vgs(a, con):
    """VGs, deren Rollen der Benutzer sieht -> {id: {slug, name, manage}}."""
    result = {}
    for v in con.execute("SELECT id, slug, name FROM vg ORDER BY name"):
        sees = a.superadmin or a.vg_can(v["id"], USERS_VIEW) or \
            any(t.vg_id == v["id"] and t.can(USERS_VIEW) for t in a.tenants.values())
        if sees:
            result[v["id"]] = {"slug": v["slug"], "name": v["name"], "manage": a.vg_can(v["id"], ROLES_MANAGE)}
    return result


@router.get("/api/admin/roles")
def get_roles(a: tenancy.Access = Depends(access)):
    """Rechtekatalog und Rollen (System-, globale und eigene Rollen der sichtbaren VGs) mit Vererbung und Verteilung."""
    with tenancy.central() as con:
        roles = rbac.Roles(con)
        vgs = _role_vgs(a, con)
        members = dict(con.execute("SELECT role_id, COUNT(*) FROM membership GROUP BY role_id").fetchall())
    if not vgs and not a.superadmin:
        raise tenancy.Forbidden("Keine Berechtigung für die Rollen.")
    listed = [r for r in roles if r.vg_id is None or r.vg_id in vgs]
    ids = {r.id for r in listed}

    def role_json(r):
        editable = _may_edit(a, r, roles)
        children = any(x.parent_id == r.id for x in roles)
        return {"id": r.id, "key": r.key, "label": r.label, "description": r.description, "scope": r.scope,
                "vg": vgs[r.vg_id]["slug"] if r.vg_id else None, "parent": r.parent_id, "system": r.system,
                "permissions": sorted(r.own), "effective": sorted(roles.permissions(r.id)),
                "grants": sorted(r.own_grants & ids),
                "granted_by": sorted(x.id for x in listed if r.id in x.own_grants),
                "members": members.get(r.id, 0), "editable": editable,
                "deletable": editable and not r.system and not members.get(r.id) and not children}

    return {"permissions": [{"key": p.key, "group": p.group, "label": p.label, "scopes": list(p.scopes),
                             "requires": list(p.requires)} for p in rbac.PERMISSIONS.values()],
            "scopes": rbac.SCOPES, "superadmin": a.superadmin,
            "vgs": [{"slug": v["slug"], "name": v["name"], "manage": v["manage"]} for v in vgs.values()],
            "roles": [role_json(r) for r in listed]}


class RoleIn(BaseModel):
    label: str
    description: str = Field("", max_length=300)
    scope: str = "tenant"
    vg: Optional[str] = None          # Slug der VG; leer = für alle VGs (nur Superadmin)
    parent: Optional[int] = None
    permissions: List[str] = []
    granted_by: List[int] = []        # Rollen, die diese Rolle vergeben dürfen
    grants: List[int] = []            # Rollen, die Inhaber dieser Rolle vergeben dürfen


def _role_summary(r: RoleIn):
    labels = [rbac.PERMISSIONS[p].label for p in rbac.PERMISSIONS if p in r.permissions]
    return f"{r.label.strip()}: {', '.join(labels) or 'keine eigenen Rechte'}"


@router.post("/api/admin/roles")
def create_role(r: RoleIn, a: tenancy.Access = Depends(access)):
    with tenancy.central() as con:
        vg_id = None
        if r.vg:
            row = con.execute("SELECT id FROM vg WHERE slug = ?", (r.vg,)).fetchone()
            if not row:
                raise HTTPException(404, "Verbandsgemeinde nicht gefunden.")
            vg_id = row["id"]
        if vg_id is None and not a.superadmin:
            raise tenancy.Forbidden("Rollen für alle VGs legt nur der Superadmin an.")
        if vg_id is not None and not a.vg_can(vg_id, ROLES_MANAGE):
            raise tenancy.Forbidden("Keine Berechtigung, Rollen dieser VG anzulegen.")
        roles = rbac.Roles(con)
        _check_ceiling(a, roles, vg_id, r.scope, r)
        try:
            rbac.save_role(con, roles, None, vg_id=vg_id, scope=r.scope, label=r.label,
                           description=r.description, parent_id=r.parent, permissions=r.permissions,
                           granted_by=r.granted_by, grants=r.grants)
        except rbac.Invalid as e:
            _invalid(str(e))
        rbac.log(con, a.email, "Rolle angelegt", _role_summary(r), vg_id)
    log.info("Rolle %s angelegt durch %s", r.label, a.email or "lokal")
    return get_roles(a)


def _editable_role(con, a, role_id):
    roles = rbac.Roles(con)
    role = roles.get(role_id)
    if not role:
        raise HTTPException(404, "Rolle nicht gefunden.")
    if not _may_edit(a, role, roles):
        if role.id in _held(a, roles):
            raise tenancy.Forbidden("Rollen, die du selbst hast (auch über Vererbung), ändert jemand anderes.")
        raise tenancy.Forbidden("Diese Rolle darfst du nicht ändern.")
    return roles, role


@router.put("/api/admin/roles/{role_id}")
def change_role(role_id: int, r: RoleIn, a: tenancy.Access = Depends(access)):
    """Rolle ändern; Bereich und VG bleiben."""
    with tenancy.central() as con:
        roles, role = _editable_role(con, a, role_id)
        _check_ceiling(a, roles, role.vg_id, role.scope, r)
        try:
            rbac.save_role(con, roles, role.id, vg_id=role.vg_id, scope=role.scope, label=r.label,
                           description=r.description, parent_id=r.parent, permissions=r.permissions,
                           granted_by=r.granted_by, grants=r.grants)
        except rbac.Invalid as e:
            _invalid(str(e))
        rbac.log(con, a.email, "Rolle geändert", _role_summary(r), role.vg_id)
    log.info("Rolle %s geändert durch %s", role.key, a.email or "lokal")
    return get_roles(a)


@router.delete("/api/admin/roles/{role_id}")
def delete_role(role_id: int, a: tenancy.Access = Depends(access)):
    with tenancy.central() as con:
        roles, role = _editable_role(con, a, role_id)
        try:
            rbac.delete_role(con, roles, role.id)
        except rbac.Invalid as e:
            _invalid(str(e))
        rbac.log(con, a.email, "Rolle gelöscht", role.label, role.vg_id)
    log.info("Rolle %s gelöscht durch %s", role.key, a.email or "lokal")
    return get_roles(a)


