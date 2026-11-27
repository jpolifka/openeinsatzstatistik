# -*- coding: utf-8 -*-
"""Verwaltung auf Ebene der VG: Gebührenordnung, Vorgaben für die Wehren, gemeinsame Fahrzeugliste.
"""
import dataclasses
import json
import re
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app import domain, fees, store, tenancy, theme
from app.bks_common import UNIT_ID
from app.rbac import SETTINGS

from app.admin.common import _invalid, _managed_vg_id, access, log
from app.admin.settings import (PlaceIn, known_places, VehicleIn, _bks_parts, _check_colors, _check_fleet, _check_places,
                                _check_plan, _check_substitutes, _types, _vehicle_json)

router = APIRouter()


# ---------------------------------------------------------------- Gebührenordnung der VG
class ScheduleIn(BaseModel):
    name: str
    valid_from: str
    rates: dict


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
    control_center_2: str = ""
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
            "known_places": known_places(vg_id, tenancy.vg_tenants(vg_id)),
            "palette": theme.palette(defaults["colors"]) if defaults["colors"] else None, "tenants": tenants}


def _setting_value(cfg, key):
    return _bks_parts(cfg)[0] if key == "bks_code" else getattr(cfg, key)


@router.get("/api/admin/vgs/{vg_slug}/settings")
def get_vg_settings(vg_slug: str, a: tenancy.Access = Depends(access)):
    return _vg_settings_json(_managed_vg_id(a, vg_slug, SETTINGS))


def _current_bks_code(vg_id):
    """Bisher gespeicherte Kennung der VG (ältere Einträge ohne Kreiskürzel bleiben gültig)."""
    with tenancy.central() as con:
        return tenancy.load_vg_layer(con, vg_id).value("bks_code") or ""


@router.put("/api/admin/vgs/{vg_slug}/settings")
def put_vg_settings(vg_slug: str, s: VgSettingsIn, a: tenancy.Access = Depends(access)):
    """Vorgaben der VG speichern; Abweichungen der Wehren, die jetzt der Vorgabe entsprechen, entfallen.
    Standort und Ausrückebereich je Wehr gleich mit."""
    vg_id = _managed_vg_id(a, vg_slug, SETTINGS)
    bks_code = s.bks_code.strip()
    if bks_code and not UNIT_ID.fullmatch(bks_code) and bks_code != _current_bks_code(vg_id):
        _invalid("Kennung der VG: Kreis und Gemeinde wie in der Kopfzeile des Berichts, z. B. MYK.ABC aus "
                 "„FW MYK.ABC 02“ (bei gleichem Zeichen von Stadt und Landkreis mit „#“, z. B. NR#.ABC).")
    places = _check_places(s.places)
    values = {"bks_code": bks_code or None, "control_center": s.control_center.strip() or None,
              "control_center_2": s.control_center_2.strip() or None,
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
            _invalid(f"{tenants[t.slug].name}: Orte für die Auswertung des Eintreffens müssen in der Ortsliste stehen.")
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
    centers = {c for t in tenants for c in t.config.control_centers}
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


