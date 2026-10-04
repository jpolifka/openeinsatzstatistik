# -*- coding: utf-8 -*-
"""Superadmin: VGs und Wehren anlegen, ändern, löschen.
"""
from typing import Optional

from app import tenant_lifecycle
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app import db, rbac, tenancy

from app.admin.common import _invalid, access, log

router = APIRouter()


# ---------------------------------------------------------------- Superadmin: VGs und Wehren
def _superadmin(a):
    if not a.superadmin:
        raise tenancy.Forbidden("Nur für Superadmins.")


@router.get("/api/super/overview")
def super_overview(a: tenancy.Access = Depends(access)):
    _superadmin(a)
    with tenancy.central() as con:
        vgs = [dict(r) for r in con.execute(
            "SELECT v.id, v.slug, v.name, COALESCE(d.status, 'pending') AS dpa FROM vg v "
            "LEFT JOIN dpa d ON d.vg_id = v.id ORDER BY v.name")]
        tenants = [dict(r) for r in con.execute(
            "SELECT t.slug, t.name, t.active, t.created, v.slug AS vg FROM tenant t JOIN vg v ON v.id = t.vg_id "
            "ORDER BY v.name, t.name")]
        archives = [r[0] for r in con.execute("SELECT slug FROM tenant_archive")]
    for t in tenants:
        if t["slug"] in archives:
            t["incidents"] = None
            continue
        with db.connection(tenancy.tenant_path(t["slug"])) as con:
            t["incidents"] = con.execute("SELECT COUNT(*) FROM incident").fetchone()[0]
    return {"vgs": vgs, "tenants": tenants, "pending_archives": archives}


class VgIn(BaseModel):
    slug: str
    name: str = Field(min_length=2, max_length=80)


@router.post("/api/super/vgs")
def create_vg(v: VgIn, a: tenancy.Access = Depends(access)):
    _superadmin(a)
    try:
        with tenancy.central() as con:
            tenancy.create_vg(con, v.slug, v.name)
    except ValueError as e:
        _invalid(str(e))
    except Exception:
        _invalid(f"Den Kurznamen „{v.slug}“ gibt es schon.")
    return super_overview(a)


@router.put("/api/super/vgs/{slug}")
def rename_vg(slug: str, v: VgIn, a: tenancy.Access = Depends(access)):
    _superadmin(a)
    with tenancy.central() as con:
        con.execute("UPDATE vg SET name = ? WHERE slug = ?", (v.name.strip(), slug))
    return super_overview(a)


class TenantIn(BaseModel):
    slug: str
    name: str = Field(min_length=2, max_length=80)
    vg: str
    email: Optional[str] = None      # erster Wehrführer


@router.post("/api/super/tenants")
def create_tenant(t: TenantIn, a: tenancy.Access = Depends(access)):
    _superadmin(a)
    with tenancy.central() as con:
        row = con.execute("SELECT id FROM vg WHERE slug = ?", (t.vg,)).fetchone()
        if not row:
            _invalid("Bitte eine Verbandsgemeinde wählen.")
        if con.execute("SELECT 1 FROM tenant WHERE slug = ?", (t.slug,)).fetchone():
            _invalid(f"Den Kurznamen „{t.slug}“ gibt es schon.")
        try:
            tenant_id = tenancy.create_tenant(con, t.slug, t.name, row["id"])
        except ValueError as e:
            _invalid(str(e))
        rbac.log(con, a.email, "Wehr angelegt", t.name, row["id"], tenant_id)
        if t.email:
            role = tenancy.grant(con, t.email, "lead", tenant_id)
            rbac.log(con, a.email, "Rolle vergeben", f"{role.label} für {tenancy.normalize_email(t.email)} in {t.name}",
                     row["id"], tenant_id)
    log.info("Wehr %s angelegt durch %s", t.slug, a.email or "lokal")
    return super_overview(a)


class TenantChange(BaseModel):
    name: Optional[str] = None
    vg: Optional[str] = None
    active: Optional[bool] = None


@router.put("/api/super/tenants/{slug}")
def change_tenant(slug: str, t: TenantChange, a: tenancy.Access = Depends(access)):
    _superadmin(a)
    with tenancy.central() as con:
        if con.execute("SELECT 1 FROM tenant_archive WHERE slug = ?", (slug,)).fetchone():
            raise HTTPException(409, "Die Wehr wird archiviert und kann nicht mehr geändert werden.")
        if not con.execute("SELECT 1 FROM tenant WHERE slug = ?", (slug,)).fetchone():
            raise HTTPException(404, "Wehr nicht gefunden.")
        if t.name:
            con.execute("UPDATE tenant SET name = ? WHERE slug = ?", (t.name.strip(), slug))
        if t.vg:
            row = con.execute("SELECT id FROM vg WHERE slug = ?", (t.vg,)).fetchone()
            if not row:
                _invalid("Unbekannte Verbandsgemeinde.")
            con.execute("UPDATE tenant SET vg_id = ? WHERE slug = ?", (row["id"], slug))
        if t.active is not None:
            con.execute("UPDATE tenant SET active = ? WHERE slug = ?", (int(t.active), slug))
    tenancy.forget_config(slug)
    log.info("Wehr %s geändert durch %s: %s", slug, a.email or "lokal", t.model_dump(exclude_none=True))
    return super_overview(a)


@router.delete("/api/super/tenants/{slug}")
def delete_tenant(slug: str, confirm: str = "", a: tenancy.Access = Depends(access)):
    """Wehr entfernen: Zuordnungen löschen, Ordner nach deleted/ verschieben (nicht löschen)."""
    _superadmin(a)
    if confirm != slug:
        _invalid("Zum Bestätigen den Kurznamen der Wehr eintippen.")
    with tenancy.central() as con:
        row = con.execute("SELECT id, vg_id, name FROM tenant WHERE slug = ?", (slug,)).fetchone()
        if not row:
            raise HTTPException(404, "Wehr nicht gefunden.")
        tenant_lifecycle.begin_archive(con, slug, a.email)
    tenant_lifecycle.finish_archive(slug)
    tenancy.forget_config(slug)
    log.warning("Archivierung für Wehr %s beauftragt durch %s", slug, a.email or "lokal")
    return super_overview(a)

