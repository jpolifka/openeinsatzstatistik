# -*- coding: utf-8 -*-
"""
Verwaltung: Fachkonfiguration, Farben und Logos einer Wehr, Stichwortkatalog, Benutzer und
(für Superadmins) Verbandsgemeinden und Wehren.

Rechte (rbac.py): Einstellungen, Fahrzeuge, Logos und Bedarfsplan-Freigabe brauchen SETTINGS bzw. PLAN_RELEASE,
der Stichwortkatalog KEYWORDS, die Gebührenordnung VG_FEES. SETTINGS und KEYWORDS in einer Rolle der VG
erlauben die Vorgaben für alle Wehren der VG; in einer Rolle der Wehr die Abweichungen dieser Wehr. Rollen vergibt jeder nur
nach der Verteilung seiner Rollen und nur in seinem Bereich, nie sich selbst; Rollen der VG pflegt, wer
ROLES_MANAGE hat, System- und globale Rollen sowie VGs und Wehren nur der Superadmin.
"""
import csv
import dataclasses
import datetime as dt
import io
import json
import logging
import os
import re
from typing import List, Optional

from app import tenant_lifecycle, parser_worker
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app import auth, db, domain, fees, rbac, store, tenancy, theme
from app.rbac import KEYWORDS, PLAN_RELEASE, ROLES_MANAGE, SETTINGS, USERS_VIEW, VG_FEES
from app.bks_common import PERSON_VEHICLE
from app.tenant_config import UNIT_MARKER, TenantConfig, Vehicle, prefixes_of

log = logging.getLogger("pdf2einsatz")
router = APIRouter()

# Funkrufname wie im BKS-Bericht; als Schlüssel eines Ersatzfahrzeugs auch der alte Kurzname (01/23)
VEHICLE_NAME = re.compile(r"[A-ZÄÖÜ0-9][\w#./^ -]{0,59}")
CALL_SIGN = re.compile(r"[\w#./ -]{1,40}")         # Kurzname eines Fahrzeugs (Block), z. B. 02/45
UNSAFE = re.compile(r"[<>\"&]")                     # in Namen nicht nötig, in der Oberfläche heikel
KEYWORD_CODE = re.compile(r"[A-Z]\d(\.\d\d)?")
NUMBERINGS = ("bks", "by_date")
MAX_KEYWORD_FILE = 2 * 1024 * 1024


access = auth.access


def _invalid(message):
    raise HTTPException(422, message)


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
    fleet_version: Optional[str] = None   # Stand der Fahrzeugliste beim Laden (tenancy.fleet_version)


def _types(name):
    return domain.describe_call_sign(name).get("types", [])


def _vehicle_json(v, cfg, used):
    """Fahrzeug der Fahrzeugliste für die Oberfläche (Wehr und Fahrzeuge der VG)."""
    return {"call_sign": v.call_sign, "name": v.name, "description": domain.call_sign_text(v.name),
            "suggested_name": "" if v.name else _suggested_name(v.call_sign, cfg) or "",
            "types": _types(v.name or _suggested_name(v.call_sign, cfg) or v.call_sign),
            "label": v.label, "in_service_from": v.in_service_from,
            "in_service_until": v.in_service_until, "replaced_by": v.replaced_by,
            "in_plan_crew": v.in_plan_crew, "incidents": used.get(v.call_sign, 0)}


def _bks_parts(cfg):
    """(Kennung der VG, Standort) aus der Einheit im Bericht, z. B. („NR#.ABC“, „02“)."""
    m = UNIT_MARKER.fullmatch(cfg.unit_marker.strip())
    return (m.group(1), m.group(2)) if m else (None, None)


def _settings_json(tenant, cfg):
    layer = tenant.layer
    with tenant.connection() as con:
        used = store.vehicles_with_data(con)
        version = tenancy.fleet_version(con)
        overrides = tenancy.config_sources(con)
        assets = {r["name"]: f"/api/branding/{tenant.slug}/{r['name']}?v={r['modified'].replace(' ', 'T')}"
                  for r in con.execute("SELECT name, modified FROM asset")}
    with tenancy.central() as con:
        fee_types = fees.vehicle_types(con, tenant.vg_id)
    bks_code, station = _bks_parts(cfg)
    if not bks_code and "bks_code" not in overrides:   # noch ohne Standort: die Kennung der VG
        bks_code = layer.value("bks_code")
    return {
        "assets": {name: assets.get(name) for name in theme.ASSETS},
        "slug": tenant.slug, "name": cfg.name, "colors": cfg.colors, "fleet_version": version,
        "palette": theme.palette(cfg.colors) if cfg.colors else None,
        "fleet": [_vehicle_json(v, cfg, used) for v in cfg.fleet],
        "unused_data": {cs: n for cs, n in used.items() if cs not in cfg.vehicles},
        "substitutes": cfg.substitutes,
        **{key: getattr(cfg, key) for key in ("unit_prefix", "own_prefix", "unit_marker", "control_center",
                                               "plan_places", "plan_min_level", "response_limits", "default_limit",
                                               "second_limit", "day_hours", "numbering", "response_plan_public")},
        "bks_code": bks_code, "station": station,
        "places": [{"name": n} for n in cfg.places],
        # Vorgaben der VG und die Schlüssel, in denen die Wehr davon abweicht
        "vg": {"slug": tenant.vg_slug, "name": tenant.vg_name},
        "inherited": {key: layer.value(key) for key in tenancy.INHERITED},
        "overrides": sorted(overrides),
        "known_vehicles": [{"name": n, "description": domain.call_sign_text(n), "types": _types(n),
                            "label": fees.suggest_type(_types(n), fee_types)} for n in _known_vehicles(tenant, cfg)],
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
    tenant = a.tenant(slug, SETTINGS)
    return _settings_json(tenant, tenant.config)


def _check_fleet(vehicles, unit_prefix):
    """Fahrzeugliste prüfen; neue Fahrzeuge bekommen ihren Kurznamen aus dem Funkrufnamen."""
    rows = [(v, v.name.strip(), v.call_sign.strip()) for v in vehicles]
    names = [name for _, name, _ in rows if name]
    if len(set(names)) != len(names):
        _invalid("Ein Funkrufname steht doppelt in der Fahrzeugliste.")
    derive = TenantConfig(name="", unit_prefix=unit_prefix)
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
        elif not CALL_SIGN.fullmatch(call_sign):
            _invalid(f"Kurzname „{call_sign}“: nur Buchstaben, Ziffern und . / # -")
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


def _check_substitutes(substitutes, fleet):
    call_signs = [v.call_sign for v in fleet]
    by_name = {v.name: v.call_sign for v in fleet if v.name}
    result = {}
    for sub, block in substitutes.items():
        if not isinstance(block, str):
            _invalid(f"Ersatzfahrzeug {sub}: bitte ein Fahrzeug der Liste wählen.")
        sub, block = sub.strip(), by_name.get(block, block)
        if not VEHICLE_NAME.fullmatch(sub) or block not in call_signs:
            _invalid(f"Ersatzfahrzeug {sub}: der Block {block} muss ein Fahrzeug der Liste sein.")
        result[sub] = block
    return result


def _check_colors(colors):
    try:
        colors = theme.normalize(colors)
    except ValueError as e:
        _invalid(str(e))
    problems = theme.check(colors)
    if problems:
        _invalid(" ".join(problems))
    return colors


def _check_places(places):
    names = [p.name.strip() for p in places]
    if any(not name for name in names) or len({n.lower() for n in names}) != len(names):
        _invalid("Jeder Ort braucht einen eindeutigen Namen.")
    if any(UNSAFE.search(name) for name in names):
        _invalid("Ortsnamen ohne die Zeichen < > \" &.")
    return tuple(names)


def _check_plan(s):
    """Bedarfsplan, Tag und Nummerierung (Wehr wie VG) -> dict für die TenantConfig."""
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
    return {"plan_min_level": s.plan_min_level, "response_limits": tuple(limits), "default_limit": s.default_limit,
            "second_limit": s.second_limit, "day_hours": tuple(s.day_hours), "numbering": s.numbering}


def _check_settings(s: SettingsIn):
    """Fachliche Prüfung -> TenantConfig; Meldungen auf Deutsch (422)."""
    if len(s.name.strip()) < 2:
        _invalid("Bitte den Namen der Wehr angeben.")
    colors = _check_colors(s.colors)
    fleet = _check_fleet(s.fleet, s.unit_prefix)
    substitutes = _check_substitutes(s.substitutes, fleet)
    names = _check_places(s.places)
    if not set(s.plan_places) <= set(names):
        _invalid("Bedarfsplan-Orte müssen in der Ortsliste stehen.")
    unit_marker = s.unit_marker.strip()
    if unit_marker and not prefixes_of(unit_marker):
        _invalid("Einheit im Bericht: wie in der Kopfzeile des Berichts, z. B. FW NR#.ABC 02.")
    # Präfixe ergeben sich aus der Einheit; ohne Einheit bleiben die bisherigen (ältere Einrichtungen)
    unit_prefix, own_prefix = prefixes_of(unit_marker) or (s.unit_prefix, s.own_prefix)
    if own_prefix and not re.fullmatch(r"\d\d/", own_prefix):
        _invalid("Eigener Präfix: zwei Ziffern und Schrägstrich, z. B. 02/.")
    return TenantConfig(
        name=s.name.strip(), colors=colors, substitutes=substitutes, fleet=fleet,
        unit_prefix=unit_prefix, own_prefix=own_prefix, unit_marker=unit_marker,
        control_center=s.control_center.strip() or domain.CONTROL_CENTER,
        places=names, plan_places=tuple(s.plan_places), response_plan_public=s.response_plan_public, **_check_plan(s))


@router.put("/api/admin/{slug}/settings")
def put_settings(slug: str, s: SettingsIn, a: tenancy.Access = Depends(access)):
    tenant = a.tenant(slug, SETTINGS)
    cfg = _check_settings(s)
    if not tenant.can(PLAN_RELEASE):            # Freigabe des Bedarfsplans ist ein eigenes Recht
        cfg = dataclasses.replace(cfg, response_plan_public=tenant.config.response_plan_public)
    with tenant.connection() as con:
        if s.fleet_version and s.fleet_version != tenancy.fleet_version(con):
            raise HTTPException(409, "Die Fahrzeugliste wurde inzwischen geändert (z. B. durch einen Import). "
                                     "Bitte die Seite neu laden und die Änderungen erneut eintragen.")
        tenancy.save_config(con, cfg, tenant.layer)
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


def _managed_vg_id(a, vg_slug, permission=VG_FEES):
    """VG, in der der Benutzer das Recht auf Ebene der VG hat (Gebührenordnung, Vorgaben für die Wehren)."""
    with tenancy.central() as con:
        row = con.execute("SELECT id FROM vg WHERE slug = ?", (vg_slug,)).fetchone()
    if not row or not a.vg_can(row["id"], permission):
        raise tenancy.Forbidden("Keine Berechtigung für diese VG.")
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


# ---------------------------------------------------------------- Vorgaben der VG für ihre Wehren
class VgTenantIn(BaseModel):
    slug: str
    station: Optional[str] = None          # Standortnummer, z. B. 02
    plan_places: Optional[List[str]] = None


class VgSettingsIn(BaseModel):
    bks_code: str = ""
    control_center: str = ""
    places: List[PlaceIn] = []
    plan_min_level: int = domain.PLAN_MIN_LEVEL
    response_limits: List[int] = list(domain.RESPONSE_LIMITS)
    default_limit: int = domain.DEFAULT_LIMIT
    second_limit: int = domain.SECOND_LIMIT
    day_hours: List[int] = [domain.DAY_START_HOUR, domain.DAY_END_HOUR]
    numbering: str = "bks"
    colors: dict = {}
    tenants: List[VgTenantIn] = []


def _vg_settings_json(vg_id):
    """Vorgaben der VG und je Wehr ihre eigenen Werte und Abweichungen (Massenansicht)."""
    with tenancy.central() as con:
        layer = tenancy.load_vg_layer(con, vg_id)
        vg = con.execute("SELECT slug, name FROM vg WHERE id = ?", (vg_id,)).fetchone()
    defaults = {key: layer.value(key) for key in tenancy.INHERITED}
    tenants = []
    for t in tenancy.vg_tenants(vg_id):
        cfg = t.config
        with t.connection() as con:
            overrides = tenancy.config_sources(con)
        bks_code, station = _bks_parts(cfg)
        tenants.append({"slug": t.slug, "name": t.name, "station": station, "unit_marker": cfg.unit_marker,
                        "plan_places": list(cfg.plan_places), "response_plan_public": cfg.response_plan_public,
                        "overrides": {key: _setting_value(cfg, key) for key in sorted(overrides)}})
    return {"vg": {"slug": vg["slug"], "name": vg["name"]}, **defaults,
            "places": [{"name": n} for n in defaults["places"]],
            "palette": theme.palette(defaults["colors"]) if defaults["colors"] else None, "tenants": tenants}


def _setting_value(cfg, key):
    return _bks_parts(cfg)[0] if key == "bks_code" else getattr(cfg, key)


@router.get("/api/admin/vgs/{vg_slug}/settings")
def get_vg_settings(vg_slug: str, a: tenancy.Access = Depends(access)):
    return _vg_settings_json(_managed_vg_id(a, vg_slug, SETTINGS))


@router.put("/api/admin/vgs/{vg_slug}/settings")
def put_vg_settings(vg_slug: str, s: VgSettingsIn, a: tenancy.Access = Depends(access)):
    """Vorgaben der VG speichern; Abweichungen der Wehren, die jetzt der Vorgabe entsprechen, entfallen.
    Standort und Ausrückebereich je Wehr gleich mit."""
    vg_id = _managed_vg_id(a, vg_slug, SETTINGS)
    bks_code = s.bks_code.strip()
    if bks_code and not re.fullmatch(r"[^\s<>\"&]{1,30}", bks_code):
        _invalid("Kennung der VG: wie in der Kopfzeile des Berichts, z. B. NR#.ABC aus „FW NR#.ABC 02“.")
    places = _check_places(s.places)
    values = {"bks_code": bks_code or None, "control_center": s.control_center.strip() or None,
              "places": list(places), "colors": _check_colors(s.colors), **_check_plan(s)}
    tenants = {t.slug: t for t in tenancy.vg_tenants(vg_id)}
    if not bks_code and any((t.station or "").strip() for t in s.tenants):
        _invalid("Für den Standort einer Wehr bitte zuerst die Kennung der VG angeben.")
    for t in s.tenants:
        if t.slug not in tenants:
            raise HTTPException(404, "Wehr nicht in dieser VG.")
        if t.station is not None and t.station.strip() and not re.fullmatch(r"\d\d", t.station.strip()):
            _invalid(f"{tenants[t.slug].name}: Standort zweistellig, z. B. 02.")
        with tenants[t.slug].connection() as con:     # eigene Orte der Wehr statt der Vorgabe?
            own = "places" in tenancy.config_sources(con)
        if t.plan_places is not None and not set(t.plan_places) <= set(tenants[t.slug].config.places if own else places):
            _invalid(f"{tenants[t.slug].name}: Bedarfsplan-Orte müssen in der Ortsliste stehen.")
    with tenancy.central() as con:
        tenancy.save_vg_settings(con, vg_id, values)
        layer = tenancy.load_vg_layer(con, vg_id)
    changes = {t.slug: t for t in s.tenants}
    for slug, tenant in tenants.items():
        with tenant.connection() as con:
            tenancy.prune_overrides(con, layer)
            change = changes.get(slug)
            if change:
                tenancy.save_tenant_values(con, {
                    **({"station": change.station.strip() or None} if change.station is not None else {}),
                    **({"plan_places": list(change.plan_places)} if change.plan_places is not None else {})})
    tenancy.forget_vg_config(vg_id)
    log.info("Vorgaben der VG %s geändert durch %s", vg_slug, a.email or "lokal")
    return _vg_settings_json(vg_id)


# ---------------------------------------------------------------- Fahrzeuge aller Wehren der VG
class VgFleetTenantIn(BaseModel):
    slug: str
    fleet: List[VehicleIn] = []
    substitutes: dict = {}
    fleet_version: Optional[str] = None


class VgFleetIn(BaseModel):
    tenants: List[VgFleetTenantIn]


def _vg_fleet_json(vg_id):
    """Alle Fahrzeuge der VG in einer Tabelle: die der Fahrzeuglisten der Wehren und die übrigen Funkrufnamen
    aus den Berichten (Stammdatensätze und Einsätze), die noch keiner Wehr gehören."""
    tenants = tenancy.vg_tenants(vg_id)
    with tenancy.central() as con:
        fee_types = fees.vehicle_types(con, vg_id)
        layer = tenancy.load_vg_layer(con, vg_id)
        seen = {v.get("name") or "" for (vehicles,) in con.execute(
            "SELECT vehicles FROM master_record WHERE vg_id = ?", (vg_id,)) for v in json.loads(vehicles)}
    result, assigned = [], set()
    for t in tenants:
        cfg = t.config
        with t.connection() as con:
            used = store.vehicles_with_data(con)
            version = tenancy.fleet_version(con)
            seen.update(r[0] for r in con.execute("SELECT DISTINCT name FROM vehicle WHERE name <> ''"))
        vehicles = [_vehicle_json(v, cfg, used) for v in cfg.fleet]
        assigned.update(v["name"] or v["suggested_name"] for v in vehicles)
        assigned.update(cfg.substitutes)
        result.append({"slug": t.slug, "name": t.name, "fleet_version": version, "fleet": vehicles,
                       "substitutes": cfg.substitutes, "unit_prefix": cfg.unit_prefix,
                       "unused_data": {cs: n for cs, n in used.items() if cs not in cfg.vehicles}})
    centers = {t.config.control_center for t in tenants}
    code = layer.value("bks_code")
    prefixes = tuple({t["unit_prefix"] for t in result if t["unit_prefix"]} | ({f"FL {code} "} if code else set()))
    unassigned = [{"name": n, "description": domain.call_sign_text(n), "types": _types(n),
                   "vg": bool(prefixes) and n.startswith(prefixes),
                   "label": fees.suggest_type(_types(n), fee_types)}
                  for n in sorted(seen - assigned - centers) if domain.describe_call_sign(n)]
    return {"tenants": result, "unassigned": unassigned, "fee_types": fee_types,
            "call_sign_directory": domain.CALL_SIGN_DIRECTORY_URL}


@router.get("/api/admin/vgs/{vg_slug}/fleet")
def get_vg_fleet(vg_slug: str, a: tenancy.Access = Depends(access)):
    return _vg_fleet_json(_managed_vg_id(a, vg_slug, SETTINGS))


def _with_legacy_names(vehicles, cfg):
    """Fahrzeug, das aus einer anderen Wehr kommt (ohne Kurznamen), auf einen alten Eintrag dieser Wehr mit
    gleichem Kurznamen, aber ohne Funkrufnamen legen: dort nur den Namen ergänzen."""
    unnamed = {v.call_sign.strip(): v for v in vehicles if v.call_sign.strip() and not v.name.strip()}
    result = []
    for v in vehicles:
        legacy = cfg.block_of(v.name.strip()) if v.name.strip() and not v.call_sign.strip() else None
        if legacy in unnamed:
            unnamed[legacy].name = v.name.strip()
            continue
        result.append(v)
    return result


@router.put("/api/admin/vgs/{vg_slug}/fleet")
def put_vg_fleet(vg_slug: str, f: VgFleetIn, a: tenancy.Access = Depends(access)):
    """Fahrzeuglisten mehrerer Wehren der VG auf einmal: erst alle prüfen, dann je Wehr speichern. Wechselt ein
    Fahrzeug die Wehr, bleiben Einsätze mit seinen Daten bei der bisherigen Wehr."""
    vg_id = _managed_vg_id(a, vg_slug, SETTINGS)
    tenants = {t.slug: t for t in tenancy.vg_tenants(vg_id)}
    checked, names = [], {}
    for entry in f.tenants:
        tenant = tenants.get(entry.slug)
        if not tenant:
            raise HTTPException(404, "Wehr nicht in dieser VG.")
        cfg = tenant.config
        try:
            fleet = _check_fleet(_with_legacy_names(entry.fleet, cfg), cfg.unit_prefix)
            substitutes = _check_substitutes(entry.substitutes, fleet)
        except HTTPException as e:
            raise HTTPException(e.status_code, f"{tenant.name}: {e.detail}")
        for v in fleet:
            if v.name and names.setdefault(v.name, tenant.name) != tenant.name:
                _invalid(f"{v.name} steht in den Fahrzeuglisten von {names[v.name]} und {tenant.name}.")
        checked.append((tenant, entry.fleet_version, dataclasses.replace(cfg, fleet=fleet, substitutes=substitutes)))
    for tenant, version, _ in checked:
        with tenant.connection() as con:
            if version and version != tenancy.fleet_version(con):
                raise HTTPException(409, f"Die Fahrzeugliste von {tenant.name} wurde inzwischen geändert (z. B. "
                                         f"durch einen Import). Bitte die Seite neu laden und die Änderungen erneut eintragen.")
    for tenant, _, cfg in checked:
        layer = tenant.layer
        with tenant.connection() as con:
            tenancy.save_config(con, cfg, layer)
        tenancy.forget_config(tenant.slug)
    log.info("Fahrzeuge der VG %s geändert (%s) durch %s", vg_slug, ", ".join(t.slug for t, _, _ in checked),
             a.email or "lokal")
    return _vg_fleet_json(vg_id)


class PlanRelease(BaseModel):
    public: bool


@router.put("/api/admin/{slug}/response-plan")
def release_response_plan(slug: str, release: PlanRelease, a: tenancy.Access = Depends(access)):
    """Bedarfsplan für alle Rollen der Wehr freigeben bzw. wieder nur für die Verwaltung zeigen."""
    tenant = a.tenant(slug, PLAN_RELEASE)
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
    line: str = Field(max_length=100_000)     # beliebiger Text aus einem Bericht
    unit_marker: str = ""
    vg: Optional[str] = None                  # Erkennung über alle Wehren dieser VG (gespeicherter Stand)


@router.post("/api/admin/parse-test")
def parse_test(t: ParseTest, a: tenancy.Access = Depends(access)):
    """Testfeld BKS-Kennung: Funkrufnamen und Einheiten in einem Text aus dem Bericht finden und zuordnen,
    wie es die Einstellungen (noch ungespeichert) täten."""
    names = dict.fromkeys(PERSON_VEHICLE.findall(t.line))
    units = dict.fromkeys(m.group(0) for m in re.finditer(UNIT_MARKER.pattern + r"\b", t.line))
    if t.vg:
        configs = [(x.name, x.config) for x in tenancy.vg_tenants(_managed_vg_id(a, t.vg, SETTINGS))]
        owner = lambda n: next((name for name, cfg in configs if cfg.is_own(n)), None)
        block = lambda n: next(({"tenant": name, "call_sign": cfg.block_of(n)} for name, cfg in configs
                                if cfg.vehicle(cfg.block_of(n) or "")), None)
        return {"vehicles": [{"name": n, "tenant": owner(n), "block": block(n), "description": domain.call_sign_text(n)}
                             for n in names],
                "units": [{"unit": u, "tenant": next((name for name, cfg in configs if cfg.unit_marker == u), None)}
                          for u in units]}
    unit_marker = t.unit_marker.strip()
    unit_prefix, own_prefix = prefixes_of(unit_marker) or ("", "")
    cfg = TenantConfig(name="", unit_prefix=unit_prefix, own_prefix=own_prefix, unit_marker=unit_marker)
    return {"vehicles": [{"name": n, "call_sign": cfg.block_of(n), "own": cfg.is_own(n),
                          "description": domain.call_sign_text(n)} for n in names],
            "units": [{"unit": u, "own": u == unit_marker} for u in units]}


# ---------------------------------------------------------------- Logos
@router.put("/api/admin/{slug}/assets/{name}")
def put_asset(slug: str, name: str, file: UploadFile = File(...), a: tenancy.Access = Depends(access)):
    tenant = a.tenant(slug, SETTINGS)
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
    with a.tenant(slug, SETTINGS).connection() as con:
        con.execute("DELETE FROM asset WHERE name = ?", (name,))
    return {"ok": True}


# ---------------------------------------------------------------- Stichwortkatalog
class KeywordIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    terms: str = ""
    active: bool = True


class _Catalog:
    """Stichwortkatalog einer Wehr (Abweichungen von der VG) oder einer VG (Vorgabe für ihre Wehren)."""

    def __init__(self, tenant=None, vg_id=None):
        self.tenant, self.vg_id = tenant, vg_id

    def entries(self):
        """Wirksamer Katalog [{code, name, terms, active, source}]."""
        if self.tenant:
            layer = self.tenant.layer
            with self.tenant.connection() as con:
                return tenancy.tenant_keywords(con, layer)
        with tenancy.central() as con:
            layer = tenancy.load_vg_layer(con, self.vg_id)
        return [{**k, "source": "vg"} for k in layer.keyword_list]

    def save(self, entries):
        if self.tenant:
            layer = self.tenant.layer
            with self.tenant.connection() as con:
                tenancy.save_tenant_keywords(con, entries, layer)
            tenancy.forget_config(self.tenant.slug)
        else:
            with tenancy.central() as con:
                tenancy.save_vg_keywords(con, self.vg_id, entries)
            tenancy.forget_vg_config(self.vg_id)

    def reset(self):
        """Wehr: alle Abweichungen aufheben; VG: wieder die Vorlage."""
        if self.tenant:
            with self.tenant.connection() as con:
                con.execute("DELETE FROM keyword")
            tenancy.forget_config(self.tenant.slug)
        else:
            with tenancy.central() as con:
                tenancy.save_vg_keywords(con, self.vg_id, None)
            tenancy.forget_vg_config(self.vg_id)

    def json(self):
        entries = self.entries()
        result = {"keywords": entries, "custom": any(k["source"] != "vg" for k in entries),
                  "template_missing": len({c for c, _, _ in domain.KEYWORD_CATALOG} - {k["code"] for k in entries})}
        if self.tenant:
            result["slug"] = self.tenant.slug
        else:                                   # je Stichwort die Wehren, die abweichen
            with tenancy.central() as con:
                result["custom"] = con.execute("SELECT 1 FROM vg_keyword WHERE vg_id = ? LIMIT 1",
                                               (self.vg_id,)).fetchone() is not None
            deviations = {}
            for t in tenancy.vg_tenants(self.vg_id):
                for k in _Catalog(t).entries():
                    if k["source"] != "vg":
                        deviations.setdefault(k["code"], []).append(
                            {"tenant": t.name, "kind": "off" if not k["active"] and k["source"] == "changed"
                             else k["source"]})
            result["deviations"] = deviations
            known = {k["code"] for k in entries}
            result["tenant_only"] = sorted(c for c in deviations if c not in known)
        return result

    def put(self, code, name, terms, active):
        entries = self.entries()
        entry = {"code": code, "name": name, "terms": terms, "active": active}
        if any(k["code"] == code for k in entries):
            entries = [entry if k["code"] == code else k for k in entries]
        else:
            entries.append(entry)
        self.save(entries)

    def delete(self, code):
        """Wehr: eigenes Stichwort löschen, eine Abweichung aufheben bzw. ein Stichwort der VG gilt hier nicht."""
        if self.tenant:
            with self.tenant.connection() as con:
                own = con.execute("DELETE FROM keyword WHERE code = ?", (code,)).rowcount
            if own:
                return tenancy.forget_config(self.tenant.slug)
        self.save([k for k in self.entries() if k["code"] != code])


def _catalog(a, slug):
    return _Catalog(tenant=a.tenant(slug, KEYWORDS))


def _vg_catalog(a, vg_slug):
    return _Catalog(vg_id=_managed_vg_id(a, vg_slug, KEYWORDS))


def _keyword_code(code):
    code = code.strip().upper()
    if not KEYWORD_CODE.fullmatch(code):
        _invalid(f"Stichwort „{code}“: bitte wie B2 oder B2.07 angeben.")
    return code


@router.get("/api/admin/{slug}/keywords")
def get_keywords(slug: str, a: tenancy.Access = Depends(access)):
    return _catalog(a, slug).json()


@router.get("/api/admin/vgs/{vg_slug}/keywords")
def get_vg_keywords(vg_slug: str, a: tenancy.Access = Depends(access)):
    return _vg_catalog(a, vg_slug).json()


@router.put("/api/admin/{slug}/keywords/{code}")
def put_keyword(slug: str, code: str, k: KeywordIn, a: tenancy.Access = Depends(access)):
    catalog = _catalog(a, slug)
    catalog.put(_keyword_code(code), k.name.strip(), k.terms.strip(), k.active)
    return catalog.json()


@router.put("/api/admin/vgs/{vg_slug}/keywords/{code}")
def put_vg_keyword(vg_slug: str, code: str, k: KeywordIn, a: tenancy.Access = Depends(access)):
    catalog = _vg_catalog(a, vg_slug)
    catalog.put(_keyword_code(code), k.name.strip(), k.terms.strip(), k.active)
    return catalog.json()


@router.delete("/api/admin/{slug}/keywords/{code}")
def delete_keyword(slug: str, code: str, a: tenancy.Access = Depends(access)):
    catalog = _catalog(a, slug)
    catalog.delete(code)
    return catalog.json()


@router.delete("/api/admin/vgs/{vg_slug}/keywords/{code}")
def delete_vg_keyword(vg_slug: str, code: str, a: tenancy.Access = Depends(access)):
    catalog = _vg_catalog(a, vg_slug)
    catalog.delete(code)
    return catalog.json()


def _add_template(catalog):
    """Fehlende Stichworte der Vorlage ergänzen."""
    entries = catalog.entries()
    known = {k["code"] for k in entries}
    catalog.save(entries + [{"code": c, "name": n, "terms": t, "active": True}
                            for c, n, t in domain.KEYWORD_CATALOG if c not in known])
    return catalog.json()


@router.post("/api/admin/{slug}/keywords/template")
def keywords_from_template(slug: str, a: tenancy.Access = Depends(access)):
    return _add_template(_catalog(a, slug))


@router.post("/api/admin/vgs/{vg_slug}/keywords/template")
def vg_keywords_from_template(vg_slug: str, a: tenancy.Access = Depends(access)):
    return _add_template(_vg_catalog(a, vg_slug))


@router.delete("/api/admin/{slug}/keywords")
def reset_keywords(slug: str, a: tenancy.Access = Depends(access)):
    """Alle Abweichungen der Wehr aufheben: wieder der Katalog der VG."""
    catalog = _catalog(a, slug)
    catalog.reset()
    return catalog.json()


@router.delete("/api/admin/vgs/{vg_slug}/keywords")
def reset_vg_keywords(vg_slug: str, a: tenancy.Access = Depends(access)):
    """Katalog der VG verwerfen, wieder die Vorlage verwenden."""
    catalog = _vg_catalog(a, vg_slug)
    catalog.reset()
    return catalog.json()


def read_keyword_file(filename, data):
    """CSV (Semikolon oder Komma) oder XLSX mit den Spalten Stichwort, Bezeichnung, Suchbegriffe -> [(code, name, terms)].
    Eine Kopfzeile wird erkannt und übersprungen."""
    if filename.lower().endswith(".xlsx"):
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".xlsx") as file:
            file.write(data)
            file.flush()
            sheets = parser_worker.read("xlsx", file.name)
        rows = [[str(c) if c is not None else "" for c in row] for row in next(iter(sheets.values()), [])]
    else:
        text = data.decode("utf-8-sig", errors="replace")
        dialect = csv.Sniffer().sniff(text[:2048], delimiters=";,\t") if text.strip() else csv.excel
        rows = list(csv.reader(io.StringIO(text), dialect))
    entries, seen = [], set()
    if len(rows) > 5000:
        _invalid("Der Stichwortkatalog darf höchstens 5000 Zeilen enthalten.")
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


def _import_keywords(catalog, mode, file, who):
    """Katalog aus CSV/XLSX: mode=preview zeigt die Änderungen, merge ergänzt/ändert, replace ersetzt."""
    data = file.file.read(MAX_KEYWORD_FILE + 1)
    if len(data) > MAX_KEYWORD_FILE:
        _invalid("Die Datei ist größer als 2 MB.")
    try:
        entries = read_keyword_file(file.filename or "", data)
    except HTTPException:
        raise
    except Exception as e:  # kaputte Datei
        _invalid(f"Die Datei lässt sich nicht lesen ({e or type(e).__name__}).")
    current = {k["code"]: k for k in catalog.entries()}
    incoming = {code: (name, terms) for code, name, terms in entries}
    preview = {
        "new": [c for c in incoming if c not in current],
        "changed": [c for c in incoming if c in current and (current[c]["name"], current[c]["terms"]) != incoming[c]],
        "unchanged": sum(1 for c in incoming if c in current and (current[c]["name"], current[c]["terms"]) == incoming[c]),
        "missing": [c for c in current if c not in incoming],
    }
    if mode == "preview":
        return preview
    rows = [{"code": code, "name": name, "terms": terms, "active": current.get(code, {}).get("active", True)}
            for code, name, terms in entries]
    if mode == "replace":
        catalog.save(rows)
    elif mode == "merge":
        new = {r["code"]: r for r in rows}
        catalog.save([new.pop(k["code"], k) for k in current.values()] + list(new.values()))
    else:
        _invalid("mode: preview, merge oder replace.")
    log.info("Stichwortkatalog %s importiert (%s) durch %s",
             catalog.tenant.slug if catalog.tenant else f"der VG {catalog.vg_id}", mode, who or "lokal")
    return {**preview, **catalog.json()}


@router.post("/api/admin/{slug}/keywords/import")
def import_keywords(slug: str, mode: str = "preview", file: UploadFile = File(...),
                    a: tenancy.Access = Depends(access)):
    return _import_keywords(_catalog(a, slug), mode, file, a.email)


@router.post("/api/admin/vgs/{vg_slug}/keywords/import")
def import_vg_keywords(vg_slug: str, mode: str = "preview", file: UploadFile = File(...),
                       a: tenancy.Access = Depends(access)):
    return _import_keywords(_vg_catalog(a, vg_slug), mode, file, a.email)


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
            "COALESCE(t.name, v.name) AS name, COALESCE(t.vg_id, v.id) AS vg_id, a.last_login "
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
                           "role": role.key, "label": role.label, "last_login": r["last_login"],
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


# ---------------------------------------------------------------- Rollen
def _held(a, roles):
    """Eigene Rollen samt Vorfahren – die ändert man nicht selbst."""
    return set().union(*(roles.chain(r["role_id"]) for r in a.roles)) if a.roles else set()


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
        try:
            rbac.save_role(con, rbac.Roles(con), None, vg_id=vg_id, scope=r.scope, label=r.label,
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
