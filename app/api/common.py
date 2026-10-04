# -*- coding: utf-8 -*-
"""Gemeinsames der Endpunkte: Zugriff, Einsatz-IDs, JSON-Aufbereitung, Filter der Gesamtansicht.
"""
import datetime as dt
import logging
import re
import unicodedata

from app import tenant_config
from app.preview_sessions import PreviewSessions, ReadJobs
from fastapi import HTTPException

from app import auth, domain, metrics, report, store
from app.rbac import DELETE, PEOPLE, PEOPLE_EDIT, PLAN_VIEW, WRITE

log = logging.getLogger("pdf2einsatz")
access = auth.access
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
previews = PreviewSessions()
read_jobs = ReadJobs()          # Berichte, die im Hintergrund gelesen werden


# ---------------------------------------------------------------- Hilfsfunktionen
def safe_filename(name):
    name = unicodedata.normalize("NFC", name or "").replace("\\", "/").split("/")[-1]
    return re.sub(r"[^\w.\- äöüÄÖÜß()]", "_", name) or "datei"


def _rounded(value):
    return round(value, 1) if isinstance(value, float) else value


def incident_key(tenant, incident_id):
    """Eindeutige Einsatz-ID über alle Wehren: "<slug>:<id>"."""
    return f"{tenant.slug}:{incident_id}" if incident_id is not None else None


def parse_incident_key(key):
    slug, _, number = key.partition(":")
    if not number.isdigit():
        raise HTTPException(404, "Einsatz nicht gefunden.")
    return slug, int(number)


def names_for(tenant, incidents):
    """Einsätze ohne Einheitsführung (Name), wenn der Benutzer in der Wehr keine Namen sehen darf (Recht PEOPLE)."""
    return incidents if tenant.can(PEOPLE) else [{**i, "unit_leader": None} for i in incidents]


def incident_json(incident, leaders, tenant, limit=None, cfg=None):
    """Einsatz mit Kennzahlen für die Oberfläche. leaders: store.LeaderNames für die Einheitsführung-Auswahl.
    cfg: abweichende Konfiguration (Vorschau mit neu entdeckten Fahrzeugen), sonst die der Wehr.
    Die Anwesenheit (Namen) nur mit Recht rbac.PEOPLE; sonst nur ihre Anzahl."""
    cfg = cfg or tenant.config
    m = metrics.incident_metrics(incident, cfg, limit)
    vehicles = []
    for call_sign in cfg.vehicles_for(incident):
        v, vm = incident["vehicles"].get(call_sign) or {}, m["vehicles"].get(call_sign) or {}
        vehicles.append({"call_sign": call_sign, "substitute": cfg.substitute_label(v.get("name"), call_sign),
                         "crew": v.get("crew"), "departed": v.get("departed"), "arrived": v.get("arrived"),
                         "alerted": v.get("alerted"), "finished": v.get("finished"),
                         "turnout_min": _rounded(vm.get("turnout_min")),
                         "arrival_min": _rounded(vm.get("arrival_min"))})
    return {
        "id": incident_key(tenant, incident.get("id")),
        "tenant": tenant.slug,
        "current_warnings": report.current_warnings(incident),
        **{name: incident.get(name) for name in ("year", *store.FIELDS, *store.ID_FIELDS, "source", "filename",
                                                 "warnings", "revision")},
        **({} if tenant.can(PEOPLE) else {"unit_leader": None}),     # Einheitsführung ist ein Name
        "bks_url": domain.BKS_REPORT_URL.format(incident["bks_report_id"]) if incident.get("bks_report_id") else None,
        "weekend_or_holiday": bool(incident.get("weekend_or_holiday")),
        **{name: _rounded(m[name]) for name in ("daytime", "duration_min", "turnout_min", "arrival_min", "on_time",
                                                 "crew_on_arrival", "crew_within_limit", "crew_within_second",
                                                 "crew_total")},
        "area": m["area"], "plan_relevant": m["plan_relevant"],     # Filter aus der Auswertung
        "vehicles": vehicles,
        "people": [{"id": p["id"], "name": p["name"], "role": p.get("role"), "vehicle": p.get("vehicle"),
                    "new": p.get("new", False), "leader_name": leaders.spelling(p),
                    "leader": leaders.is_leader(incident.get("unit_leader"), p)} for p in incident["people"]]
        if tenant.can(PEOPLE) else [],
        "people_count": len(incident["people"]),
        "people_visible": tenant.can(PEOPLE),
        "people_editable": tenant.can(PEOPLE_EDIT),
        "can_edit": tenant.can(WRITE),
        "can_delete": tenant.can(DELETE),
    }



def filtered(tenants, only):
    """Wehr-Filter der Gesamtansicht (?tenants=a,b); ohne Filter alle."""
    if not only:
        return tenants
    wanted = set(only.split(","))
    chosen = [t for t in tenants if t.slug in wanted]
    if not chosen:
        raise HTTPException(400, "Keine der gewählten Wehren ist in der Auswahl.")
    return chosen


def latest_year(tenants):
    years = []
    for t in tenants:
        with t.connection() as con:
            years.append(store.latest_year(con))
    return max((y for y in years if y), default=dt.date.today().year)


PLAN_KEYS = ("plan_count", "on_time", "rate", "arrival_min")


def plan_visible(tenant):
    """Bedarfsplan einer Wehr: freigegeben oder mit Recht PLAN_VIEW."""
    return tenant.config.response_plan_public or tenant.can(PLAN_VIEW)


def without_plan(row, visible=False):
    """Kennzahlzeile ohne Bedarfsplan-Werte, solange er nicht sichtbar ist."""
    return row if visible else {**row, **dict.fromkeys(PLAN_KEYS)}


def selection_config(tenants, a):
    """Konfiguration der Auswahl: die der einen Wehr oder die vereinigte der VG-Gesamtansicht."""
    if len(tenants) == 1 and not a.vg:
        return tenants[0].config
    return tenant_config.combine(a.vgs.get(a.vg, "Alle Wehren"), [t.config for t in tenants])
