# -*- coding: utf-8 -*-
"""
Auswertungen – dieselben Regeln wie die Formeln der Einsatzübersicht:

  Einsatz je Zeile   D, G, O/Q/T/V/…, AM, AO–AU     -> incident_metrics()
  Blatt Statistik    Stichworte, Stufen, Orte, …     -> statistics()
  Blatt Auswertung   Feuerwehrbedarfsplan Pos. 8.4   -> response_plan()
  Blatt Anwesenheit  Stärke, Gesamtstunden           -> attendance_overview()

Die drei Blatt-Auswertungen bekommen evaluate(einsätze, cfg), damit die Kennzahlen je
Einsatz nur einmal berechnet werden. cfg ist die TenantConfig der Wehr, zu der die Einsätze gehören.
"""
import datetime as dt

from app import domain
from app.timeutil import parse_iso, seconds_of_day

WEEKDAYS = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")
MONTHS = ("Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez")


def time_windows(cfg):
    """Zeitfenster des Bedarfsplans: (Schlüssel, Tagart, Uhrzeit, Wochenende/Feiertag, Tag)."""
    start, end = cfg.day_hours
    day, night = f"{start:02d}:00 – {end:02d}:00 Uhr", f"{end:02d}:00 – {start:02d}:00 Uhr"
    return (("weekday_day", "Werktag", day, False, True),
            ("weekday_night", "Werktag", night, False, False),
            ("weekend_day", "Sa, So, Feiertag", day, True, True),
            ("weekend_night", "Sa, So, Feiertag", night, True, False))


# Toleranzen wie in den Excel-Formeln (Gleitkomma-Minuten)
_ON_TIME_TOLERANCE = 0.0001
_WINDOW_TOLERANCE = 0.001


def _average(values):
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 2) if values else None


def _share(part, total, digits=3):
    return round(part / total, digits) if total else None


# ---------------------------------------------------------------- je Einsatz
def _minutes_after(start_seconds, time_text):
    """Minuten ab Einsatzbeginn wie Excel MOD(…;1): über Mitternacht weitergezählt."""
    if not time_text or start_seconds is None:
        return None
    return ((seconds_of_day(time_text) - start_seconds) % 86400) / 60


def incident_metrics(incident, cfg, limit=None):
    """Formeln der Einsatzzeile."""
    limit = limit or cfg.default_limit
    start, end = parse_iso(incident["started_at"]), parse_iso(incident["ended_at"])
    start_seconds = seconds_of_day(start) if start else None
    duration = (end - start).total_seconds() / 60 if start and end and end >= start else None

    vehicles = {}
    for call_sign in cfg.vehicles:
        v = incident["vehicles"].get(call_sign)
        if v:
            vehicles[call_sign] = {"crew": v["crew"] or 0,
                                   "turnout_min": _minutes_after(start_seconds, v["departed"]),
                                   "arrival_min": _minutes_after(start_seconds, v["arrived"])}

    turnouts = [v["turnout_min"] for v in vehicles.values() if v["turnout_min"] is not None]
    arrivals = [v["arrival_min"] for v in vehicles.values() if v["arrival_min"] is not None]
    turnout = min(turnouts) if turnouts else None     # AO: schnellstes Fahrzeug
    first = min(arrivals) if arrivals else None       # AP: erstes Fahrzeug vor Ort

    def crew_arriving(condition):
        return sum(v["crew"] for v in vehicles.values() if v["arrival_min"] is not None and condition(v["arrival_min"]))

    on_arrival = within_limit = within_second = None
    if first is not None:
        window_end = limit + _WINDOW_TOLERANCE
        second_end = cfg.second_limit + _WINDOW_TOLERANCE
        on_arrival = crew_arriving(lambda m: m == first)                          # AR
        within_limit = crew_arriving(lambda m: first < m <= window_end)           # AS
        within_second = crew_arriving(lambda m: m > first and limit < m <= second_end)  # AT
    return {
        "daytime": bool(start) and cfg.is_daytime(start.time()),                 # D
        "duration_min": duration,                                                 # G
        "vehicles": vehicles,
        "turnout_min": turnout,
        "arrival_min": first,
        "on_time": first <= limit + _ON_TIME_TOLERANCE if first is not None else None,   # AQ
        "crew_on_arrival": on_arrival,
        "crew_within_limit": within_limit,
        "crew_within_second": within_second,
        "crew_plan_total": sum(v["crew"] for cs, v in vehicles.items()
                               if cs not in cfg.excluded_from_plan_crew),               # AU
        "crew_total": sum(v["crew"] for v in vehicles.values()) + (incident["station_staff"] or 0),  # AM
        "attendees": len(incident["people"]),
        # Zuordnungen nach den Regeln der eigenen Wehr – so lassen sich Einsätze mehrerer Wehren zusammenführen
        "area": cfg.area_of(incident["place"]),
        "plan_relevant": cfg.is_plan_relevant(incident),
    }


def evaluate(incidents, cfg, limit=None):
    """[(einsatz, kennzahlen)] – Eingabe für die Blatt-Auswertungen."""
    return [(i, incident_metrics(i, cfg, limit)) for i in incidents]


# ---------------------------------------------------------------- Blatt Statistik
def _count_by(values, keys):
    counts = dict.fromkeys(keys, 0)
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    return counts


def statistics(evaluated, year, cfg, previous=None, today=None):
    """previous: Einsätze des Vorjahrs (ohne Kennzahlen) oder None."""
    today = today or dt.date.today()
    incidents = [i for i, _ in evaluated]
    count = len(incidents)

    keywords = _count_by((i["keyword"] or "?" for i in incidents), ())
    categories = [{"code": code, "name": name,
                   "count": sum(1 for i in incidents if domain.category_of(i["keyword"]) == code),
                   "keywords": {f"{code}{level}": keywords.get(f"{code}{level}", 0) for level in domain.ALARM_LEVELS}}
                  for code, name in domain.CATEGORIES]
    levels = _count_by((domain.alarm_level(i["keyword"]) for i in incidents), domain.ALARM_LEVELS)
    areas = _count_by((m["area"] for _, m in evaluated), cfg.place_names + (domain.OTHER_AREA,))

    starts = [s for s in (parse_iso(i["started_at"]) for i in incidents) if s]
    weekdays = _count_by((s.weekday() for s in starts), range(7))
    hours = _count_by((s.hour for s in starts), range(24))
    months = _count_by((s.month for s in starts), range(1, 13))

    previous_months = previous_to_date = None
    if previous is not None:
        # Stichtag im Vorjahr; aus dem 29.02. wird der 28.02.
        leap_day = (today.month, today.day) == (2, 29)
        cutoff = dt.date(year - 1, 2, 28) if leap_day else today.replace(year=year - 1)
        previous_starts = [s for s in (parse_iso(i["started_at"]) for i in previous) if s]
        previous_months = _count_by((s.month for s in previous_starts), range(1, 13))
        previous_to_date = sum(1 for s in previous_starts if s.date() <= cutoff)

    durations = [m["duration_min"] for _, m in evaluated if m["duration_min"] is not None]
    staff = staff_totals(evaluated)
    # Einsätze / Woche: laufendes Jahr wie Excel (=Gesamt/ISOKALENDERWOCHE(HEUTE())), sonst ganzes Jahr
    weeks = today.isocalendar()[1] if year == today.year else dt.date(year, 12, 28).isocalendar()[1]
    return {
        "year": year,
        "count": count,
        "previous_to_date": previous_to_date,
        "previous_total": len(previous) if previous is not None else None,
        "per_week": round(count / weeks, 2) if weeks else None,
        "duration_total_min": round(sum(durations)),
        "duration_avg_min": round(sum(durations) / len(durations), 1) if durations else None,
        **staff,
        "attendees_avg": _average([m["attendees"] for _, m in evaluated if m["attendees"]]),
        "categories": categories,
        "fire_alarm_systems": sum(1 for i in incidents if domain.is_fire_alarm_system(i["keyword"], i["subcode"])),
        "fire_watches": sum(1 for i in incidents if domain.is_fire_watch(i["keyword"], i["subcode"])),
        "levels": [{"level": level, "count": levels[level]} for level in domain.ALARM_LEVELS],
        "areas": [{"name": name, "count": n} for name, n in areas.items()],
        "weekdays": [{"name": WEEKDAYS[d], "count": weekdays[d]} for d in range(7)],
        "hours": [{"hour": h, "count": hours[h], "daytime": cfg.day_hours[0] <= h < cfg.day_hours[1]}
                  for h in range(24)],
        "daytime_share": _share(sum(1 for _, m in evaluated if m["daytime"]), count),
        "months": [{"name": MONTHS[m - 1], "count": months[m],
                    "previous": previous_months[m] if previous_months is not None else None} for m in range(1, 13)],
    }


HISTORY_WINDOW = 12  # Monate für den gleitenden Durchschnitt im Verlauf


def monthly_history(counts, today=None):
    """Verlauf über alle Jahre: {"JJJJ-MM": anzahl} -> lückenlose Monatsliste mit gleitendem Durchschnitt.

    Reicht bis zum Vormonat (den laufenden Monat nur, wenn er schon Einsätze hat), höchstens bis zum
    Ende des letzten Jahres mit Einsätzen.
    """
    if not counts:
        return []
    today = today or dt.date.today()
    first, last = min(counts), max(counts)
    year, month = int(first[:4]), int(first[5:7])
    running = f"{today.year:04d}-{today.month:02d}"
    previous_month = f"{today.year - 1:04d}-12" if today.month == 1 else f"{today.year:04d}-{today.month - 1:02d}"
    end = max(last, min(previous_month, f"{last[:4]}-12"))
    history, window = [], []
    while f"{year:04d}-{month:02d}" <= end:
        count = counts.get(f"{year:04d}-{month:02d}", 0)
        window = (window + [count])[-HISTORY_WINDOW:]
        history.append({"year": year, "month": month, "name": MONTHS[month - 1], "count": count,
                        "running": f"{year:04d}-{month:02d}" == running,
                        "average": round(sum(window) / HISTORY_WINDOW, 2) if len(window) == HISTORY_WINDOW else None})
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return history


# ---------------------------------------------------------------- Blatt Auswertung (Bedarfsplan)
def _summarize(evaluated):
    on_time = sum(1 for _, m in evaluated if m["on_time"])
    return {
        "count": len(evaluated),
        "turnout_min": _average([m["turnout_min"] for _, m in evaluated]),
        "arrival_min": _average([m["arrival_min"] for _, m in evaluated]),
        "on_time": on_time,
        "late": len(evaluated) - on_time,
        "rate": _share(on_time, len(evaluated)),
        "crew_on_arrival": _average([m["crew_on_arrival"] for _, m in evaluated]),
        "crew_within_limit": _average([m["crew_within_limit"] for _, m in evaluated]),
        "crew_within_second": _average([m["crew_within_second"] for _, m in evaluated]),
        "crew_total": _average([m["crew_plan_total"] for _, m in evaluated]),
        "incidents": [{"id": i["id"], "number": i["number"], "arrival_min": round(m["arrival_min"], 1),
                       "on_time": m["on_time"]} for i, m in evaluated],
    }


def response_plan(evaluated, limit, cfg):
    """Pos. 8.4: ab Alarmstufe 2 im eigenen Ausrückebereich; evaluated mit derselben Zeitgrenze."""
    relevant = [(i, m) for i, m in evaluated if m["plan_relevant"]]
    # Excel zählt Einsätze ohne Eintreffzeit mit 0 min als "erreicht" – hier ausgenommen
    timed = [(i, m) for i, m in relevant if m["arrival_min"] is not None]
    windows = [{"key": key, "day_type": day_type, "hours": hours,
                **_summarize([(i, m) for i, m in timed
                              if bool(i["weekend_or_holiday"]) == weekend and m["daytime"] == daytime])}
               for key, day_type, hours, weekend, daytime in time_windows(cfg)]
    return {"limit": limit, "places": cfg.plan_places, "windows": windows, "total": _summarize(timed),
            "without_times": len(relevant) - len(timed)}


# ---------------------------------------------------------------- Mehrere Wehren
def unique_incidents(incidents):
    """Einsätze ohne Doppelte über mehrere Wehren -> (anzahl, ohne_schlüssel).

    Ein gemeinsamer Einsatz teilt den Stammdatensatz im BKS-Portal oder die Einsatznummer der
    Leitstelle (selbst angelegte Datensätze wie BSW haben keine; Altdaten nur die Nummer). Einsätze,
    die über einen der beiden Schlüssel verbunden sind, zählen einmal; ohne beide zählt jeder einzeln.
    """
    parent = {}

    def root(key):
        while parent.setdefault(key, key) != key:
            key = parent[key]
        return key

    without = 0
    for i in incidents:
        keys = [f"{kind}:{i[name]}" for kind, name in (("bks", "bks_record_id"), ("els", "dispatch_number"))
                if i.get(name)]
        if not keys:
            without += 1
        for key in keys[1:]:
            parent[root(key)] = root(keys[0])
        for key in keys[:1]:
            root(key)
    return len({root(key) for key in parent}) + without, without


def staff_totals(evaluated):
    """Erfasste Personalstunden mit Datenabdeckung; fehlende Anwesenheit ist keine gesicherte Null."""
    recorded = [m for _, m in evaluated if m["duration_min"] is not None and m["attendees"] > 0]
    minutes = sum(m["duration_min"] * m["attendees"] for m in recorded)
    return {"staff_hours": round(minutes / 60, 1) if recorded or not evaluated else None,
            "staff_recorded": len(recorded), "staff_total": len(evaluated)}


def summary(evaluated, limit, cfg):
    """Kennzahlen einer Wehr (oder der Summe) für Übersichten – ohne Personenbezug."""
    plan = response_plan(evaluated, limit, cfg)["total"]
    durations = [m["duration_min"] for _, m in evaluated if m["duration_min"] is not None]
    return {"count": len(evaluated), "plan_count": plan["count"], "on_time": plan["on_time"], "rate": plan["rate"],
            "arrival_min": plan["arrival_min"], "duration_hours": round(sum(durations) / 60, 1),
            **staff_totals(evaluated)}


# ---------------------------------------------------------------- Blatt Anwesenheit
def attendance_overview(evaluated):
    count = len(evaluated)
    members = {}
    for incident, m in evaluated:
        for person in incident["people"]:
            row = members.setdefault(person["id"], {"id": person["id"], "name": person["name"], "incidents": 0,
                                                    "minutes": 0.0, "nights": 0, "weekends": 0, "last": None})
            row["incidents"] += 1
            row["minutes"] += m["duration_min"] or 0
            row["nights"] += not m["daytime"]
            row["weekends"] += bool(incident["weekend_or_holiday"])
            if incident["started_at"] and (row["last"] is None or incident["started_at"] > row["last"]):
                row["last"] = incident["started_at"]
    rows = sorted(members.values(), key=lambda r: (-r["incidents"], r["name"]))
    for r in rows:
        r["hours"] = round(r.pop("minutes") / 60, 1)
        r["rate"] = _share(r["incidents"], count)
    return {"incident_count": count, "members": rows}
