# -*- coding: utf-8 -*-
"""
Kostenersatz nach der Gebührenordnung (Satzung) der Verbandsgemeinde.

Gebührenordnungen liegen je VG in Fassungen mit Gültigkeitsbeginn (fee_schedule, zentrale DB).
calculate() rechnet einen Einsatz (Stammdatensatz im BKS-Portal) über alle beteiligten Wehren –
nur zur Anzeige und zum Drucken, gespeichert wird nichts. Regeln der Satzung (§ 5):
  - Fahrzeuge: Stundensatz je Fahrzeugtyp, vom Ausrücken bis zum Einsatzende des Fahrzeugs
  - Einsatzkräfte: Stundensatz je Person, von der Alarmierung bis zum Einsatzende
    (Brandsicherheitswache mit eigenem Satz)
  - halbstündlich abgerechnet: angefangene Stunden bis 30 Minuten auf die halbe, darüber auf die
    volle Stunde aufgerundet
  - Fehlalarm durch eine Brandmeldeanlage: höchstens die Pauschale
  - Auslagen mit Verwaltungszuschlag (Prozent), Umsatzsteuer nur wenn sie anfällt (§ 8)
Den Fahrzeugtyp liefert die Bezeichnung in der Fahrzeugliste der Wehr (z. B. „HLF 20“).
"""
import datetime as dt
import json
import math
import re

from app import domain, records
from app.timeutil import parse_iso

RATE_KEYS = ("personnel", "personnel_bma", "fire_watch", "bma_flat_max", "admin_surcharge")


# ---------------------------------------------------------------- Gebührenordnungen
def schedules(con, vg_id):
    """Fassungen der VG, neueste zuerst."""
    return [{**dict(r), "rates": json.loads(r["rates"])} for r in con.execute(
        "SELECT * FROM fee_schedule WHERE vg_id = ? ORDER BY valid_from DESC, id DESC", (vg_id,))]


def schedule_for(con, vg_id, day, schedule_id=None):
    """Fassung für einen Einsatztag (gültig ab ≤ Tag), auf Wunsch eine bestimmte."""
    found = schedules(con, vg_id)
    if schedule_id is not None:
        return next((s for s in found if s["id"] == schedule_id), None)
    return next((s for s in found if s["valid_from"] <= day), None)


def vehicle_types(con, vg_id, day=None):
    """Fahrzeugtypen der zum Tag (Standard: heute) gültigen Gebührenordnung der VG."""
    schedule = schedule_for(con, vg_id, day or dt.date.today().isoformat())
    return [v["code"] for v in schedule["rates"]["vehicles"]] if schedule else []


def suggest_type(types, fee_types):
    """Fahrzeugtyp zum Vorbelegen: der eine Typ der Kennzahl, der in der Gebührenordnung steht (in deren
    Schreibweise), sonst der einzige Typ der Kennzahl; bei mehreren Möglichkeiten keiner."""
    by_key = {_type_key(t): t for t in fee_types}
    listed = [by_key[_type_key(t)] for t in types if _type_key(t) in by_key]
    if len(listed) == 1:
        return listed[0]
    return types[0] if len(types) == 1 else ""


def check_rates(rates):
    """Sätze einer Fassung prüfen und bereinigen -> rates; ValueError mit deutscher Meldung."""
    clean = {}
    for key in RATE_KEYS:
        value = rates.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError("Alle Sätze müssen Zahlen ab 0 sein.")
        clean[key] = round(float(value), 2)
    vehicles, codes = [], set()
    for v in rates.get("vehicles", []):
        code, rate = str(v.get("code", "")).strip(), v.get("rate")
        if not code or isinstance(rate, bool) or not isinstance(rate, (int, float)) or not math.isfinite(rate) or rate < 0:
            raise ValueError("Jeder Fahrzeugtyp braucht ein Kürzel und einen Stundensatz ab 0.")
        if _type_key(code) in codes:
            raise ValueError(f"Fahrzeugtyp {code} steht doppelt in der Liste.")
        codes.add(_type_key(code))
        vehicles.append({"code": code, "name": str(v.get("name", "")).strip(), "rate": round(float(rate), 2)})
    clean["vehicles"] = vehicles
    return clean


def save_schedule(con, vg_id, name, valid_from, rates, email, schedule_id=None):
    if not (name or "").strip() or not re.fullmatch(r"\d{4}-\d\d-\d\d", valid_from or ""):
        raise ValueError("Bezeichnung und „gültig ab“ (Datum) angeben.")
    try:
        dt.date.fromisoformat(valid_from)
    except ValueError:
        raise ValueError("„Gültig ab“ muss ein gültiges Kalenderdatum sein.")
    values = (name.strip(), valid_from, json.dumps(check_rates(rates), ensure_ascii=False), email)
    if schedule_id is None:
        return con.execute("INSERT INTO fee_schedule (vg_id, name, valid_from, rates, modified_by) VALUES (?, ?, ?, ?, ?)",
                           (vg_id, *values)).lastrowid
    updated = con.execute("UPDATE fee_schedule SET name = ?, valid_from = ?, rates = ?, modified_by = ?, "
                          "modified = datetime('now', 'localtime') WHERE id = ? AND vg_id = ?",
                          (*values, schedule_id, vg_id)).rowcount
    if not updated:
        raise KeyError(schedule_id)
    return schedule_id


def delete_schedule(con, vg_id, schedule_id):
    con.execute("DELETE FROM fee_schedule WHERE id = ? AND vg_id = ?", (schedule_id, vg_id))


# ---------------------------------------------------------------- Berechnung
def billed_hours(minutes):
    """Abgerechnete Stunden: angefangene Stunde bis 30 Min. -> halbe, darüber -> volle Stunde."""
    if not minutes or minutes <= 0:
        return 0.0
    full, rest = divmod(math.ceil(minutes), 60)
    return full + (0 if rest == 0 else 0.5 if rest <= 30 else 1)


def _clock_minutes(start, end):
    """Minuten zwischen zwei Uhrzeiten ("HH:MM:SS"); über Mitternacht wie in der Einsatzübersicht."""
    def seconds(t):
        h, m, s = (int(x) for x in (t + ":00")[:8].split(":"))
        return h * 3600 + m * 60 + s
    return ((seconds(end) - seconds(start)) % 86400) / 60


def _vehicle_minutes(v, start, end_of_incident):
    """Minuten vom Ausrücken bis zum Ende des Fahrzeugs. Ohne eigenes Ende gilt das Einsatzende – dann mit
    Datum gerechnet, also auch über 24 Stunden; die Uhrzeiten der Fahrzeuge allein haben kein Datum."""
    if v.get("finished"):
        return _clock_minutes(v["departed"], v["finished"])
    if not (start and end_of_incident):
        return None
    departed = dt.datetime.combine(start.date(), dt.time.fromisoformat((v["departed"] + ":00")[:8]))
    if departed < start:                         # nach Mitternacht ausgerückt
        departed += dt.timedelta(days=1)
    return max(0.0, (end_of_incident - departed).total_seconds() / 60)


def _type_key(text):
    return re.sub(r"[\s\-./]", "", text or "").lower()


def _round(value):
    return round(value + 1e-9, 2)


def calculate(central_con, vg_id, bks_record_id, tenants, schedule_id=None, bma_cap=None, expenses=(),
              vat_percent=0):
    """Kostenaufstellung eines Einsatzes über alle Wehren der VG -> dict mit Positionen und Summen."""
    incidents = []
    for t in tenants:
        with t.connection() as con:
            incident = records.incident_of(con, bks_record_id)
        if incident:
            incidents.append((t, incident))
    if not incidents:
        raise ValueError("Zu diesem Einsatz hat noch keine Wehr einen Bericht erfasst.")
    starts = sorted(i["started_at"] for _, i in incidents if i["started_at"])
    day = starts[0][:10] if starts else "9999-12-31"
    schedule = schedule_for(central_con, vg_id, day, schedule_id)
    if not schedule:
        if schedule_id is None and schedules(central_con, vg_id):
            raise ValueError(f"Für den Einsatztag {day} ist keine gültige Gebührenordnung hinterlegt.")
        raise ValueError("Diese Gebührenordnung gibt es nicht." if schedule_id is not None and schedules(
            central_con, vg_id) else "Für die VG ist keine Gebührenordnung hinterlegt (Verwaltung → Gebührenordnung).")
    rates = schedule["rates"]
    by_type = {_type_key(v["code"]): v for v in rates["vehicles"]}
    fire_watch = any(domain.is_fire_watch(i["keyword"], i["subcode"]) for _, i in incidents)
    alarm_system = any(domain.is_fire_alarm_system(i["keyword"], i["subcode"]) for _, i in incidents)
    positions, hints = [], []
    if schedule["valid_from"] > day:
        hints.append(f"Der Einsatz liegt vor dem Gültigkeitsbeginn der Gebührenordnung „{schedule['name']}“ "
                     f"({schedule['valid_from']}) – bitte prüfen, ob sie anzuwenden ist.")
    # Fahrzeugtyp eines Ersatzfahrzeugs: aus der Fahrzeugliste, in der es steht, sonst aus dem Funkrufnamen
    labels_by_name = {v.name: v.label for t in tenants for v in t.config.fleet if v.name and v.label}
    fee_types = [v["code"] for v in rates["vehicles"]]

    for t, incident in incidents:
        labels = {v.call_sign: v.label for v in t.config.fleet}
        start, end_of_incident = parse_iso(incident["started_at"]), parse_iso(incident["ended_at"])
        moved = [(cs, v) for cs, v in sorted(incident["vehicles"].items()) if v.get("departed")]
        if start and end_of_incident and end_of_incident - start > dt.timedelta(hours=24) and \
                any(v.get("finished") for _, v in moved):
            hints.append(f"{t.name}: Einsatz länger als 24 Stunden – die Fahrzeugstunden aus den Uhrzeiten "
                         "(ohne Datum) bitte prüfen.")
        for call_sign, v in moved:
            minutes = _vehicle_minutes(v, start, end_of_incident)
            substitute = t.config.substitute_label(v.get("name"), call_sign)
            label = labels.get(call_sign) or ""
            if substitute:
                label = labels_by_name.get(v["name"]) or \
                    suggest_type(domain.describe_call_sign(v["name"]).get("types", []), fee_types)
                call_sign = f"{call_sign} (Ersatz {substitute})"
            vehicle_type = by_type.get(_type_key(label))
            if not vehicle_type:
                hints.append(f"{t.name}, {call_sign}: " + (f"Fahrzeugtyp „{label}“ steht nicht in der Gebührenordnung"
                             if label else "keine Bezeichnung in der Fahrzeugliste") +
                             " – dort den Fahrzeugtyp wie in der Gebührenordnung eintragen (z. B. HLF 20).")
            if minutes is None:
                hints.append(f"{t.name}, {call_sign}: Einsatzende fehlt – keine Stunden berechnet.")
            hours, rate = billed_hours(minutes), vehicle_type["rate"] if vehicle_type else 0.0
            positions.append({"tenant": t.name, "kind": "vehicle", "label": f"{call_sign} {label}".strip(),
                              "count": 1, "minutes": minutes, "hours": hours, "rate": rate,
                              "amount": _round(hours * rate)})
        count = len(incident["people"])
        if not count:
            count = sum(v.get("crew") or 0 for _, v in moved)
            hints.append(f"{t.name}: keine Anwesenheit erfasst – Einsatzkräfte aus der Stärke der Fahrzeuge ({count}).")
        end = end_of_incident
        minutes = (end - start).total_seconds() / 60 if start and end and end > start else None
        if minutes is None:
            hints.append(f"{t.name}: Beginn oder Ende des Einsatzes fehlt – keine Personalstunden berechnet.")
        rate = rates["fire_watch"] if fire_watch else rates["personnel_bma"] if alarm_system else rates["personnel"]
        hours = billed_hours(minutes)
        positions.append({"tenant": t.name, "kind": "personnel",
                          "label": "Brandsicherheitswache" if fire_watch else "Einsatzkräfte (ehrenamtlich)",
                          "count": count, "minutes": minutes, "hours": hours, "rate": rate,
                          "amount": _round(count * hours * rate)})

    operations = _round(sum(p["amount"] for p in positions))
    cap = alarm_system if bma_cap is None else bma_cap
    if cap and operations > rates["bma_flat_max"]:
        positions.append({"tenant": None, "kind": "cap", "label": "Fehlalarm Brandmeldeanlage: höchstens Pauschale",
                          "count": None, "minutes": None, "hours": None, "rate": rates["bma_flat_max"],
                          "amount": _round(rates["bma_flat_max"] - operations)})
    costs = [e for e in expenses if e.get("amount")]
    for e in costs:
        positions.append({"tenant": None, "kind": "expense", "label": (e.get("label") or "Auslagen").strip(),
                          "count": None, "minutes": None, "hours": None, "rate": None, "amount": _round(e["amount"])})
    if costs and rates["admin_surcharge"]:
        base = sum(e["amount"] for e in costs)
        positions.append({"tenant": None, "kind": "surcharge", "label": f"Verwaltungszuschlag {rates['admin_surcharge']:g} % "
                          "auf Auslagen", "count": None, "minutes": None, "hours": None, "rate": None,
                          "amount": _round(base * rates["admin_surcharge"] / 100)})
    net = _round(sum(p["amount"] for p in positions))
    vat = _round(net * vat_percent / 100) if vat_percent else 0.0
    first = incidents[0][1]
    return {"schedule": {"id": schedule["id"], "name": schedule["name"], "valid_from": schedule["valid_from"]},
            "incidents": [{"tenant": t.name, "number": i["number"], "year": i["year"], "started_at": i["started_at"],
                           "ended_at": i["ended_at"], "keyword": f"{i['keyword']}.{i['subcode']}".strip("."),
                           "description": i["description"], "place": i["place"]} for t, i in incidents],
            "keyword": f"{first['keyword']}.{first['subcode']}".strip("."), "fire_watch": fire_watch,
            "alarm_system": alarm_system, "bma_cap": bool(cap), "positions": positions, "net": net,
            "vat_percent": vat_percent, "vat": vat, "total": _round(net + vat), "hints": hints}
