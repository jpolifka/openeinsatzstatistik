# -*- coding: utf-8 -*-
"""
Fachkonfiguration einer Wehr: Fahrzeuge, Kennungen im BKS-Bericht, Orte, Bedarfsplan.

Jede Wehr hat ihre eigene TenantConfig. Backend und Oberfläche lesen die Werte nur von hier
(die Oberfläche über /api/config, siehe client_config). Was für alle Wehren gilt, steht in domain.py.
"""
import dataclasses
import datetime as dt
from typing import Optional

from app import domain


@dataclasses.dataclass(frozen=True)
class Vehicle:
    """Fahrzeug der Wehr. Ohne Dienstzeitraum ist es unbegrenzt im Dienst."""
    call_sign: str                            # Funkrufname ohne Einheit, z. B. 02/45
    label: str = ""                           # Bezeichnung, z. B. HLF 20
    in_service_from: Optional[str] = None     # ISO-Datum, erster Tag im Dienst
    in_service_until: Optional[str] = None    # ISO-Datum, letzter Tag im Dienst
    replaced_by: Optional[str] = None         # Funkrufname des Nachfolgers
    in_plan_crew: bool = True                 # zählt zur Gesamtstärke des Bedarfsplans (Excel-Spalte AU)

    def in_service_on(self, day: dt.date):
        day = day.isoformat()
        return (not self.in_service_from or self.in_service_from <= day) and \
               (not self.in_service_until or day <= self.in_service_until)

    def in_service_during(self, year):
        return (not self.in_service_from or self.in_service_from[:4] <= str(year)) and \
               (not self.in_service_until or str(year) <= self.in_service_until[:4])


@dataclasses.dataclass(frozen=True)
class TenantConfig:
    name: str                                 # Name der Wehr, z. B. „Feuerwehr Musterstadt“
    fleet: tuple = ()                         # Vehicle in der Reihenfolge der Einsatzübersicht
    # Ersatzfahrzeuge, die bei Werkstattaufenthalt im Block eines anderen geführt werden: {ersatz: block}
    substitutes: dict = dataclasses.field(default_factory=dict)
    unit_prefix: str = ""                     # Fahrzeuge der Einheit im BKS-Bericht, z. B. „FL NR#.ABC “
    own_prefix: str = ""                      # Funkrufnamen der eigenen Wehr, z. B. „02/“
    unit_marker: str = ""                     # Einheit im Bericht, z. B. „FW NR#.ABC 02“
    control_center: str = domain.CONTROL_CENTER
    places: tuple = ()                        # (Name, Namensanfang) für die Zuordnung des Einsatzgebiets
    plan_places: tuple = ()                   # Ausrückebereich laut Feuerwehrbedarfsplan
    plan_min_level: int = domain.PLAN_MIN_LEVEL
    response_limits: tuple = domain.RESPONSE_LIMITS
    default_limit: int = domain.DEFAULT_LIMIT
    second_limit: int = domain.SECOND_LIMIT
    day_hours: tuple = (domain.DAY_START_HOUR, domain.DAY_END_HOUR)
    keywords: tuple = domain.KEYWORD_CATALOG  # (Stichwort.Stufe, Bezeichnung, Suchbegriffe)
    # Einsatznummern: "bks" = Nr. aus dem Bericht (fehlt sie, die nächste freie), "by_date" = nach Beginn
    # durchnummeriert (ein später eingelesener Einsatz rückt an seine Stelle)
    numbering: str = "bks"
    response_plan_public: bool = False        # Bedarfsplan für alle Rollen; sonst nur mit Verwaltungsrecht
    inactive_keywords: tuple = ()             # deaktivierte: nur noch Bezeichnung für alte Einsätze
    colors: dict = dataclasses.field(default_factory=dict)   # {"brand": "#RRGGBB", "brand_dark": …}, siehe theme.py

    # ------------------------------------------------------------ Fahrzeuge
    @property
    def vehicles(self):
        """Funkrufnamen aller Fahrzeuge in der Reihenfolge der Einsatzübersicht."""
        return tuple(v.call_sign for v in self.fleet)

    def vehicles_on(self, day: dt.date):
        """Fahrzeuge, die an diesem Tag im Dienst sind."""
        return tuple(v.call_sign for v in self.fleet if v.in_service_on(day))

    def vehicles_in(self, year, incidents=()):
        """Spalten der Einsatzübersicht eines Jahres: im Jahr mindestens einen Tag im Dienst, oder mit
        Daten in einem der Einsätze."""
        used = {cs for i in incidents for cs in i["vehicles"]}
        return tuple(v.call_sign for v in self.fleet if v.in_service_during(year) or v.call_sign in used)

    def vehicles_for(self, incident):
        """Fahrzeugblöcke eines Einsatzes: am Einsatztag im Dienst oder mit Daten im Einsatz."""
        start = (incident.get("started_at") or "")[:10]
        day = dt.date.fromisoformat(start) if start else None
        return tuple(v.call_sign for v in self.fleet
                     if v.call_sign in incident["vehicles"] or day is None or v.in_service_on(day))

    def with_new_vehicles(self, call_signs, day):
        """Konfiguration mit neu aufgenommenen Fahrzeugen (für die Vorschau vor dem Speichern)."""
        known = set(self.vehicles)
        new = tuple(Vehicle(cs, in_service_from=day.isoformat() if day else None) for cs in call_signs
                    if cs not in known)
        return dataclasses.replace(self, fleet=self.fleet + new) if new else self

    @property
    def excluded_from_plan_crew(self):
        return {v.call_sign for v in self.fleet if not v.in_plan_crew}

    @property
    def own_vehicle_prefix(self):
        """Anfang der Fahrzeugnamen der eigenen Wehr im Bericht, z. B. „FL NR#.ABC 02/“."""
        return self.unit_prefix + self.own_prefix

    def substitute_label(self, vehicle_name, call_sign):
        """Kurzname eines Ersatzfahrzeugs im Block (z. B. '01/23-01'); None, wenn das Stammfahrzeug fuhr."""
        if not vehicle_name or call_sign in vehicle_name:
            return None
        return vehicle_name.replace(self.unit_prefix, "")

    # ------------------------------------------------------------ Orte und Bedarfsplan
    @property
    def place_names(self):
        return tuple(name for name, _ in self.places)

    def area_of(self, place):
        """Einsatzgebiet anhand des Anfangs des Ortsnamens."""
        text = (place or "").lower()
        return next((name for name, prefix in self.places if text.startswith(prefix)), domain.OTHER_AREA)

    def is_plan_relevant(self, incident):
        """Einsatz zählt für den Bedarfsplan: ab Mindest-Alarmstufe im eigenen Ausrückebereich."""
        level = domain.alarm_level(incident["keyword"])
        return level in domain.ALARM_LEVELS and level >= self.plan_min_level and incident["place"] in self.plan_places

    def is_daytime(self, t: dt.time):
        """Wie Excel =UND(E>0,25;E<0,75): die Grenzen selbst zählen zur Nacht."""
        start, end = self.day_hours
        return dt.time(start) < t < dt.time(end)

    # ------------------------------------------------------------ Oberfläche
    def client_config(self):
        """Fachkonstanten für die Oberfläche."""
        return {
            "vehicles": list(self.vehicles),
            "own_prefix": self.own_prefix,
            "substitutes": dict(self.substitutes),
            "categories": [{"code": code, "name": name} for code, name in domain.CATEGORIES],
            "places": list(self.place_names),
            "plan_places": list(self.plan_places),
            "plan_min_level": self.plan_min_level,
            "plan_excluded_vehicles": sorted(self.excluded_from_plan_crew),
            "limits": list(self.response_limits),
            "default_limit": self.default_limit,
            "second_limit": self.second_limit,
            "day_hours": list(self.day_hours),
            "numbering": self.numbering,
            "response_plan_public": self.response_plan_public,
            "fire_alarm_system": ".".join(domain.FIRE_ALARM_SYSTEM),
            "fire_watch": ".".join(domain.FIRE_WATCH),
            "keyword_catalog": [{"code": code, "name": name, "terms": terms, "active": True}
                                for code, name, terms in self.keywords] +
                               [{"code": code, "name": name, "terms": terms, "active": False}
                                for code, name, terms in self.inactive_keywords],
        }


def _unique(values, key=lambda v: v):
    seen, result = set(), []
    for v in values:
        if key(v) not in seen:
            seen.add(key(v))
            result.append(v)
    return tuple(result)


def combine(name, cfgs):
    """Konfiguration für die Gesamtansicht mehrerer Wehren (Anzeige und Statistik über alle).

    Orte, Bedarfsplan-Orte, Fahrzeuge, Zeitgrenzen und Stichworte werden vereinigt; Tagesstunden,
    Standard- und zweite Zeitgrenze kommen von der ersten Wehr. Die Kennzahlen je Einsatz rechnet
    trotzdem jede Wehr mit ihrer eigenen Konfiguration (metrics.evaluate).
    """
    first = cfgs[0]
    return dataclasses.replace(
        first, name=name,
        fleet=_unique((v for c in cfgs for v in c.fleet), key=lambda v: v.call_sign),
        substitutes={k: v for c in reversed(cfgs) for k, v in c.substitutes.items()},
        places=_unique((p for c in cfgs for p in c.places), key=lambda p: p[0]),
        plan_places=_unique(p for c in cfgs for p in c.plan_places),
        plan_min_level=min(c.plan_min_level for c in cfgs),
        response_limits=tuple(sorted({limit for c in cfgs for limit in c.response_limits})),
        keywords=_unique((k for c in cfgs for k in c.keywords), key=lambda k: k[0]),
        numbering=first.numbering if len({c.numbering for c in cfgs}) == 1 else "mixed",
        response_plan_public=all(c.response_plan_public for c in cfgs),
    )
