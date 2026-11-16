# -*- coding: utf-8 -*-
"""Verwaltung: Einstellungen, Bedarfsplan-Freigabe, Farben und Logos einer Wehr.
"""
import dataclasses
import datetime as dt
import json
import re
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app import domain, fees, store, tenancy, theme
from app.rbac import PLAN_RELEASE, SETTINGS
from app.bks_common import PERSON_VEHICLE
from app.tenant_config import UNIT_MARKER, TenantConfig, Vehicle, prefixes_of

from app.admin.common import _invalid, _managed_vg_id, access, log

router = APIRouter()

# Funkrufname wie im BKS-Bericht; als Schlüssel eines Ersatzfahrzeugs auch der alte Kurzname (01/23)
VEHICLE_NAME = re.compile(r"[A-ZÄÖÜ0-9][\w#./^ -]{0,59}")
CALL_SIGN = re.compile(r"[\w#./ -]{1,40}")         # Kurzname eines Fahrzeugs (Block), z. B. 02/45
UNSAFE = re.compile(r"[<>\"&]")                     # in Namen nicht nötig, in der Oberfläche heikel
NUMBERINGS = ("bks", "by_date")


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
        "assets": {name: assets.get(name) for name in (*theme.ASSETS, *theme.FONTS)},
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
        "known_places": known_places(tenant.vg_id, [tenant]),
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


def known_places(vg_id, tenants):
    """Orte und Ortsteile aus Berichten zur Auswahl in der Ortsliste: Stammdatensätze der VG (personenfrei) und
    Einsätze der Wehren, alphabetisch."""
    names = set()
    with tenancy.central() as con:
        for town, district in con.execute("SELECT town, district FROM master_record WHERE vg_id = ?", (vg_id,)):
            names.update((town, district))
    for t in tenants:
        with t.connection() as con:
            names.update(r[0] for r in con.execute("SELECT DISTINCT place FROM incident"))
    return sorted(n.strip() for n in names if n and n.strip())


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
        _invalid("Die zweite Zeitgrenze muss über den Zeitgrenzen für das Eintreffen liegen.")
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
        _invalid("Orte für die Auswertung des Eintreffens müssen in der Ortsliste stehen.")
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
    line: str = Field(max_length=5_000)       # ein Textausschnitt aus einem Bericht (Zeilen sind kurz)
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
    if name not in theme.ASSETS and name not in theme.FONTS:
        raise HTTPException(404, "Unbekanntes Logo.")
    if name in theme.FONTS:
        data = file.file.read(theme.MAX_FONT_BYTES + 1)
        if len(data) > theme.MAX_FONT_BYTES:
            _invalid("Die Schriftdatei ist größer als 1 MB.")
        content_type = theme.font_type(data)
        if not content_type:
            _invalid("Bitte eine Schriftdatei im Format WOFF2, WOFF, TTF oder OTF hochladen.")
    else:
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


