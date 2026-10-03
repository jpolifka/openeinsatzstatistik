# -*- coding: utf-8 -*-
"""
Vom gelesenen Einsatzbericht zum Einsatz: Ableitungsregeln, Prüfhinweise und die
Umwandlung in die Form der Datenbank. cfg ist die TenantConfig der Wehr, für die der
Bericht eingelesen wird.

  parser()            Leser für eine Datei (PDF oder Excel-Export des BKS-Portals)
  read()              Bericht lesen, Nr. ergänzen, Felder ableiten, Plausibilität prüfen
  to_fields()         abgeleitete Felder -> Datenbankfelder (store.FIELDS)
  to_incident()       Bericht -> Einsatz wie aus store.load_incidents
  preview()           Einsatz für die Vorschau mit Namensabgleich und bereits erfasstem Einsatz
  save()              Bericht als Einsatz speichern bzw. einen erfassten Einsatz damit aktualisieren
  differences()       Abweichungen zwischen erfasstem Einsatz und Bericht
"""
import datetime as dt
import copy
import re

from app import domain, pdf_report, store, xlsx_report, parser_worker
from app.holidays import is_weekend_or_holiday
from app.names import normalize, short_name
from app.timeutil import parse_iso, time_text, to_iso, year_of
from app.bks_common import _call_sign_pattern

MAX_DURATION_HOURS = 24


def pdf_parser(texts, filename):
    """Leser für den Text einer PDF (pdf_report.extract_text): parse(unit_prefix) -> Bericht."""
    return lambda unit_prefix: pdf_report.parse_report(*texts, filename, unit_prefix)


def parser(path, filename):
    """Leser für eine Datei nach ihrer Endung: Excel-Export (.xlsx) oder PDF."""
    kind = "xlsx_report" if filename.lower().endswith(".xlsx") else "pdf_report"
    parsed = parser_worker.read(kind, (path, filename))
    def for_unit(unit_prefix):
        result = copy.deepcopy(parsed)
        pattern = _call_sign_pattern(unit_prefix)
        for vehicle in result["vehicles"]:
            match = pattern.search(vehicle["name"])
            vehicle["call_sign"] = match.group(1) if match else None
        return result
    return for_unit


def read(parse, cfg):
    """Ablauf ab dem Leser (parser, pdf_parser): auswerten, ableiten, prüfen."""
    report = parse(cfg.unit_prefix)
    complete_number(report)
    derive(report, cfg)
    check_plausibility(report, cfg)
    return report


def read_text(texts, filename, cfg):
    return read(pdf_parser(texts, filename), cfg)


def match_tenant(parse, candidates):
    """Wehr, zu der ein Bericht gehört -> (schlüssel, "unit" | "vehicles") oder (None, None).

    Zuerst über die berichtende Einheit (unit_marker). Über die meisten eigenen Fahrzeuge im Bericht nur
    bei Wehren ohne unit_marker – sonst landete z. B. der Bericht der FEZ über mitalarmierte Fahrzeuge
    bei einer Wehr. parse: Leser wie bei read(); candidates: [(schlüssel, cfg)].
    """
    best, best_score = None, 0
    for key, cfg in candidates:
        report = parse(cfg.unit_prefix)
        if cfg.unit_marker and report["unit"] == cfg.unit_marker:
            return key, "unit"
        if cfg.unit_marker and report["unit"]:
            continue
        score = sum(1 for v in report["vehicles"] if cfg.is_own(v["name"]))
        if score > best_score:
            best, best_score = key, score
    return (best, "vehicles") if best else (None, None)


def unit_label(report):
    """Berichtende Einheit für Meldungen, z. B. "FW NR#.ABC 00 (FEZ VG)"."""
    name = f" ({report['unit_name']})" if report.get("unit_name") else ""
    return f"{report['unit']}{name}" if report.get("unit") else "unbekannte Einheit"


# ---------------------------------------------------------------- Einsatz-Nr.
def complete_number(report):
    """Einsatz-Nr. ergänzen, wenn das Feld fehlt oder anders geschrieben ist.

    Manche Berichte schreiben "17-25" statt "17/25", bei anderen fehlt das Feld
    ganz – dann bleibt nur die Nr. vorn im Dateinamen ("61-25_B1_....pdf").
    """
    m = re.match(r"(\d{1,3})[-_/](\d\d)(?!\d)", report["filename"])
    from_filename = int(m.group(1)) if m else None
    if report["number"] is None:
        m = re.match(r"(\d+)\s*-\s*(\d+)", report["number_text"])
        if m:
            report["number"] = int(m.group(1))
        elif from_filename is not None:
            report["number"] = from_filename
            report["warnings"].append(
                f"Einsatzbericht-Nr. fehlt im PDF – Nr. {from_filename} aus Dateiname übernommen")
    if report["number"] is not None and from_filename is not None and report["number"] != from_filename:
        report["warnings"].append(f"Nr. im PDF ({report['number']}) weicht vom Dateinamen ({from_filename}) ab")


# ---------------------------------------------------------------- Ableitungen
def _is_own(vehicle, cfg):
    return cfg.is_own(vehicle["name"])


def _report_day(report):
    """Einsatztag für den Dienstzeitraum der Fahrzeuge: früheste Alarmierung im Bericht."""
    alarms = [v["alerted"] for v in report["vehicles"] if v["alerted"]]
    first = min(alarms) if alarms else report.get("first_alarm")
    return first.date() if first else None


def assign_vehicles(report, cfg):
    """Fahrzeuge den Blöcken der Einsatzübersicht zuordnen (inkl. Ersatzfahrzeuge).

    Zugeordnet wird über den vollen Funkrufnamen (TenantConfig.block_of); danach tragen Fahrzeuge und
    Personen im Feld call_sign bzw. vehicle den Block der Wehr. Eigene Fahrzeuge, die noch nicht in der
    Fahrzeugliste stehen, bekommen einen eigenen Block und stehen in report["new_vehicles"] (beim Speichern
    werden sie in die Liste aufgenommen, siehe new_fleet_vehicles).
    """
    slots, day = {}, _report_day(report)
    report["new_vehicles"] = []
    in_service = set(cfg.vehicles_on(day)) if day else set(cfg.vehicles)
    for v in report["vehicles"]:
        v["call_sign"] = cfg.block_of(v["name"])
    for p in report["people"]:
        if p.get("vehicle_name"):
            p["vehicle"] = cfg.block_of(p["vehicle_name"])
    crewed = {p.get("vehicle_name") or p["vehicle"] for p in report["people"] if p["vehicle"] or p.get("vehicle_name")}
    for v in report["vehicles"]:
        if v["call_sign"] in cfg.vehicles:
            slots[v["call_sign"]] = v
            if v["call_sign"] not in in_service:
                report["warnings"].append(f"{v['call_sign']} ist laut Fahrzeugliste an diesem Tag außer Dienst")
    for v in report["vehicles"]:
        target = cfg.substitute_of(v["name"])
        if target and target not in slots and (v["name"] in crewed or v["call_sign"] in crewed):
            slots[target] = v
            report["warnings"].append(f"{v['name']} als Ersatz für {target} eingetragen")
    for v in report["vehicles"]:
        if not _is_own(v, cfg) or v in slots.values():
            continue
        call_sign = v["call_sign"] or cfg.new_call_sign(v["name"], set(cfg.vehicles) | set(slots))
        if call_sign not in slots and call_sign not in cfg.vehicles:
            v["call_sign"] = call_sign
            slots[call_sign] = v
            report["new_vehicles"].append(call_sign)
    report["day"] = day
    return slots


def new_fleet_vehicles(report):
    """Neu aufzunehmende Fahrzeuge als [(call_sign, Funkrufname im Bericht)]."""
    return [(cs, report["slots"][cs]["name"]) for cs in report.get("new_vehicles", ())]


def _start_and_end(report, cfg):
    """Beginn = früheste Alarmierung der eigenen Fahrzeuge, Ende = spätestes Einsatzende (inkl. FEZ)."""
    own = [v for v in report["vehicles"] if _is_own(v, cfg)] or [v for v in report["vehicles"] if v["call_sign"]]
    alarms = [v["alerted"] for v in own if v["alerted"]] or \
             [v["alerted"] for v in report["slots"].values() if v["alerted"]]
    start = min(alarms) if alarms else report["first_alarm"]
    ends = [v["finished"] for v in report["vehicles"]
            if v["finished"] and (v["call_sign"] or v["name"] == cfg.control_center)]
    return start, (max(ends) if ends else None)


def _place(report, cfg):
    """Bekannter Ortsteil vor bekanntem Ort, sonst was im Bericht steht."""
    district, town = report["district"], report["town"]
    if district in cfg.place_names:
        return district
    if town in cfg.place_names:
        return town
    return district or town


def _description(report):
    """'Meldebild / Objekt' (ohne Präfix WH/HG/AH), ersatzweise 'Meldebild / Straße'."""
    target = report["building"] or report["street"]
    detail = re.sub(r"^(WH|HG|AH)\s+", "", target) if report["building"] else target
    reported = "BSW" if domain.is_fire_watch(report["keyword"], report["subcode"]) else report["reported_as"]
    return f"{reported} / {detail}" if detail else reported


def _unit_leader(report):
    """Person mit Funktion Einheitsführer; ersatzweise der Einsatzleiter, wenn er anwesend war."""
    leaders = [p for p in report["people"] if "Einheitsführer" in p["role"]]
    if leaders:
        return short_name(leaders[0]["first_name"], leaders[0]["last_name"])
    commander = report["incident_commander"].split()
    present = len(commander) >= 2 and any(
        normalize(p["last_name"]) == normalize(commander[-1]) and normalize(p["first_name"]) == normalize(commander[0])
        for p in report["people"])
    report["warnings"].append("Kein Einheitsführer im Bericht – " + (
        "Einsatzleiter eingetragen, bitte prüfen" if present else "EHF bitte manuell eintragen"))
    return short_name(commander[0], commander[-1]) if present else ""


def _station_staff(report):
    """Personen im Gerätehaus = Anwesende minus Besatzung der erfassten Fahrzeuge."""
    present = len({(normalize(p["last_name"]), normalize(p["first_name"])) for p in report["people"]})
    return max(0, present - sum(v["crew"] for v in report["slots"].values()))


def derive(report, cfg):
    """Felder der Einsatzübersicht aus dem gelesenen Bericht ableiten."""
    report["slots"] = assign_vehicles(report, cfg)
    report["started_at"], report["ended_at"] = _start_and_end(report, cfg)
    if not report["started_at"]:
        report["warnings"].append("Einsatzbeginn nicht ermittelbar")
    if not report["ended_at"]:
        report["warnings"].append("Einsatzende nicht ermittelbar")
    report["place"] = _place(report, cfg)
    report["description"] = _description(report)
    report["unit_leader"] = _unit_leader(report)
    report["station_staff"] = _station_staff(report)
    start = report["started_at"]
    report["weekend_or_holiday"] = int(bool(start and is_weekend_or_holiday(start.date())))
    return report


def check_plausibility(report, cfg=None):
    # Bei Nummerierung nach Datum vergibt die App die Nr. selbst
    if report["number"] is None and not (cfg and cfg.numbering == "by_date"):
        report["warnings"].append("Einsatzbericht-Nr. nicht erkannt")
    start, end = report["started_at"], report["ended_at"]
    if start and end:
        if end < start:
            report["warnings"].append("Einsatzende liegt vor Einsatzbeginn – Datum im Bericht prüfen")
        elif end - start > dt.timedelta(hours=MAX_DURATION_HOURS):
            report["warnings"].append(f"Einsatzdauer über {MAX_DURATION_HOURS} Stunden – bitte prüfen")
    if not report["people"]:
        report["warnings"].append("Anwesenheitsliste leer")


# ---------------------------------------------------------------- Umwandlungen
def current_warnings(incident):
    """Aktuell gespeicherte Daten prüfen, unabhängig von historischen Importhinweisen."""
    warnings = []
    start, end = parse_iso(incident.get("started_at")), parse_iso(incident.get("ended_at"))
    if not start:
        warnings.append("Einsatzbeginn fehlt")
    if not end:
        warnings.append("Einsatzende fehlt – Dauer und Personalstunden sind unvollständig")
    if start and end and end - start > dt.timedelta(hours=MAX_DURATION_HOURS):
        warnings.append(f"Einsatzdauer über {MAX_DURATION_HOURS} Stunden – bitte prüfen")
    if not incident.get("people"):
        warnings.append("Anwesenheitsliste leer – Personalstunden sind unvollständig")
    return warnings


def to_fields(report):
    """Abgeleitete Felder in der Form der Datenbank (Zeiten als ISO-Text)."""
    fields = {name: report[name] for name in store.FIELDS}
    fields.update({name: report.get(name) for name in store.ID_FIELDS})
    fields["started_at"], fields["ended_at"] = to_iso(report["started_at"]), to_iso(report["ended_at"])
    return fields


def vehicle_rows(report):
    """Fahrzeugblöcke in der Form der Datenbank."""
    return {call_sign: {"call_sign": call_sign, "name": v["name"], "crew": v["crew"],
                        "departed": time_text(v["departed"]), "arrived": time_text(v["arrived"]),
                        "alerted": time_text(v.get("alerted")), "finished": time_text(v.get("finished"))}
            for call_sign, v in report["slots"].items()}


def _source(report):
    """Herkunft des Einsatzes: "pdf" oder "bks_xlsx" (Excel-Export des BKS-Portals)."""
    return report.get("source", "pdf")


def to_incident(report, fields, people):
    """Bericht (mit ggf. korrigierten Feldern) als Einsatz wie aus store.load_incidents."""
    return {**fields, "id": None, "year": year_of(fields.get("started_at")), "source": _source(report),
            "filename": report["filename"], "warnings": report["warnings"],
            "weekend_or_holiday": report["weekend_or_holiday"], "vehicles": vehicle_rows(report), "people": people}


def preview(con, report, numbered=True):
    """(einsatz, erfasster_einsatz_oder_None). Personen ohne Treffer sind mit new=True markiert.
    numbered=False (Nummerierung nach Datum): die Nr. des Berichts sagt nichts über erfasste Einsätze."""
    members = store.MemberDirectory(con)
    people = []
    for p in report["people"]:
        member_id = members.find(p["last_name"], p["first_name"])
        name = members.names[member_id] if member_id else f"{p['last_name']}, {p['first_name']}"
        people.append({"id": member_id, "name": name, "last_name": p["last_name"], "first_name": p["first_name"],
                       "role": p["role"], "vehicle": p["vehicle"], "new": member_id is None})
    incident = to_incident(report, to_fields(report), people)
    existing_id = store.find_existing(con, incident["bks_report_id"], incident["year"],
                                      incident["number"] if numbered else None)
    return incident, (store.load_incident(con, existing_id) if existing_id else None)


def save(con, report, fields, update_id=None, modified_by=None, revision=None):
    """Bericht mit den (ggf. korrigierten) Feldern als Einsatz speichern; unbekannte Personen anlegen.

    update_id: erfasster Einsatz, der mit dem Bericht aktualisiert wird. Er behält seine ID und
    manuell ergänzte Fahrzeuge und Personen (siehe store.replace_report_rows).
    """
    if update_id:
        store.update_incident(con, update_id, fields, modified_by=modified_by,
                              revision=revision,
                              source={"source": _source(report), "filename": report["filename"],
                                      "warnings": report["warnings"]})
        incident_id = update_id
    else:
        incident_id = store.create_incident(con, fields, source=_source(report), filename=report["filename"],
                                            warnings=report["warnings"], modified_by=modified_by)
    store.add_fleet_vehicles(con, new_fleet_vehicles(report), report.get("day"))
    members = store.MemberDirectory(con)
    attendance = [(members.find_or_create(p["last_name"], p["first_name"]), p["role"] or None, p["vehicle"])
                  for p in report["people"]]
    store.replace_report_rows(con, incident_id, vehicle_rows(report).values(), attendance)
    return incident_id


# ---------------------------------------------------------------- Abgleich
COMPARED_FIELDS = {"number": "Nr.", "started_at": "Beginn", "ended_at": "Ende", "keyword": "Stichwort",
                   "subcode": "Stufe", "place": "Ort", "unit_leader": "EHF", "station_staff": "Personen Gerätehaus",
                   "description": "Beschreibung", "dispatch_number": "Leitstellen-Nr."}
COMPARED_VEHICLE_FIELDS = {"crew": "Stärke", "departed": "Ausrücken", "arrived": "Eintreffen"}


def _display(name, value):
    """Wert für den Abgleich; Zeiten mit Sekunden."""
    if value in (None, ""):
        return "–"
    if name in ("started_at", "ended_at"):
        return parse_iso(value).strftime("%d.%m.%Y %H:%M:%S")
    if name in ("departed", "arrived"):
        return value[:8]
    return str(value)


def differences(stored, incoming, cfg):
    """Unterschiede zwischen gespeichertem Einsatz und Bericht als [{field, stored, report}]."""
    diffs = []

    def compare(label, name, old, new):
        old, new = _display(name, old), _display(name, new)
        if old != new:
            diffs.append({"field": label, "stored": old, "report": new})

    for name, label in COMPARED_FIELDS.items():
        compare(label, name, stored.get(name), incoming.get(name))
    for call_sign in sorted(set(cfg.vehicles) | set(stored["vehicles"]) | set(incoming["vehicles"])):
        old, new = stored["vehicles"].get(call_sign) or {}, incoming["vehicles"].get(call_sign) or {}
        for name, label in COMPARED_VEHICLE_FIELDS.items():
            compare(f"{label} {call_sign}", name, old.get(name), new.get(name))
    def attendance(people):
        def identity(person):
            if person.get("id") is not None:
                return f"id:{person['id']}"
            return "name:" + "|".join(normalize(part) for part in store.person_names(person))
        return sorted((identity(p), p.get("role") or "", p.get("vehicle") or "") for p in people)

    if attendance(stored["people"]) != attendance(incoming["people"]):
        diffs.append({"field": "Anwesende", "stored": str(len(stored["people"])),
                      "report": str(len(incoming["people"])) + " (Personen oder Zuordnungen geändert)"})
    return diffs
