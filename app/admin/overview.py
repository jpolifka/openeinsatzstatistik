# -*- coding: utf-8 -*-
"""Verwaltung: Übersicht, was der Benutzer verwalten darf.
"""

from fastapi import APIRouter, Depends

from app import tenancy, theme
from app.rbac import KEYWORDS, PLAN_RELEASE, ROLES_MANAGE, SETTINGS, USERS_VIEW, VG_FEES

from app.admin.common import access

router = APIRouter()


# ---------------------------------------------------------------- Übersicht
TENANT_ADMIN = (SETTINGS, KEYWORDS, USERS_VIEW)
VG_ADMIN = (SETTINGS, KEYWORDS, VG_FEES, USERS_VIEW, ROLES_MANAGE)


def has_admin(a):
    """Sieht die Verwaltung: Superadmin oder ein Verwaltungsrecht in einer Wehr bzw. VG."""
    return a.superadmin or any(t.can(p) for t in a.tenants.values() for p in TENANT_ADMIN) or \
        any(p in granted for granted in a.vg_permissions.values() for p in VG_ADMIN)


@router.get("/api/admin")
def admin_overview(a: tenancy.Access = Depends(access)):
    """Was der Benutzer verwalten darf: Wehren und VGs mit ihren Verwaltungsrechten."""
    if not has_admin(a):
        raise tenancy.Forbidden("Keine Berechtigung für die Verwaltung.")
    tenants = [t for t in a.tenants.values() if a.superadmin or any(t.can(p) for p in TENANT_ADMIN)]
    vgs = {}
    for t in a.tenants.values():
        granted = sorted(p for p in VG_ADMIN if a.vg_can(t.vg_id, p))
        if granted:
            vgs[t.vg_slug] = {"slug": t.vg_slug, "name": t.vg_name, "permissions": granted}
    return {"superadmin": a.superadmin,
            "tenants": [{"slug": t.slug, "name": t.name, "vg": t.vg_name, "vg_slug": t.vg_slug,
                         "permissions": sorted(p for p in (*TENANT_ADMIN, PLAN_RELEASE) if t.can(p))}
                        for t in tenants],
            "vgs": list(vgs.values()),
            "users": a.superadmin or any(t.can(USERS_VIEW) for t in a.tenants.values()) or
            any(USERS_VIEW in granted for granted in a.vg_permissions.values()),
            "assets": theme.ASSETS, "fonts": theme.FONTS}


