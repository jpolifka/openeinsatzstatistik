# -*- coding: utf-8 -*-
"""
Verwaltung: Fachkonfiguration, Farben und Logos einer Wehr, Stichwortkatalog, Benutzer und
(für Superadmins) Verbandsgemeinden und Wehren.

Rechte: die Wehr-Einstellungen brauchen das Recht ADMIN für die Wehr (Wehrführer, Wehrleiter,
Superadmin). Rollen vergeben darf jeder nur im Rahmen von tenancy.GRANTABLE und nur in seinem
Bereich; VGs und Wehren anlegen nur der Superadmin.
"""
import csv
import datetime as dt
import io
import json
import logging
import os
import re
import shutil
from typing import List, Optional

import openpyxl
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app import auth, db, domain, fees, store, tenancy, theme
from app.tenancy import ADMIN, ROLES
from app.tenant_config import TenantConfig, Vehicle

log = logging.getLogger("pdf2einsatz")
router = APIRouter()

# Funkrufname wie im BKS-Bericht; als Schlüssel eines Ersatzfahrzeugs auch der alte Kurzname (01/23)
VEHICLE_NAME = re.compile(r"[A-ZÄÖÜ0-9][\w#./^ -]{0,59}")
KEYWORD_CODE = re.compile(r"[A-Z]\d(\.\d\d)?")
NUMBERINGS = ("bks", "by_date")
MAX_KEYWORD_FILE = 2 * 1024 * 1024


access = auth.access


def _invalid(message):
    raise HTTPException(422, message)


# ---------------------------------------------------------------- Übersicht
@router.get("/api/admin")
def admin_overview(a: tenancy.Access = Depends(access)):
    """Was der Benutzer verwalten darf: Wehren mit Verwaltungsrecht, VGs mit Rollenvergabe."""
    tenants = [t for t in a.tenants.values() if t.can(ADMIN)]
    if not tenants and not a.superadmin:
        raise tenancy.Forbidden("Keine Berechtigung für die Verwaltung.")
    vgs = {}
    for t in tenants:
        if _manages_vg(a, t.vg_id):
            vgs[t.vg_slug] = t.vg_name
    return {"superadmin": a.superadmin,
            "tenants": [{"slug": t.slug, "name": t.name, "vg": t.vg_name, "vg_slug": t.vg_slug} for t in tenants],
            "vgs": [{"slug": slug, "name": name} for slug, name in vgs.items()],
            "roles": {role: {"scope": scope, "label": label} for role, (scope, label, _) in ROLES.items()},
            "assets": theme.ASSETS}


# ---------------------------------------------------------------- Einstellungen der Wehr
class VehicleIn(BaseModel):
    name: str = ""                 # Funkrufname wie im BKS-Bericht
    call_sign: str = ""            # Kurzname; leer bei neuen Fahrzeugen, dann aus dem Namen abgeleitet
    label: str = ""
    in_service_from: Optional[dt.date] = None
    in_service_until: Optional[dt.date] = None
    replaced_by: Optional[str] = None
    in_plan_crew: bool = True


class PlaceIn(BaseModel):
    name: str
    prefix: str


class SettingsIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    colors: dict = {}
    fleet: List[VehicleIn] = []
    substitutes: dict = {}
    unit_prefix: str = ""
    own_prefix: str = ""
    unit_marker: str = ""
    control_center: str = ""
    places: List[PlaceIn] = []
    plan_places: List[str] = []
    plan_min_level: int = domain.PLAN_MIN_LEVEL
    response_limits: List[int] = list(domain.RESPONSE_LIMITS)
    default_limit: int = domain.DEFAULT_LIMIT
    second_limit: int = domain.SECOND_LIMIT
    day_hours: List[int] = [domain.DAY_START_HOUR, domain.DAY_END_HOUR]
    numbering: str = "bks"
    response_plan_public: bool = False


def _settings_json(tenant, cfg):
    with tenant.connection() as con:
        used = store.vehicles_with_data(con)
        assets = {r["name"]: f"/api/branding/{tenant.slug}/{r['name']}?v={r['modified'].replace(' ', 'T')}"
                  for r in con.execute("SELECT name, modified FROM asset")}
    with tenancy.central() as con:
        fee_types = fees.vehicle_types(con, tenant.vg_id)

    def types(name):
        return domain.describe_call_sign(name).get("types", [])

    return {
        "assets": {name: assets.get(name) for name in theme.ASSETS},
        "slug": tenant.slug, "name": cfg.name, "colors": cfg.colors,
        "palette": theme.palette(cfg.colors) if cfg.colors else None,
        "fleet": [{"call_sign": v.call_sign, "name": v.name, "description": domain.call_sign_text(v.name),
                   "suggested_name": "" if v.name else _suggested_name(v.call_sign, cfg) or "",
                   "types": types(v.name or _suggested_name(v.call_sign, cfg) or v.call_sign),
                   "label": v.label, "in_service_from": v.in_service_from,
                   "in_service_until": v.in_service_until, "replaced_by": v.replaced_by,
                   "in_plan_crew": v.in_plan_crew, "incidents": used.get(v.call_sign, 0)} for v in cfg.fleet],
        "unused_data": {cs: n for cs, n in used.items() if cs not in cfg.vehicles},
        "substitutes": cfg.substitutes,
        **{key: getattr(cfg, key) for key in ("unit_prefix", "own_prefix", "unit_marker", "control_center",
                                               "plan_places", "plan_min_level", "response_limits", "default_limit",
                                               "second_limit", "day_hours", "numbering", "response_plan_public")},
        "places": [{"name": n, "prefix": p} for n, p in cfg.places],
        "known_vehicles": [{"name": n, "description": domain.call_sign_text(n), "types": types(n),
                            "label": fees.suggest_type(types(n), fee_types)} for n in _known_vehicles(tenant, cfg)],
        "fee_types": fee_types,
        "call_sign_directory": domain.CALL_SIGN_DIRECTORY_URL,
    }


def _suggested_name(call_sign, cfg):
    """Vorschlag für Einträge mit altem Kurznamen ohne Funkrufnamen: unit_prefix + 02/45 + „-01“."""
    if cfg.unit_prefix and re.fullmatch(r"\d\d/\d\d", call_sign):
        return f"{cfg.unit_prefix}{call_sign}-01"
    return None


def _known_vehicles(tenant, cfg):
    """Funkrufnamen aus Berichten zur Auswahl in der Fahrzeugliste: aus den Einsätzen der Wehr und den
    Stammdatensätzen ihrer VG (personenfrei), ohne Leitstelle und Zeilen ohne Funkrufnummer."""
    with tenant.connection() as con:
        names = {r[0] for r in con.execute("SELECT DISTINCT name FROM vehicle WHERE name <> ''")}
    with tenancy.central() as con:
        for (vehicles,) in con.execute("SELECT vehicles FROM master_record WHERE vg_id = ?", (tenant.vg_id,)):
            names.update(v.get("name") or "" for v in json.loads(vehicles))
    names.update(v.name for v in cfg.fleet)
    names.update(filter(None, (_suggested_name(cs, cfg) for cs in [v.call_sign for v in cfg.fleet] + list(cfg.substitutes))))
    return sorted(n for n in names if n and n != cfg.control_center and domain.describe_call_sign(n))


@router.get("/api/admin/{slug}/settings")
def get_settings(slug: str, a: tenancy.Access = Depends(access)):
    tenant = a.tenant(slug, ADMIN)
    return _settings_json(tenant, tenant.config)


def _check_fleet(s: SettingsIn):
    """Fahrzeugliste prüfen; neue Fahrzeuge bekommen ihren Kurznamen aus dem Funkrufnamen."""
    rows = [(v, v.name.strip(), v.call_sign.strip()) for v in s.fleet]
    names = [name for _, name, _ in rows if name]
    if len(set(names)) != len(names):
        _invalid("Ein Funkrufname steht doppelt in der Fahrzeugliste.")
    derive = TenantConfig(name="", unit_prefix=s.unit_prefix)
    taken = {call_sign for _, _, call_sign in rows if call_sign}
    result = []
    for v, name, call_sign in rows:
        label = name or call_sign
        if not label:
            _invalid("Jedes Fahrzeug braucht einen Funkrufnamen wie im BKS-Bericht, z. B. FL NR#.ABC 02/45-01.")
        if name and not VEHICLE_NAME.fullmatch(name):
            _invalid(f"Funkrufname „{name}“: bitte wie im BKS-Bericht angeben, z. B. FL NR#.ABC 02/45-01.")
        if not call_sign:
            call_sign = derive.new_call_sign(name, taken)
            taken.add(call_sign)
        if v.in_service_from and v.in_service_until and v.in_service_until < v.in_service_from:
            _invalid(f"{label}: „außer Dienst ab“ liegt vor „im Dienst ab“.")
        result.append((v, name, call_sign))
    unnamed = {call_sign for _, name, call_sign in result if not name}
    for v, name, _ in result:
        legacy = derive.block_of(name) if name and not v.call_sign.strip() else None
        if legacy in unnamed:
            _invalid(f"„{name}“ ist das Fahrzeug {legacy}, das schon in der Liste steht – "
                     f"bitte den Funkrufnamen dort eintragen statt es neu hinzuzufügen.")
    call_signs = [call_sign for _, _, call_sign in result]
    if len(set(call_signs)) != len(call_signs):
        _invalid("Ein Kurzname steht doppelt in der Fahrzeugliste.")
    by_name = {name: call_sign for _, name, call_sign in result if name}
    fleet = []
    for v, name, call_sign in result:
        successor = by_name.get(v.replaced_by, v.replaced_by) or None
        if successor and successor not in call_signs:
            _invalid(f"{name or call_sign}: Nachfolger {v.replaced_by} steht nicht in der Fahrzeugliste.")
        fleet.append(Vehicle(call_sign, v.label.strip(),
                             v.in_service_from.isoformat() if v.in_service_from else None,
                             v.in_service_until.isoformat() if v.in_service_until else None,
                             successor, v.in_plan_crew, name))
    return tuple(fleet)


def _check_settings(s: SettingsIn):
    """Fachliche Prüfung -> TenantConfig; Meldungen auf Deutsch (422)."""
    try:
        colors = theme.normalize(s.colors)
    except ValueError as e:
        _invalid(str(e))
    problems = theme.check(colors)
    if problems:
        _invalid(" ".join(problems))
    fleet = _check_fleet(s)
    call_signs = [v.call_sign for v in fleet]
    by_name = {v.name: v.call_sign for v in fleet if v.name}
    substitutes = {}
    for sub, block in s.substitutes.items():
        sub, block = sub.strip(), by_name.get(block, block)
        if not VEHICLE_NAME.fullmatch(sub) or block not in call_signs:
            _invalid(f"Ersatzfahrzeug {sub}: der Block {block} muss ein Fahrzeug der Liste sein.")
        substitutes[sub] = block
    names = [p.name.strip() for p in s.places]
    if any(not p.name.strip() or not p.prefix.strip() for p in s.places) or len(set(names)) != len(names):
        _invalid("Jeder Ort braucht einen eindeutigen Namen und einen Namensanfang.")
    if not set(s.plan_places) <= set(names):
        _invalid("Bedarfsplan-Orte müssen in der Ortsliste stehen.")
    limits = sorted(set(s.response_limits))
    if not limits or any(not 1 <= m <= 60 for m in limits) or s.default_limit not in limits:
        _invalid("Zeitgrenzen: 1 bis 60 Minuten, die Standardgrenze muss dabei sein.")
    if not max(limits) < s.second_limit <= 120:
        _invalid("Die zweite Zeitgrenze muss über den Zeitgrenzen des Bedarfsplans liegen.")
    if not 1 <= s.plan_min_level <= 4:
        _invalid("Die Mindest-Alarmstufe muss zwischen 1 und 4 liegen.")
    if len(s.day_hours) != 2 or not 0 <= s.day_hours[0] < s.day_hours[1] <= 24:
        _invalid("Tag: Beginn und Ende als volle Stunden, Beginn vor Ende.")
    if s.numbering not in NUMBERINGS:
        _invalid("Nummerierung: aus dem Bericht oder nach Datum.")
    if s.own_prefix and not re.fullmatch(r"\d\d/", s.own_prefix):
        _invalid("Eigener Präfix: zwei Ziffern und Schrägstrich, z. B. 02/.")
    return TenantConfig(
        name=s.name.strip(), colors=colors, substitutes=substitutes, fleet=fleet,
        unit_prefix=s.unit_prefix, own_prefix=s.own_prefix, unit_marker=s.unit_marker.strip(),
        control_center=s.control_center.strip() or domain.CONTROL_CENTER,
        places=tuple((p.name.strip(), p.prefix.strip().lower()) for p in s.places), plan_places=tuple(s.plan_places),
        plan_min_level=s.plan_min_level, response_limits=tuple(limits), default_limit=s.default_limit,
        second_limit=s.second_limit, day_hours=tuple(s.day_hours), numbering=s.numbering,
        response_plan_public=s.response_plan_public)


@router.put("/api/admin/{slug}/settings")
def put_settings(slug: str, s: SettingsIn, a: tenancy.Access = Depends(access)):
    tenant = a.tenant(slug, ADMIN)
    cfg = _check_settings(s)
    with tenant.connection() as con:
        tenancy.save_config(con, cfg)
        if cfg.numbering == "by_date":         # beim Umstellen alle Jahre nach Datum durchnummerieren
            for row in store.years(con):
                store.renumber(con, row["year"])
    with tenancy.central() as con:
        con.execute("UPDATE tenant SET name = ? WHERE id = ?", (cfg.name, tenant.id))
    tenancy.forget_config(slug)
    log.info("Einstellungen von %s geändert durch %s", slug, a.email or "lokal")
    tenant.name = cfg.name
    return _settings_json(tenant, tenant.config)


# ---------------------------------------------------------------- Gebührenordnung der VG
class ScheduleIn(BaseModel):
    name: str
    valid_from: str
    rates: dict


def _managed_vg_id(a, vg_slug):
    """VG, deren Gebührenordnung der Benutzer pflegen darf (Wehrleiter der VG, Superadmin)."""
    with tenancy.central() as con:
        row = con.execute("SELECT id FROM vg WHERE slug = ?", (vg_slug,)).fetchone()
    if not row or not a.manages_vg(row["id"]):
        raise tenancy.Forbidden("Die Gebührenordnung pflegt der Wehrleiter der VG.")
    return row["id"]


def _schedules_json(vg_id):
    with tenancy.central() as con:
        return {"schedules": fees.schedules(con, vg_id)}


@router.get("/api/admin/vgs/{vg_slug}/fees")
def get_fee_schedules(vg_slug: str, a: tenancy.Access = Depends(access)):
    return _schedules_json(_managed_vg_id(a, vg_slug))


@router.post("/api/admin/vgs/{vg_slug}/fees")
@router.put("/api/admin/vgs/{vg_slug}/fees/{schedule_id}")
def save_fee_schedule(vg_slug: str, s: ScheduleIn, schedule_id: Optional[int] = None,
                      a: tenancy.Access = Depends(access)):
    vg_id = _managed_vg_id(a, vg_slug)
    with tenancy.central() as con:
        try:
            fees.save_schedule(con, vg_id, s.name, s.valid_from, s.rates, a.email, schedule_id)
        except ValueError as e:
            _invalid(str(e))
        except KeyError:
            raise HTTPException(404, "Fassung nicht gefunden.")
    log.info("Gebührenordnung der VG %s geändert durch %s", vg_slug, a.email or "lokal")
    return _schedules_json(vg_id)


@router.delete("/api/admin/vgs/{vg_slug}/fees/{schedule_id}")
def delete_fee_schedule(vg_slug: str, schedule_id: int, a: tenancy.Access = Depends(access)):
    vg_id = _managed_vg_id(a, vg_slug)
    with tenancy.central() as con:
        fees.delete_schedule(con, vg_id, schedule_id)
    return _schedules_json(vg_id)


class PlanRelease(BaseModel):
    public: bool


@router.put("/api/admin/{slug}/response-plan")
def release_response_plan(slug: str, release: PlanRelease, a: tenancy.Access = Depends(access)):
    """Bedarfsplan für alle Rollen der Wehr freigeben bzw. wieder nur für die Verwaltung zeigen."""
    tenant = a.tenant(slug, ADMIN)
    with tenant.connection() as con:
        con.execute("INSERT INTO setting (key, value) VALUES ('response_plan_public', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value", ("true" if release.public else "false",))
    tenancy.forget_config(slug)
    log.info("Bedarfsplan von %s %s durch %s", slug, "freigegeben" if release.public else "zurückgezogen",
             a.email or "lokal")
    return {"public": release.public}


class Colors(BaseModel):
    colors: dict


@router.post("/api/admin/theme-check")
def theme_check(c: Colors, a: tenancy.Access = Depends(access)):
    """Farben prüfen und die abgeleiteten Töne für die Vorschau liefern (ohne zu speichern)."""
    try:
        colors = theme.normalize(c.colors)
    except ValueError as e:
        return {"problems": [str(e)], "palette": None}
    return {"problems": theme.check(colors), "palette": theme.palette(colors) if colors else None}


class ParseTest(BaseModel):
    line: str
    unit_prefix: str
    own_prefix: str


@router.post("/api/admin/parse-test")
def parse_test(t: ParseTest, a: tenancy.Access = Depends(access)):
    """Testfeld BKS-Kennung: wie wird eine Fahrzeugzeile aus dem Bericht erkannt?"""
    from app import pdf_report
    report = pdf_report.parse_report(t.line, "", "", "test.pdf", t.unit_prefix)
    return {"vehicles": [{"name": v["name"], "call_sign": v["call_sign"],
                          "own": bool(t.own_prefix) and v["name"].startswith(t.unit_prefix + t.own_prefix)}
                         for v in report["vehicles"]]}


# ---------------------------------------------------------------- Logos
@router.put("/api/admin/{slug}/assets/{name}")
def put_asset(slug: str, name: str, file: UploadFile = File(...), a: tenancy.Access = Depends(access)):
    tenant = a.tenant(slug, ADMIN)
    if name not in theme.ASSETS:
        raise HTTPException(404, "Unbekanntes Logo.")
    data = file.file.read(theme.MAX_ASSET_BYTES + 1)
    if len(data) > theme.MAX_ASSET_BYTES:
        _invalid("Das Bild ist größer als 512 KB.")
    content_type = theme.image_type(data)
    if not content_type:
        _invalid("Bitte ein Bild im Format PNG, JPEG oder WebP hochladen.")
    with tenant.connection() as con:
        con.execute("INSERT INTO asset (name, content_type, data, modified) VALUES (?, ?, ?, datetime('now', 'localtime')) "
                    "ON CONFLICT(name) DO UPDATE SET content_type = excluded.content_type, data = excluded.data, "
                    "modified = excluded.modified", (name, content_type, data))
    return {"ok": True}


@router.delete("/api/admin/{slug}/assets/{name}")
def delete_asset(slug: str, name: str, a: tenancy.Access = Depends(access)):
    with a.tenant(slug, ADMIN).connection() as con:
        con.execute("DELETE FROM asset WHERE name = ?", (name,))
    return {"ok": True}


# ---------------------------------------------------------------- Stichwortkatalog
class KeywordIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    terms: str = ""
    active: bool = True


def _keywords_json(tenant):
    with tenant.connection() as con:
        own = tenancy.keywords(con)
    template = [{"code": c, "name": n, "terms": t, "active": True} for c, n, t in domain.KEYWORD_CATALOG]
    return {"custom": own is not None, "keywords": own if own is not None else template,
            "template_missing": len({c for c, _, _ in domain.KEYWORD_CATALOG} - {k["code"] for k in own or template})}


def _changed_keywords(tenant, change):
    with tenant.connection() as con:
        result = change(con)
    tenancy.forget_config(tenant.slug)
    return result


@router.get("/api/admin/{slug}/keywords")
def get_keywords(slug: str, a: tenancy.Access = Depends(access)):
    return _keywords_json(a.tenant(slug, ADMIN))


@router.put("/api/admin/{slug}/keywords/{code}")
def put_keyword(slug: str, code: str, k: KeywordIn, a: tenancy.Access = Depends(access)):
    tenant = a.tenant(slug, ADMIN)
    code = code.strip().upper()
    if not KEYWORD_CODE.fullmatch(code):
        _invalid(f"Stichwort „{code}“: bitte wie B2 oder B2.07 angeben.")
    _changed_keywords(tenant, lambda con: tenancy.save_keyword(con, code, k.name.strip(), k.terms.strip(), k.active))
    return _keywords_json(tenant)


@router.delete("/api/admin/{slug}/keywords/{code}")
def delete_keyword(slug: str, code: str, a: tenancy.Access = Depends(access)):
    tenant = a.tenant(slug, ADMIN)
    _changed_keywords(tenant, lambda con: tenancy.delete_keyword(con, code))
    return _keywords_json(tenant)


@router.post("/api/admin/{slug}/keywords/template")
def keywords_from_template(slug: str, a: tenancy.Access = Depends(access)):
    """Fehlende Stichworte der Vorlage ergänzen."""
    tenant = a.tenant(slug, ADMIN)
    _changed_keywords(tenant, tenancy.add_template_keywords)
    return _keywords_json(tenant)


@router.delete("/api/admin/{slug}/keywords")
def reset_keywords(slug: str, a: tenancy.Access = Depends(access)):
    """Eigenen Katalog verwerfen, wieder die Vorlage verwenden."""
    tenant = a.tenant(slug, ADMIN)
    _changed_keywords(tenant, lambda con: tenancy.replace_keywords(con, []))
    return _keywords_json(tenant)


def read_keyword_file(filename, data):
    """CSV (Semikolon oder Komma) oder XLSX mit den Spalten Stichwort, Bezeichnung, Suchbegriffe -> [(code, name, terms)].
    Eine Kopfzeile wird erkannt und übersprungen."""
    if filename.lower().endswith(".xlsx"):
        sheet = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True).worksheets[0]
        rows = [[str(c) if c is not None else "" for c in row] for row in sheet.iter_rows(values_only=True)]
    else:
        text = data.decode("utf-8-sig", errors="replace")
        dialect = csv.Sniffer().sniff(text[:2048], delimiters=";,\t") if text.strip() else csv.excel
        rows = list(csv.reader(io.StringIO(text), dialect))
    entries, seen = [], set()
    for number, row in enumerate(rows, start=1):
        cells = [c.strip() for c in row] + ["", "", ""]
        code = cells[0].upper().replace(" ", "")
        if not code or (number == 1 and not KEYWORD_CODE.fullmatch(code)):
            continue                            # Leerzeile bzw. Kopfzeile
        if not KEYWORD_CODE.fullmatch(code):
            _invalid(f"Zeile {number}: „{cells[0]}“ ist kein Stichwort wie B2 oder B2.07.")
        if not cells[1]:
            _invalid(f"Zeile {number}: Bezeichnung fehlt.")
        if code in seen:
            _invalid(f"Zeile {number}: {code} steht doppelt in der Datei.")
        seen.add(code)
        entries.append((code, cells[1], cells[2]))
    if not entries:
        _invalid("Die Datei enthält keine Stichworte.")
    return entries


@router.post("/api/admin/{slug}/keywords/import")
def import_keywords(slug: str, mode: str = "preview", file: UploadFile = File(...),
                    a: tenancy.Access = Depends(access)):
    """Katalog aus CSV/XLSX: mode=preview zeigt die Änderungen, merge ergänzt/ändert, replace ersetzt."""
    tenant = a.tenant(slug, ADMIN)
    data = file.file.read(MAX_KEYWORD_FILE + 1)
    if len(data) > MAX_KEYWORD_FILE:
        _invalid("Die Datei ist größer als 2 MB.")
    try:
        entries = read_keyword_file(file.filename or "", data)
    except HTTPException:
        raise
    except Exception as e:  # kaputte Datei
        _invalid(f"Die Datei lässt sich nicht lesen ({e or type(e).__name__}).")
    current = {k["code"]: k for k in _keywords_json(tenant)["keywords"]}
    incoming = {code: (name, terms) for code, name, terms in entries}
    preview = {
        "new": [c for c in incoming if c not in current],
        "changed": [c for c in incoming if c in current and (current[c]["name"], current[c]["terms"]) != incoming[c]],
        "unchanged": sum(1 for c in incoming if c in current and (current[c]["name"], current[c]["terms"]) == incoming[c]),
        "missing": [c for c in current if c not in incoming],
    }
    if mode == "preview":
        return preview
    if mode == "replace":
        _changed_keywords(tenant, lambda con: tenancy.replace_keywords(con, entries))
    elif mode == "merge":
        def merge(con):
            for code, name, terms in entries:
                active = current.get(code, {}).get("active", True)
                tenancy.save_keyword(con, code, name, terms, active)
        _changed_keywords(tenant, merge)
    else:
        _invalid("mode: preview, merge oder replace.")
    log.info("Stichwortkatalog von %s importiert (%s) durch %s", slug, mode, a.email or "lokal")
    return {**preview, **_keywords_json(tenant)}


# ---------------------------------------------------------------- Benutzer und Rollen
def _manages_vg(a, vg_id):
    """Superadmin oder Wehrleiter dieser VG."""
    return a.manages_vg(vg_id)


def _grantable(a, scope, scope_id, vg_id):
    """Rollen, die der Benutzer in diesem Bereich vergeben und entziehen darf."""
    if _manages_vg(a, vg_id):
        return {role for role, (s, _, _) in ROLES.items() if s == scope}
    if scope == "tenant" and any(r["role"] == "lead" and r["scope"] == "tenant" and r["scope_id"] == scope_id
                                 for r in a.roles):
        return tenancy.GRANTABLE["lead"]
    return set()


def _scope_row(con, scope, slug):
    """(scope_id, vg_id, name) eines Bereichs; 404, wenn es ihn nicht gibt."""
    if scope == "tenant":
        row = con.execute("SELECT id, vg_id, name FROM tenant WHERE slug = ?", (slug,)).fetchone()
    else:
        row = con.execute("SELECT id, id AS vg_id, name FROM vg WHERE slug = ?", (slug,)).fetchone()
    if not row:
        raise HTTPException(404, "Wehr bzw. VG nicht gefunden.")
    return row["id"], row["vg_id"], row["name"]


@router.get("/api/admin/memberships")
def get_memberships(a: tenancy.Access = Depends(access)):
    """Zuordnungen in allen Bereichen, in denen der Benutzer Rollen vergeben darf."""
    with tenancy.central() as con:
        rows = con.execute(
            "SELECT m.email, m.scope, m.role, m.scope_id, COALESCE(t.slug, v.slug) AS slug, "
            "COALESCE(t.name, v.name) AS name, COALESCE(t.vg_id, v.id) AS vg_id, a.last_login "
            "FROM membership m JOIN account a ON a.email = m.email "
            "LEFT JOIN tenant t ON m.scope = 'tenant' AND t.id = m.scope_id "
            "LEFT JOIN vg v ON m.scope = 'vg' AND v.id = m.scope_id ORDER BY name, m.email").fetchall()
    result = []
    for r in rows:
        grantable = _grantable(a, r["scope"], r["scope_id"], r["vg_id"])
        if grantable or (r["scope"] == "tenant" and r["slug"] in a.tenants and a.tenants[r["slug"]].can(ADMIN)):
            result.append({"email": r["email"], "scope": r["scope"], "slug": r["slug"], "name": r["name"],
                           "role": r["role"], "label": ROLES.get(r["role"], ("", r["role"]))[1],
                           "last_login": r["last_login"], "editable": r["role"] in grantable})
    return {"memberships": result}


class MembershipIn(BaseModel):
    email: str
    scope: str            # 'tenant' oder 'vg'
    slug: str
    role: str


@router.post("/api/admin/memberships")
def grant_membership(m: MembershipIn, a: tenancy.Access = Depends(access)):
    email = tenancy.normalize_email(m.email)
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        _invalid("Bitte eine gültige E-Mail-Adresse angeben.")
    if m.role not in ROLES or ROLES[m.role][0] != m.scope:
        _invalid("Diese Rolle passt nicht zum Bereich.")
    with tenancy.central() as con:
        scope_id, vg_id, _ = _scope_row(con, m.scope, m.slug)
        existing = con.execute("SELECT role FROM membership WHERE email = ? AND scope = ? AND scope_id = ?",
                               (email, m.scope, scope_id)).fetchone()
        grantable = _grantable(a, m.scope, scope_id, vg_id)
        if m.role not in grantable or (existing and existing["role"] not in grantable):
            raise tenancy.Forbidden("Diese Rolle darfst du hier nicht vergeben.")
        if existing and existing["role"] == "vg_lead" and m.role != "vg_lead":
            _check_last_vg_lead(con, a, scope_id, email)
        tenancy.grant(con, email, m.role, scope_id)
    log.info("Rolle %s für %s in %s %s vergeben durch %s", m.role, email, m.scope, m.slug, a.email or "lokal")
    return get_memberships(a)


def _check_last_vg_lead(con, a, vg_id, email):
    """Den letzten Wehrleiter einer VG entfernt nur der Superadmin."""
    others = con.execute("SELECT COUNT(*) FROM membership WHERE scope = 'vg' AND scope_id = ? AND role = 'vg_lead' "
                         "AND email != ?", (vg_id, email)).fetchone()[0]
    if not others and not a.superadmin:
        raise tenancy.Forbidden("Der letzte Wehrleiter einer VG kann nur vom Superadmin entfernt werden.")


@router.delete("/api/admin/memberships")
def revoke_membership(email: str, scope: str, slug: str, a: tenancy.Access = Depends(access)):
    email = tenancy.normalize_email(email)
    with tenancy.central() as con:
        scope_id, vg_id, _ = _scope_row(con, scope, slug)
        row = con.execute("SELECT role FROM membership WHERE email = ? AND scope = ? AND scope_id = ?",
                          (email, scope, scope_id)).fetchone()
        if not row:
            raise HTTPException(404, "Zuordnung nicht gefunden.")
        if row["role"] not in _grantable(a, scope, scope_id, vg_id):
            raise tenancy.Forbidden("Diese Rolle darfst du hier nicht entziehen.")
        if row["role"] == "vg_lead":
            _check_last_vg_lead(con, a, scope_id, email)
        con.execute("DELETE FROM membership WHERE email = ? AND scope = ? AND scope_id = ?", (email, scope, scope_id))
        con.execute("DELETE FROM account WHERE email = ? AND NOT EXISTS (SELECT 1 FROM membership WHERE email = ?)",
                    (email, email))
    log.info("Rolle %s für %s in %s %s entzogen durch %s", row["role"], email, scope, slug, a.email or "lokal")
    return get_memberships(a)


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
    for t in tenants:
        with db.connection(tenancy.tenant_path(t["slug"])) as con:
            t["incidents"] = con.execute("SELECT COUNT(*) FROM incident").fetchone()[0]
    return {"vgs": vgs, "tenants": tenants}


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
        if t.email:
            tenancy.grant(con, t.email, "lead", tenant_id)
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
        row = con.execute("SELECT id FROM tenant WHERE slug = ?", (slug,)).fetchone()
        if not row:
            raise HTTPException(404, "Wehr nicht gefunden.")
        con.execute("DELETE FROM membership WHERE scope = 'tenant' AND scope_id = ?", (row["id"],))
        con.execute("DELETE FROM tenant WHERE id = ?", (row["id"],))
        con.execute("DELETE FROM account WHERE NOT EXISTS (SELECT 1 FROM membership m WHERE m.email = account.email)")
    source = os.path.dirname(tenancy.tenant_path(slug))
    target = os.path.join(db.DATA_DIR, "deleted", f"{slug}-{dt.datetime.now():%Y%m%d-%H%M%S}")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    shutil.move(source, target)
    tenancy.forget_config(slug)
    log.warning("Wehr %s entfernt durch %s, Daten liegen in %s", slug, a.email or "lokal", target)
    return super_overview(a)
