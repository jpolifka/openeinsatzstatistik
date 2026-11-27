# -*- coding: utf-8 -*-
"""Superadmin: VGs und Wehren anlegen, ändern, löschen; Sitzungen einsehen und beenden.
"""
import time
from typing import Optional

from app import tenant_lifecycle
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app import agt_reminders, atemschutz, auth, db, mail, rbac, tenancy

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
            "SELECT v.id, v.slug, v.name, v.kind, v.subdomain, COALESCE(d.status, 'pending') AS dpa FROM vg v "
            "LEFT JOIN dpa d ON d.vg_id = v.id ORDER BY v.name")]
        tenants = [dict(r) for r in con.execute(
            "SELECT t.slug, t.name, t.active, t.created, v.slug AS vg FROM tenant t JOIN vg v ON v.id = t.vg_id "
            "ORDER BY v.name, t.name")]
        archives = [r[0] for r in con.execute("SELECT slug FROM tenant_archive")]
    for v in vgs:
        v["blocked"] = v["dpa"] not in ("signed", "not_required")   # AVV fehlt: Wehren gesperrt
    for t in tenants:
        if t["slug"] in archives or not t["active"]:
            t["incidents"] = None      # inaktive Wehren nicht öffnen (schneller bei vielen Wehren)
            continue
        with db.connection(tenancy.tenant_path(t["slug"])) as con:
            t["incidents"] = con.execute("SELECT COUNT(*) FROM incident").fetchone()[0]
    return {"vgs": vgs, "tenants": tenants, "pending_archives": archives}


# Rollen, die Atemschutz-Rechte haben dürfen (alles andere ist eine Abweichung)
AGT_EXPECTED = {"lead": {rbac.AGT_OWN, rbac.AGT_EVAL}, "vg_lead": {rbac.AGT_OWN}, "agt_self": {rbac.AGT_OWN}}


@router.get("/api/super/atemschutz")
def super_atemschutz(a: tenancy.Access = Depends(access)):
    """Prüfansicht der Atemschutz-Dokumentation für Superadmins: nur Zahlen, Rechte-Abgleich und Zugriffsprotokoll –
    nie Inhalte oder Daten einzelner Personen. Der Abruf selbst wird in jeder Wehr protokolliert."""
    _superadmin(a)
    with tenancy.central() as con:
        roles = rbac.Roles(con)
        holders = {r.key + (f" (VG {r.vg_id})" if r.vg_id else ""): sorted(roles.permissions(r.id) & rbac.FIXED_PERMISSIONS)
                   for r in roles if roles.permissions(r.id) & rbac.FIXED_PERMISSIONS}
        tenants = [dict(r) for r in con.execute(
            "SELECT t.id, t.slug, t.name, v.name AS vg FROM tenant t JOIN vg v ON v.id = t.vg_id WHERE t.active "
            "ORDER BY v.name, t.name")]
        archives = {r[0] for r in con.execute("SELECT slug FROM tenant_archive")}
    deviations = [f"{key}: {', '.join(perms)}" for key, perms in holders.items()
                  if key not in AGT_EXPECTED or set(perms) != AGT_EXPECTED[key]]
    result = []
    for t in tenants:
        if t["slug"] in archives:
            continue
        with db.connection(tenancy.tenant_path(t["slug"])) as con:
            atemschutz.audit(con, a.email, "agt.check.view")
            data = atemschutz.integrity(con)
            events = atemschutz.recent_audit(con)
        with tenancy.central() as con:
            role = tenancy.find_role(con, "agt_self", "tenant", t["id"])
            holders_here = {r[0] for r in con.execute("SELECT email FROM membership WHERE scope = 'tenant' AND scope_id = ? "
                                                      "AND role_id = ?", (t["id"], role.id))}
        emails = set(data.pop("emails"))
        result.append({"slug": t["slug"], "name": t["name"], "vg": t["vg"], **data,
                       "with_email": len(emails), "email_without_access": len(emails - holders_here),
                       "access_without_person": len(holders_here - emails), "events": events})
    return {"tenants": result, "deviations": deviations, "mail": mail.enabled(), "reminder_hour": agt_reminders.HOUR}


class VgIn(BaseModel):
    slug: str = ""   # leer = aus dem Namen bilden; Benutzer sehen den Kurznamen nicht
    name: str = Field(min_length=2, max_length=80)
    subdomain: Optional[str] = None   # Host des Anmeldelinks: <subdomain>.BASE_DOMAIN; leer = keine
    kind: Optional[str] = None   # Art des Aufgabenträgers (rbac.KINDS); leer = vg bzw. unverändert


@router.post("/api/super/vgs")
def create_vg(v: VgIn, a: tenancy.Access = Depends(access)):
    _superadmin(a)
    try:
        with tenancy.central() as con:
            tenancy.create_vg(con, v.slug.strip() or tenancy.suggest_vg_slug(con, v.name), v.name, v.kind or "vg",
                              v.subdomain)
            rbac.log(con, a.email, "VG angelegt", v.name)
    except ValueError as e:
        _invalid(str(e))
    except Exception:
        _invalid(f"Den Kurznamen „{v.slug}“ gibt es schon.")
    return super_overview(a)


@router.put("/api/super/vgs/{slug}")
def rename_vg(slug: str, v: VgIn, a: tenancy.Access = Depends(access)):
    _superadmin(a)
    with tenancy.central() as con:
        row = con.execute("SELECT id, kind FROM vg WHERE slug = ?", (slug,)).fetchone()
        if not row:
            raise HTTPException(404, "Verbandsgemeinde nicht gefunden.")
        try:
            if v.kind and v.kind != row["kind"]:
                tenancy.set_vg_kind(con, row["id"], v.kind)
            if v.subdomain is not None:
                tenancy.set_vg_subdomain(con, row["id"], v.subdomain)
        except ValueError as e:
            _invalid(str(e))
        con.execute("UPDATE vg SET name = ? WHERE slug = ?", (v.name.strip(), slug))
        rbac.log(con, a.email, "VG geändert", f"{v.name.strip()} ({v.kind or row['kind']})", row["id"])
    return super_overview(a)


@router.delete("/api/super/vgs/{slug}")
def delete_vg(slug: str, confirm: str = "", a: tenancy.Access = Depends(access)):
    """Leere VG entfernen (ohne Wehren): Zuordnungen, eigene Rollen, Vorgaben und Gebührenordnungen der VG
    werden gelöscht; das Protokoll und hochgeladene AVV-Dateien bleiben erhalten."""
    _superadmin(a)
    if confirm != slug:
        _invalid("Zum Bestätigen den Kurznamen der VG eintippen.")
    with tenancy.central() as con:
        row = con.execute("SELECT id, name FROM vg WHERE slug = ?", (slug,)).fetchone()
        if not row:
            raise HTTPException(404, "Verbandsgemeinde nicht gefunden.")
        if con.execute("SELECT 1 FROM tenant WHERE vg_id = ?", (row["id"],)).fetchone():
            _invalid("Die VG hat noch Wehren. Zuerst alle Wehren archivieren oder in eine andere VG verschieben.")
        con.execute("DELETE FROM membership WHERE (scope = 'vg' AND scope_id = ?) "
                    "OR role_id IN (SELECT id FROM role WHERE vg_id = ?)", (row["id"], row["id"]))
        con.execute("DELETE FROM account WHERE NOT EXISTS (SELECT 1 FROM membership m WHERE m.email = account.email)")
        rbac.log(con, a.email, "VG gelöscht", row["name"], row["id"])
        con.execute("DELETE FROM vg WHERE id = ?", (row["id"],))
    tenancy.forget_vg_config(row["id"])
    log.warning("VG %s gelöscht durch %s", slug, a.email or "lokal")
    return super_overview(a)


class TenantIn(BaseModel):
    slug: str = ""                   # leer = <vg>-<wehr>-<lfd>; die Oberfläche schickt nie einen
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
        try:
            if not t.slug.strip():
                t.slug = tenancy.suggest_slug(con, t.name, t.vg)
            if con.execute("SELECT 1 FROM tenant WHERE slug = ?", (t.slug,)).fetchone():
                _invalid(f"Den Kurznamen „{t.slug}“ gibt es schon (Kurznamen gelten für alle VGs). "
                         f"Vorschlag: „{tenancy.suggest_slug(con, t.name, t.vg)}“ – oder den Kurznamen weglassen.")
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
def change_tenant(slug: str, t: TenantChange, confirm: str = "", a: tenancy.Access = Depends(access)):
    _superadmin(a)
    with tenancy.central() as con:
        if con.execute("SELECT 1 FROM tenant_archive WHERE slug = ?", (slug,)).fetchone():
            raise HTTPException(409, "Die Wehr wird archiviert und kann nicht mehr geändert werden.")
        cur = con.execute("SELECT id, name, vg_id FROM tenant WHERE slug = ?", (slug,)).fetchone()
        if not cur:
            raise HTTPException(404, "Wehr nicht gefunden.")
        if t.name:
            con.execute("UPDATE tenant SET name = ? WHERE slug = ?", (t.name.strip(), slug))
            rbac.log(con, a.email, "Wehr umbenannt", f"{cur['name']} → {t.name.strip()}", cur["vg_id"], cur["id"])
        if t.vg:
            row = con.execute("SELECT id, name FROM vg WHERE slug = ?", (t.vg,)).fetchone()
            if not row:
                _invalid("Unbekannte Verbandsgemeinde.")
            if row["id"] != cur["vg_id"]:
                if confirm != slug:
                    _invalid("Zum Verschieben den Kurznamen der Wehr bestätigen.")
                foreign = con.execute(
                    "SELECT m.email, r.label FROM membership m JOIN role r ON r.id = m.role_id "
                    "WHERE m.scope = 'tenant' AND m.scope_id = ? AND r.vg_id IS NOT NULL AND r.vg_id <> ?",
                    (cur["id"], row["id"])).fetchall()
                if foreign:
                    _invalid("Die Wehr hat Zuordnungen mit Rollen der bisherigen VG. Zuerst entziehen: "
                             + "; ".join(f"{f['email']} ({f['label']})" for f in foreign[:10]))
                con.execute("UPDATE tenant SET vg_id = ? WHERE slug = ?", (row["id"], slug))
                rbac.log(con, a.email, "Wehr verschoben", f"{cur['name']} → {row['name']}", row["id"], cur["id"])
        if t.active is not None:
            con.execute("UPDATE tenant SET active = ? WHERE slug = ?", (int(t.active), slug))
            rbac.log(con, a.email, "Wehr aktiviert" if t.active else "Wehr deaktiviert", cur["name"], cur["vg_id"], cur["id"])
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
        rbac.log(con, a.email, "Wehr archiviert", row["name"], row["vg_id"], row["id"])
    tenant_lifecycle.finish_archive(slug)
    tenancy.forget_config(slug)
    log.warning("Archivierung für Wehr %s beauftragt durch %s", slug, a.email or "lokal")
    return super_overview(a)



# ---------------------------------------------------------------- Superadmin: Sitzungen
def _sessions(a, request):
    """Gültige Sitzungen, zuletzt aktive zuerst; die eigene ist markiert."""
    own = auth.current_session_id(request)
    with tenancy.central() as con:
        rows = [dict(r) for r in con.execute(
            "SELECT id, email, created, last_seen, expires, user_agent FROM session WHERE expires > ? "
            "ORDER BY last_seen DESC", (time.time(),))]
    for r in rows:
        r["current"] = r["id"] == own
    return {"enabled": auth.enabled(), "sessions": rows}


@router.get("/api/super/sessions")
def list_sessions(request: Request, a: tenancy.Access = Depends(access)):
    _superadmin(a)
    return _sessions(a, request)


@router.delete("/api/super/sessions/{session_id}")
def end_one_session(session_id: int, request: Request, a: tenancy.Access = Depends(access)):
    """Eine Sitzung beenden (erzwungene Abmeldung). Die eigene geht über „Abmelden“."""
    _superadmin(a)
    if session_id == auth.current_session_id(request):
        _invalid("Die eigene Sitzung beendest du mit „Abmelden“.")
    with tenancy.central() as con:
        row = con.execute("DELETE FROM session WHERE id = ? RETURNING email", (session_id,)).fetchone()
    if row:
        log.info("Sitzung %s von %s beendet durch %s", session_id, row["email"], a.email or "lokal")
    return _sessions(a, request)


@router.delete("/api/super/sessions")
def end_sessions(request: Request, email: str = "", others: bool = False, a: tenancy.Access = Depends(access)):
    """Alle Sitzungen einer Adresse (email) oder aller anderen Benutzer (others) beenden – nie die eigene."""
    _superadmin(a)
    own = auth.current_session_id(request)
    if bool(email) == others:
        _invalid("Entweder eine Adresse oder „alle anderen“ angeben.")
    with tenancy.central() as con:
        if email:
            count = con.execute("DELETE FROM session WHERE email = ? AND id IS NOT ?",
                                (tenancy.normalize_email(email), own)).rowcount
        else:
            count = con.execute("DELETE FROM session WHERE id IS NOT ?", (own,)).rowcount
    log.info("%s Sitzungen (%s) beendet durch %s", count, email or "alle anderen", a.email or "lokal")
    return _sessions(a, request)
