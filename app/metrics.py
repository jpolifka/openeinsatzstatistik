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
import math

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
    # Einsatz vor dem Eintreffen abgebrochen (Einsatzabbruch im BKS-Bericht): gilt als rechtzeitig, damit die
    # Eintreffquote nicht durch Alarme sinkt, bei denen die Einheit gar nicht ankommen musste
    aborted = first is None and bool(incident.get("abort_reason"))
    return {
        "daytime": bool(start) and cfg.is_daytime(start.time()),                 # D
        "duration_min": duration,                                                 # G
        "vehicles": vehicles,
        "turnout_min": turnout,
        "arrival_min": first,
        "on_time": True if aborted else first <= limit + _ON_TIME_TOLERANCE if first is not None else None,   # AQ
        "aborted": aborted,
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
        "incidents": [{"id": i["id"], "number": i["number"], "arrival_min": None if m["arrival_min"] is None else round(m["arrival_min"], 1),
                       "aborted": m["aborted"],
                       "on_time": m["on_time"]} for i, m in evaluated],
    }


def response_plan(evaluated, limit, cfg):
    """Pos. 8.4: ab Alarmstufe 2 im eigenen Ausrückebereich; evaluated mit derselben Zeitgrenze."""
    relevant = [(i, m) for i, m in evaluated if m["plan_relevant"]]
    # Excel zählt Einsätze ohne Eintreffzeit mit 0 min als "erreicht" – hier ausgenommen; abgebrochene Einsätze
    # (Einsatzabbruch hinterlegt) gelten dagegen als rechtzeitig
    timed = [(i, m) for i, m in relevant if m["on_time"] is not None]
    windows = [{"key": key, "day_type": day_type, "hours": hours,
                **_summarize([(i, m) for i, m in timed
                              if bool(i["weekend_or_holiday"]) == weekend and m["daytime"] == daytime])}
               for key, day_type, hours, weekend, daytime in time_windows(cfg)]
    return {"limit": limit, "places": cfg.plan_places, "windows": windows, "total": _summarize(timed),
            "without_times": len(relevant) - len(timed)}


# ---------------------------------------------------------------- Zeiten, Kräfte, Belastung
# Neue Auswertungen ohne Vorbild in der Excel-Übersicht. Grundsatz: Fehlende Angaben sind nicht null –
# jede Kennzahl nennt, für wie viele Einsätze sie berechnet werden konnte ("valid" von "total").
SMALL_SAMPLE = 5          # darunter kennzeichnet die Oberfläche eine Zeile als wenig belastbar
BUILD_UP_MARKS = (5, 10, 15)   # Minuten nach Alarmierung für den Kräfteaufbau
LONG_MINUTES = 120        # ab dieser Dauer gilt ein Einsatz als lang
DURATION_BUCKETS = ((30, "bis 30 min"), (60, "30–60 min"), (120, "1–2 h"), (240, "2–4 h"), (None, "über 4 h"))


def percentile(values, share):
    """Nächster Rang: kleinster Wert, bei dem mindestens der Anteil `share` der Werte höchstens so groß ist. None ohne Werte."""
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    rank = max(1, math.ceil(round(len(values) * share, 9)))
    return values[min(rank, len(values)) - 1]


def _median(values):
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    middle = len(values) // 2
    return values[middle] if len(values) % 2 else (values[middle - 1] + values[middle]) / 2


def distribution(values, total):
    """Verteilung einer Zeit in Minuten: Fallzahl, Mittel, Median, 90. Perzentil und Abdeckung."""
    values = [v for v in values if v is not None]
    rounded = lambda v: round(v, 1) if v is not None else None
    return {"valid": len(values), "total": total, "average": rounded(sum(values) / len(values)) if values else None,
            "median": rounded(_median(values)), "p90": rounded(percentile(values, 0.9))}


def _travel_minutes(vehicles):
    """Anfahrtdauer je Fahrzeug (Eintreffen minus Ausrücken desselben Fahrzeugs); unplausible (negative) Werte entfallen."""
    result = []
    for v in vehicles.values():
        if v["turnout_min"] is not None and v["arrival_min"] is not None and v["arrival_min"] >= v["turnout_min"]:
            result.append(v["arrival_min"] - v["turnout_min"])
    return result


def timing(evaluated, cfg, marks=BUILD_UP_MARKS):
    """Zeiten und Kräfte aller Einsätze (nicht nur der Planrelevanten), je Wehr mit deren Zeitgrenzen.

    Ausrückdauer und Zeit bis zum Eintreffen je Einsatz (schnellstes bzw. erstes eigenes Fahrzeug), Anfahrtdauer je
    Fahrzeug, Kräfteaufbau (Ø anwesende Kräfte nach n Minuten) und Zeiten nach Ort und Zeitfenster.
    """
    total = len(evaluated)
    travel = [t for _, m in evaluated for t in _travel_minutes(m["vehicles"])]
    vehicle_total = sum(1 for _, m in evaluated for v in m["vehicles"].values() if v["arrival_min"] is not None
                        or v["turnout_min"] is not None)
    timed = [(i, m) for i, m in evaluated if m["arrival_min"] is not None]
    build_up = [{"minutes": minute,
                 "crew": _average([sum(v["crew"] for v in m["vehicles"].values()
                                       if v["arrival_min"] is not None and v["arrival_min"] <= minute + _WINDOW_TOLERANCE)
                                   for _, m in timed]),
                 "valid": len(timed), "total": total} for minute in marks]

    def group(items):
        return {"count": len(items), "small": len(items) < SMALL_SAMPLE,
                "turnout": distribution([m["turnout_min"] for _, m in items], len(items)),
                "arrival": distribution([m["arrival_min"] for _, m in items], len(items))}

    areas = {}
    for i, m in evaluated:
        areas.setdefault(m["area"], []).append((i, m))
    order = list(cfg.place_names) + [domain.OTHER_AREA]
    by_area = [{"name": name, **group(areas[name])} for name in sorted(areas, key=lambda n: (order.index(n) if n in order else len(order), n))]
    by_window = [{"key": key, "day_type": day_type, "hours": hours,
                  **group([(i, m) for i, m in evaluated if bool(i["weekend_or_holiday"]) == weekend and m["daytime"] == daytime])}
                 for key, day_type, hours, weekend, daytime in time_windows(cfg)]
    return {"total": total, "turnout": distribution([m["turnout_min"] for _, m in evaluated], total),
            "arrival": distribution([m["arrival_min"] for _, m in evaluated], total),
            "travel": {**distribution(travel, vehicle_total), "unit": "vehicle"},
            "build_up": build_up, "by_area": by_area, "by_window": by_window}


def overlaps(evaluated):
    """Zeitliche Überschneidung von Einsätzen einer Wehr: gleichzeitig offen heißt nicht, dass dieselben Kräfte gebunden waren.

    -> {valid, total, incidents_with_overlap, max_concurrent, overlap_minutes}; Einsätze ohne Beginn/Ende zählen nicht.
    Berühren sich Ende und Beginn genau, überschneiden sich die Einsätze nicht.
    """
    events = []
    for i, _ in evaluated:
        start, end = parse_iso(i["started_at"]), parse_iso(i["ended_at"])
        if start and end and end > start:
            events += [(start, 1, len(events)), (end, 0, len(events))]   # 0 (Ende) sortiert vor 1 (Beginn)
    spans = len(events) // 2
    events = [(t, kind, n // 2) for n, (t, kind, _) in enumerate(events)]
    events.sort(key=lambda e: (e[0], e[1]))
    active, overlapping, maximum, minutes, last = set(), set(), 0, 0.0, None
    for time, kind, index in events:
        if len(active) >= 2:
            minutes += (time - last).total_seconds() / 60
        last = time
        if kind:
            if active:
                overlapping |= active | {index}
            active.add(index)
            maximum = max(maximum, len(active))
        else:
            active.discard(index)
    return {"valid": spans, "total": len(evaluated), "incidents_with_overlap": len(overlapping),
            "max_concurrent": maximum, "overlap_minutes": round(minutes)}


def combine_overlaps(parts):
    """Überschneidungen mehrerer Wehren zusammenfassen (je Wehr berechnet; Wehren überschneiden sich nicht untereinander)."""
    return {"valid": sum(p["valid"] for p in parts), "total": sum(p["total"] for p in parts),
            "incidents_with_overlap": sum(p["incidents_with_overlap"] for p in parts),
            "max_concurrent": max((p["max_concurrent"] for p in parts), default=0),
            "overlap_minutes": sum(p["overlap_minutes"] for p in parts)}


def workload(evaluated, overlap):
    """Belastung: lange, nächtliche und Wochenend-Einsätze mit Stunden, Dauerverteilung und Überschneidungen."""
    total = len(evaluated)
    with_duration = [(i, m) for i, m in evaluated if m["duration_min"] is not None]
    durations = [m["duration_min"] for _, m in with_duration]

    def part(items):
        spent = [m["duration_min"] for _, m in items if m["duration_min"] is not None]
        return {"count": len(items), "share": _share(len(items), total),
                "hours": round(sum(spent) / 60, 1), "hours_valid": len(spent), **staff_totals(items)}

    buckets, lower = [], 0
    for upper, label in DURATION_BUCKETS:
        count = sum(1 for d in durations if d >= lower and (upper is None or d < upper))
        buckets.append({"label": label, "count": count})
        lower = upper if upper is not None else lower
    return {"total": total, "duration": distribution(durations, total),
            "long": {**part([(i, m) for i, m in with_duration if m["duration_min"] >= LONG_MINUTES]), "minutes": LONG_MINUTES},
            "night": part([(i, m) for i, m in evaluated if not m["daytime"] and i["started_at"]]),
            "weekend": part([(i, m) for i, m in evaluated if i["weekend_or_holiday"]]),
            "buckets": buckets, "overlap": overlap}


def coverage(evaluated):
    """Datenvollständigkeit: für wie viele Einsätze liegt die jeweilige Angabe vor?"""
    count = lambda test: sum(1 for i, m in evaluated if test(i, m))
    return {"total": len(evaluated), "rows": [
        {"key": "duration", "valid": count(lambda i, m: m["duration_min"] is not None)},
        {"key": "turnout", "valid": count(lambda i, m: m["turnout_min"] is not None)},
        {"key": "arrival", "valid": count(lambda i, m: m["arrival_min"] is not None)},
        {"key": "crew", "valid": count(lambda i, m: m["crew_total"] > 0)},
        {"key": "attendance", "valid": count(lambda i, m: m["attendees"] > 0)},
        {"key": "leader", "valid": count(lambda i, m: bool(i["unit_leader"]))},
    ]}


# ---------------------------------------------------------------- Abbrüche, Anlagen, Fahrzeuge, Atemschutz, Brand, Rettung
def aborts(evaluated):
    """Einsätze mit Abbruchgrund im BKS-Bericht: Anteil, Gruppen der Gründe, häufigste Gründe, Anteil je Einsatzart."""
    total = len(evaluated)
    aborted = [i for i, _ in evaluated if i.get("abort_reason")]
    kinds = _count_by((domain.abort_kind(i["abort_reason"]) for i in aborted), [k for k, _ in domain.ABORT_KINDS])
    reasons = {}
    for i in aborted:
        key = " ".join(i["abort_reason"].lower().split())
        entry = reasons.setdefault(key, {"reason": " ".join(i["abort_reason"].split()), "count": 0,
                                         "kind": domain.abort_kind(i["abort_reason"])})
        entry["count"] += 1
    categories = []
    for code, name in domain.CATEGORIES:
        part = [i for i, _ in evaluated if domain.category_of(i["keyword"]) == code]
        done = sum(1 for i in part if i.get("abort_reason"))
        categories.append({"code": code, "name": name, "count": len(part), "aborted": done,
                           "share": _share(done, len(part))})
    alarm = [i for i, _ in evaluated if domain.is_fire_alarm_system(i["keyword"], i["subcode"])]
    alarm_aborted = [i for i in alarm if i.get("abort_reason")]
    return {"total": total, "aborted": len(aborted), "share": _share(len(aborted), total),
            "kinds": [{"kind": k, "label": label, "count": kinds[k], "share": _share(kinds[k], len(aborted))}
                      for k, label in domain.ABORT_KINDS],
            "reasons": sorted(reasons.values(), key=lambda r: (-r["count"], r["reason"]))[:15],
            "categories": [c for c in categories if c["count"]],
            "fire_alarm_systems": {"count": len(alarm), "aborted": len(alarm_aborted),
                                   "false_alarms": sum(1 for i in alarm_aborted
                                                       if domain.abort_kind(i["abort_reason"]) == "false_alarm"),
                                   "share": _share(len(alarm_aborted), len(alarm))}}


def alarm_systems(evaluated):
    """Einsätze an Brandmeldeanlagen (Stichwort B2.07 oder Nummer der Anlage im Bericht) je Anlage bzw. Objekt.

    Gruppiert wird nach der Nummer der Gefahrenmeldeanlage, ersatzweise nach dem Objekt. Einsätze ohne beides stehen
    gesammelt unter „ohne Angabe“, damit die Abdeckung sichtbar bleibt.
    """
    rows = [i for i, _ in evaluated if domain.is_fire_alarm_system(i["keyword"], i["subcode"]) or i.get("alarm_system")]
    groups = {}
    for i in rows:
        key = i.get("alarm_system") or (i.get("building") or "").strip() or None
        g = groups.setdefault(key, {"system": i.get("alarm_system"), "buildings": {}, "count": 0, "aborted": 0,
                                    "false_alarms": 0, "last": None})
        g["count"] += 1
        if i.get("building"):
            g["buildings"][i["building"]] = g["buildings"].get(i["building"], 0) + 1
        if i.get("abort_reason"):
            g["aborted"] += 1
            g["false_alarms"] += domain.abort_kind(i["abort_reason"]) == "false_alarm"
        if i["started_at"] and (g["last"] is None or i["started_at"] > g["last"]):
            g["last"] = i["started_at"]
    result = []
    for key, g in groups.items():
        building = max(g.pop("buildings").items(), key=lambda kv: kv[1])[0] if g["buildings"] else None
        result.append({**g, "building": building, "known": key is not None,
                       "false_share": _share(g["false_alarms"], g["count"])})
    result.sort(key=lambda r: (not r["known"], -r["count"], r["building"] or ""))
    return {"total": len(rows), "identified": sum(r["count"] for r in result if r["known"]), "rows": result}


def _clock_minutes(start, end):
    """Minuten zwischen zwei Uhrzeiten (HH:MM:SS), über Mitternacht weitergezählt."""
    return ((seconds_of_day(end) - seconds_of_day(start)) % 86400) / 60 if start and end else None


def vehicle_usage(evaluated, cfg):
    """Je Fahrzeug: Alarmierungen, Ausfahrten, tatsächlicher Einsatz (laut Bericht), nur bereitgestellt, Stunden."""
    order = [v.call_sign for v in cfg.fleet]
    labels = {v.call_sign: v.label for v in cfg.fleet}
    usage = {}
    for incident, _ in evaluated:
        for call_sign, v in incident["vehicles"].items():
            u = usage.setdefault(call_sign, {"call_sign": call_sign, "label": labels.get(call_sign, ""), "alerted": 0,
                                             "drove": 0, "deployed": 0, "standby": 0, "unknown": 0, "minutes": 0.0,
                                             "minutes_valid": 0, "crew": 0})
            u["alerted"] += 1
            drove = bool(v.get("departed"))
            u["drove"] += drove
            u["crew"] += (v.get("crew") or 0) if drove else 0
            state = v.get("deployed")
            u["deployed"] += state == 1
            u["standby"] += state == 0
            u["unknown"] += state is None
            spent = _clock_minutes(v.get("alerted"), v.get("finished")) if drove else None
            if spent is not None:
                u["minutes"] += spent
                u["minutes_valid"] += 1
    rows = sorted(usage.values(), key=lambda u: (order.index(u["call_sign"]) if u["call_sign"] in order else len(order),
                                                  u["call_sign"]))
    for u in rows:
        u["hours"] = round(u.pop("minutes") / 60, 1)
        u["crew_avg"] = round(u.pop("crew") / u["drove"], 1) if u["drove"] else None
        known = u["deployed"] + u["standby"]
        u["standby_share"] = _share(u["standby"], known)
        u["known"] = known
    return {"total": len(evaluated), "rows": rows}


def respiratory(evaluated):
    """Atemschutz: Einsätze mit Geräteträgern, Träger und Minuten unter Atemschutz (je Person laut Anwesenheitsliste)."""
    total = len(evaluated)
    known = with_agt = carriers = minutes = persons = 0
    longest = None
    for incident, _ in evaluated:
        counts = [v["respiratory"] for v in incident["vehicles"].values() if v.get("respiratory") is not None]
        agt = [p for p in incident["people"] if p.get("agt")]
        if counts or any(p.get("agt") is not None for p in incident["people"]):
            known += 1
        carried = sum(counts)
        carriers += carried
        with_agt += bool(carried or agt)
        persons += len(agt)
        for p in agt:
            if p.get("agt_min"):
                minutes += p["agt_min"]
                longest = max(longest or 0, p["agt_min"])
    return {"total": total, "known": known, "with_agt": with_agt, "share": _share(with_agt, known),
            "carriers": carriers, "persons": persons, "minutes": minutes,
            "average_minutes": round(minutes / persons, 1) if persons else None, "longest_minutes": longest}


def fire_course(evaluated):
    """Brandverlauf der Brandeinsätze (Einsatzart B, ohne Abbrüche): Zeit vom Eintreffen bis „Brand unter Kontrolle“ und
    „Feuer aus“, Einsatztaktik und Brandwachen."""
    fires = [(i, m) for i, m in evaluated if domain.category_of(i["keyword"]) == "B" and not i.get("abort_reason")
             and not domain.is_fire_alarm_system(i["keyword"], i["subcode"]) and not domain.is_fire_watch(i["keyword"], i["subcode"])]
    to_control, to_out, by_tactic, watch_hours, watches = [], [], {}, [], 0
    for i, m in fires:
        start = parse_iso(i["started_at"])
        arrival = start + dt.timedelta(minutes=m["arrival_min"]) if start and m["arrival_min"] is not None else None

        def after(stamp):
            at = parse_iso(stamp)
            minutes = (at - arrival).total_seconds() / 60 if at and arrival else None
            return minutes if minutes is not None and minutes >= 0 else None

        controlled, out = after(i.get("fire_controlled_at")), after(i.get("fire_out_at"))
        to_control.append(controlled)
        to_out.append(out)
        if i.get("tactic"):
            entry = by_tactic.setdefault(i["tactic"], {"tactic": i["tactic"], "count": 0, "control": []})
            entry["count"] += 1
            entry["control"].append(controlled)
        until, base = parse_iso(i.get("fire_watch_until")), parse_iso(i.get("fire_out_at")) or parse_iso(i["ended_at"])
        if until:
            watches += 1
            if base and until >= base:
                watch_hours.append((until - base).total_seconds() / 3600)
    total = len(fires)
    return {"total": total, "to_control": distribution(to_control, total), "to_out": distribution(to_out, total),
            "tactics": [{"tactic": t["tactic"], "count": t["count"], "control": distribution(t["control"], t["count"])}
                        for t in sorted(by_tactic.values(), key=lambda t: -t["count"])],
            "fire_watches": watches, "fire_watch_hours": round(sum(watch_hours), 1) if watch_hours else None,
            "fire_watch_valid": len(watch_hours)}


CASUALTY_FIELDS = ("rescued", "rescued_animals", "injured", "injured_firefighters", "deceased")


def casualties(evaluated):
    """Menschenrettung, gerettete Tiere, Verletzte und Verstorbene; „nicht angegeben“ ist nie null."""
    total = len(evaluated)
    fields = {}
    for name in CASUALTY_FIELDS:
        values = [i[name] for i, _ in evaluated if i.get(name) is not None]
        fields[name] = {"total": sum(values), "incidents": sum(1 for v in values if v > 0), "reported": len(values)}
    any_event = sum(1 for i, _ in evaluated if any((i.get(n) or 0) > 0 for n in CASUALTY_FIELDS))
    return {"total": total, "fields": fields, "incidents_with_persons": any_event}


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
                                                    "minutes": 0.0, "nights": 0, "weekends": 0, "last": None,
                                                    "functions": {}, "agt_incidents": 0, "agt_minutes": 0})
            row["incidents"] += 1
            role = " ".join((person.get("role") or "").split())
            if role:
                row["functions"][role] = row["functions"].get(role, 0) + 1
            if person.get("agt"):
                row["agt_incidents"] += 1
                row["agt_minutes"] += person.get("agt_min") or 0
            row["minutes"] += m["duration_min"] or 0
            row["nights"] += not m["daytime"]
            row["weekends"] += bool(incident["weekend_or_holiday"])
            if incident["started_at"] and (row["last"] is None or incident["started_at"] > row["last"]):
                row["last"] = incident["started_at"]
    rows = sorted(members.values(), key=lambda r: (-r["incidents"], r["name"]))
    for r in rows:
        r["hours"] = round(r.pop("minutes") / 60, 1)
        r["rate"] = _share(r["incidents"], count)
    functions = {}
    for r in rows:
        for role, n in r["functions"].items():
            f = functions.setdefault(role, {"role": role, "count": 0, "people": 0})
            f["count"] += n
            f["people"] += 1
    return {"incident_count": count, "members": rows,
            "functions": sorted(functions.values(), key=lambda f: (-f["count"], f["role"]))}
