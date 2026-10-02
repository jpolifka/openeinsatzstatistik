# -*- coding: utf-8 -*-
"""
Einsätze über Wehren hinweg: Stammdatensätze des BKS-Portals und Verzeichnis der eingelesenen Berichte.

Ein Einsatz hat im BKS-Portal einen Stammdatensatz (VG, ohne Einheit, mit allen Fahrzeugen und den
Zeiten der Leitstelle) und je beteiligter Einheit einen Haupt- bzw. Nebenbericht, der auf ihn
verweist. Beides liegt in der zentralen Datenbank und enthält keine Personen; Namen und
Anwesenheit bleiben in der Datenbank der jeweiligen Wehr.

Der Abgleich (check) vergleicht je Stammdatensatz die Zeiten der Leitstelle mit den Berichten der
Wehren, findet fehlende und unbearbeitete Berichte und ist die Grundlage für das Prüfprotokoll des
Wehrleiters. Hinweise (notice) an eine Wehr entstehen beim Einlesen durch andere.
"""
import datetime as dt
import hashlib
import json
import re

from app import store
from app.timeutil import to_iso

CALL_SIGN = re.compile(r"\d\d/\d\d")
# Werte je Fahrzeug, die Stammdatensatz und Berichte gemeinsam haben
VEHICLE_FIELDS = (("crew", "Stärke"), ("alerted", "Alarmierung"), ("departed", "Ausrücken"),
                  ("arrived", "Eintreffen"), ("finished", "Ende"))
# Zeiten, die ältere Einsätze noch nicht gespeichert haben: fehlen sie im Einsatz, kein Befund
NEWER_FIELDS = ("alerted", "finished")


def save_master(con, vg_id, report, email=None):
    """Stammdatensatz speichern bzw. mit einem neueren Stand ersetzen (nur innerhalb derselben VG)."""
    vehicles = [{"name": v["name"], "crew": v["crew"],
                 **{key: to_iso(v[key]) for key in ("alerted", "departed", "arrived", "finished")}}
                for v in report["vehicles"]]
    con.execute(
        "INSERT INTO master_record (bks_record_id, vg_id, dispatch_number, first_alarm, keyword, subcode, reported_as, "
        "town, district, street, vehicles, filename, imported_by) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(bks_record_id) DO UPDATE SET dispatch_number = excluded.dispatch_number, "
        "first_alarm = excluded.first_alarm, keyword = excluded.keyword, subcode = excluded.subcode, "
        "reported_as = excluded.reported_as, town = excluded.town, district = excluded.district, "
        "street = excluded.street, vehicles = excluded.vehicles, filename = excluded.filename, "
        "imported_by = excluded.imported_by, imported = datetime('now', 'localtime') "
        "WHERE master_record.vg_id = excluded.vg_id",
        (report["bks_record_id"], vg_id, report.get("dispatch_number"), to_iso(report.get("first_alarm")),
         report.get("keyword"), report.get("subcode"), report.get("reported_as"), report.get("town"),
         report.get("district"), report.get("street"), json.dumps(vehicles, ensure_ascii=False),
         report.get("filename"), email))


def load_master(con, bks_record_id):
    row = con.execute("SELECT * FROM master_record WHERE bks_record_id = ?", (bks_record_id,)).fetchone()
    if not row:
        return None
    return {**dict(row), "vehicles": json.loads(row["vehicles"])}


def register_report(con, tenant_id, report, email=None):
    """Eingelesenen Bericht einer Wehr im Verzeichnis vermerken (ohne Inhalt)."""
    if not report.get("bks_report_id"):
        return
    con.execute(
        "INSERT INTO record_report (bks_report_id, bks_record_id, tenant_id, unit, kind, number_text, imported_by) "
        "VALUES (?,?,?,?,?,?,?) ON CONFLICT(bks_report_id) DO UPDATE SET bks_record_id = excluded.bks_record_id, "
        "tenant_id = excluded.tenant_id, unit = excluded.unit, kind = excluded.kind, "
        "number_text = excluded.number_text, imported_by = excluded.imported_by, "
        "imported = datetime('now', 'localtime')",
        (report["bks_report_id"], report.get("bks_record_id"), tenant_id, report.get("unit"),
         report.get("report_kind"), report.get("number_text"), email))


def reports_of(con, bks_record_id):
    """Eingelesene Berichte zu einem Stammdatensatz mit ihrer Wehr."""
    return [dict(r) for r in con.execute(
        "SELECT r.*, t.slug, t.name FROM record_report r JOIN tenant t ON t.id = r.tenant_id "
        "WHERE r.bks_record_id = ? ORDER BY r.kind, t.name", (bks_record_id,))]




# ---------------------------------------------------------------- Abgleich
def _minute(value):
    """Zeit minutengenau als "HH:MM" – aus datetime, ISO-Text oder "HH:MM:SS"."""
    if value is None or value == "":
        return None
    if isinstance(value, dt.datetime):
        return value.strftime("%H:%M")
    return str(value).split("T")[-1][:5]


def _value(field, value):
    if field == "crew":
        return None if value is None else int(value)
    return _minute(value)


def call_sign_of(name, cfg):
    """Funkrufname aus dem Fahrzeugnamen im Bericht, z. B. "FL NR#.ABC 02/45-01" -> "02/45"."""
    m = CALL_SIGN.match(name[len(cfg.unit_prefix):]) if name.startswith(cfg.unit_prefix) else None
    return m.group(0) if m else name


def moved_vehicles(vehicles, cfg):
    """Eigene Fahrzeuge der Wehr, die laut Bericht bzw. Stammdatensatz ausgerückt sind."""
    seen, result = set(), []
    for v in vehicles:
        if v["name"].startswith(cfg.own_vehicle_prefix) and (v.get("departed") or v.get("arrived")) \
                and v["name"] not in seen:
            seen.add(v["name"])
            result.append(v)
    return result


def vehicle_differences(source, incident, cfg):
    """Abweichungen zwischen Fahrzeugen aus Stammdatensatz bzw. fremdem Bericht (source) und dem
    erfassten Einsatz der Wehr -> [{vehicle, field, source, stored}]; nur eigene Fahrzeuge der Wehr."""
    stored = incident["vehicles"]
    by_name = {v["name"]: v for v in stored.values() if v.get("name")}
    result = []
    for v in moved_vehicles(source, cfg):
        call_sign = call_sign_of(v["name"], cfg)
        mine = by_name.get(v["name"]) or stored.get(call_sign)
        if not mine:
            result.append({"vehicle": call_sign, "field": "Fahrzeug", "source": "ausgerückt", "stored": None})
            continue
        for field, label in VEHICLE_FIELDS:
            theirs, ours = _value(field, v.get(field)), _value(field, mine.get(field))
            if ours is None and field in NEWER_FIELDS:
                continue
            if theirs != ours:
                result.append({"vehicle": call_sign, "field": label, "source": theirs, "stored": ours})
    return result


def incident_of(con, bks_record_id):
    """Erfasster Einsatz der Wehr zu einem Stammdatensatz (oder None)."""
    row = con.execute("SELECT id FROM incident WHERE bks_record_id = ? ORDER BY id LIMIT 1", (bks_record_id,)).fetchone()
    return store.load_incident(con, row["id"]) if row else None


def _keyword(item):
    return f"{item.get('keyword') or ''}.{item.get('subcode') or ''}".strip(".")


def check(central_con, bks_record_id, tenants):
    """Abgleich eines Einsatzes über die Wehren der VG -> {record, incidents, findings}.

    findings: [{tenant, tenant_name, kind, vehicle, field, source, stored}] mit kind
    vehicle (Stammdatensatz ≠ Bericht), keyword, missing (kein Bericht trotz ausgerückter Fahrzeuge),
    unedited (Bericht ohne Anwesenheit) und no_number (Bericht ohne Nr.).
    """
    master = load_master(central_con, bks_record_id)
    findings, incidents = [], []

    def add(tenant, kind, **values):
        findings.append({"tenant": tenant.slug, "tenant_name": tenant.name, "kind": kind,
                         **{k: values.get(k) for k in ("vehicle", "field", "source", "stored")}})

    for t in tenants:
        cfg = t.config
        with t.connection() as con:
            incident = incident_of(con, bks_record_id)
            pending = any(r.get("bks_record_id") == bks_record_id for r in store.pending_reports(con))
        moved = moved_vehicles(master["vehicles"], cfg) if master else []
        if not incident:
            if moved:
                add(t, "missing", vehicle=", ".join(call_sign_of(v["name"], cfg) for v in moved),
                    source="liegt zur Übernahme bereit" if pending else None)
            continue
        incidents.append({"tenant": t.slug, "tenant_name": t.name, "id": f"{t.slug}:{incident['id']}",
                          "number": incident["number"], "year": incident["year"], "started_at": incident["started_at"],
                          "keyword": _keyword(incident), "place": incident["place"],
                          "people": len(incident["people"]), "bks_report_id": incident.get("bks_report_id")})
        if master:
            for d in vehicle_differences(master["vehicles"], incident, cfg):
                add(t, "vehicle", **d)
            if master.get("keyword") and _keyword(master) != _keyword(incident):
                add(t, "keyword", field="Stichwort", source=_keyword(master), stored=_keyword(incident))
        if not incident["people"]:
            add(t, "unedited", field="Anwesenheit", stored="leer")
        if incident["number"] is None:
            add(t, "no_number", field="Nr.", stored="fehlt")
    if not master and len({i["keyword"] for i in incidents}) > 1:
        for i in incidents:
            findings.append({"tenant": i["tenant"], "tenant_name": i["tenant_name"], "kind": "keyword",
                             "vehicle": None, "field": "Stichwort", "source": None, "stored": i["keyword"]})
    record = {key: master.get(key) for key in ("bks_record_id", "dispatch_number", "first_alarm", "keyword", "subcode",
                                               "reported_as", "town", "district", "street")} if master else \
        {"bks_record_id": bks_record_id}
    return {"record": record, "incidents": incidents, "findings": findings}


def findings_hash(findings):
    return hashlib.sha1(json.dumps(findings, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def record_ids(central_con, vg_id, year, tenants):
    """Stammdatensätze eines Jahres: aus den Einsätzen der Wehren und den gespeicherten Stammdatensätzen."""
    ids = {r[0] for r in central_con.execute(
        "SELECT bks_record_id FROM master_record WHERE vg_id = ? AND substr(first_alarm, 1, 4) = ?", (vg_id, str(year)))}
    for t in tenants:
        with t.connection() as con:
            ids |= {r[0] for r in con.execute(
                "SELECT bks_record_id FROM incident WHERE year = ? AND bks_record_id IS NOT NULL", (year,))}
    return ids


def protocol(central_con, vg_id, year, tenants):
    """Prüfprotokoll eines Jahres: je Stammdatensatz Abgleich und Prüfvermerk, neueste zuerst."""
    reviews = {r["bks_record_id"]: dict(r) for r in central_con.execute(
        "SELECT * FROM record_review WHERE vg_id = ?", (vg_id,))}
    entries = []
    for record_id in record_ids(central_con, vg_id, year, tenants):
        entry = check(central_con, record_id, tenants)
        review = reviews.get(record_id)
        entry["reviewed"] = {"by": review["reviewed_by"], "at": review["reviewed"]} \
            if review and review["findings_hash"] == findings_hash(entry["findings"]) else None
        starts = [i["started_at"] for i in entry["incidents"] if i["started_at"]]
        entry["started_at"] = min(starts) if starts else entry["record"].get("first_alarm")
        entries.append(entry)
    return sorted(entries, key=lambda e: e["started_at"] or "", reverse=True)


def review(central_con, vg_id, bks_record_id, tenants, email, done=True):
    """Prüfvermerk setzen (gilt für den jetzigen Stand der Befunde) bzw. entfernen."""
    if not done:
        central_con.execute("DELETE FROM record_review WHERE bks_record_id = ? AND vg_id = ?", (bks_record_id, vg_id))
        return
    digest = findings_hash(check(central_con, bks_record_id, tenants)["findings"])
    central_con.execute(
        "INSERT INTO record_review (bks_record_id, vg_id, findings_hash, reviewed_by) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(bks_record_id) DO UPDATE SET findings_hash = excluded.findings_hash, "
        "reviewed_by = excluded.reviewed_by, reviewed = datetime('now', 'localtime')",
        (bks_record_id, vg_id, digest, email))


# ---------------------------------------------------------------- Hinweise an Wehren
def notify(con, tenant_id, kind, text, bks_record_id=None, incident_key=None, year=None, email=None):
    """Hinweis an eine Wehr; derselbe offene Hinweis wird nicht doppelt angelegt.
    incident_key und year: Einsatz, den die Oberfläche dazu öffnet."""
    if con.execute("SELECT 1 FROM notice WHERE tenant_id = ? AND kind = ? AND text = ? AND done IS NULL",
                   (tenant_id, kind, text)).fetchone():
        return
    con.execute("INSERT INTO notice (tenant_id, kind, bks_record_id, incident_key, year, text, created_by) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)", (tenant_id, kind, bks_record_id, incident_key, year, text, email))


def open_notices(con, tenant_ids):
    if not tenant_ids:
        return []
    marks = ",".join("?" * len(tenant_ids))
    return [dict(r) for r in con.execute(
        f"SELECT n.*, t.slug AS tenant, t.name AS tenant_name FROM notice n JOIN tenant t ON t.id = n.tenant_id "
        f"WHERE n.done IS NULL AND n.tenant_id IN ({marks}) ORDER BY n.created DESC, n.id DESC", list(tenant_ids))]


def close_notice(con, notice_id, email):
    con.execute("UPDATE notice SET done = datetime('now', 'localtime'), done_by = ? WHERE id = ?", (email, notice_id))


def format_date(value):
    """Datum für Hinweistexte: TT.MM.JJJJ aus datetime oder ISO-Text."""
    value = to_iso(value) if isinstance(value, dt.datetime) else value
    return f"{value[8:10]}.{value[5:7]}.{value[:4]}" if value else "?"


def _difference_text(d):
    return f"{d['vehicle']} {d['field']} {d['source'] or '–'} (erfasst: {d['stored'] or '–'})"


def close_notices(con, tenant_id, bks_record_id, kinds):
    """Hinweise zu einem Einsatz erledigen, die sich erübrigt haben – z. B. „noch kein eigener Bericht“,
    sobald die Wehr einen hat bzw. einer bereitliegt."""
    if bks_record_id:
        con.execute(f"UPDATE notice SET done = datetime('now', 'localtime'), done_by = 'System' "
                    f"WHERE tenant_id = ? AND bks_record_id = ? AND done IS NULL "
                    f"AND kind IN ({','.join('?' * len(kinds))})", (tenant_id, bks_record_id, *kinds))


def notify_others(central_con, source, vehicles, origin, tenants, exclude=None, deviations=True, email=None):
    """Hinweise an die Wehren der VG zu einem eingelesenen Bericht bzw. Stammdatensatz (source):
    Abweichungen bei ihren Fahrzeugen (deviations) und fehlende eigene Berichte.
    origin: z. B. „Bericht von Leutesdorf“. Die Zeiten der Leitstelle im Stammdatensatz korrigieren die
    Wehren in ihren Berichten oft bewusst – dort nur fehlende Berichte melden (deviations=False)."""
    record_id = source.get("bks_record_id")
    when = format_date(source.get("started_at") or source.get("first_alarm"))
    what = " ".join(part for part in (_keyword(source), source.get("reported_as") or "") if part)
    for t in tenants:
        if exclude and t.id == exclude:
            continue
        cfg = t.config
        moved = moved_vehicles(vehicles, cfg)
        if not moved:
            continue
        with t.connection() as con:
            incident = incident_of(con, record_id) if record_id else None
            if not incident and source.get("dispatch_number"):
                row = con.execute("SELECT id FROM incident WHERE dispatch_number = ? LIMIT 1",
                                  (source["dispatch_number"],)).fetchone()
                incident = store.load_incident(con, row["id"]) if row else None
            pending = any(r.get("bks_record_id") == record_id for r in store.pending_reports(con)) if record_id else False
        if incident:
            differences = vehicle_differences(vehicles, incident, cfg) if deviations else []
            if differences:
                notify(central_con, t.id, "deviation",
                       f"Einsatz {incident['number'] or '–'}/{incident['year']} vom {format_date(incident['started_at'])}: "
                       f"{origin} weicht ab – " + "; ".join(_difference_text(d) for d in differences),
                       record_id, f"{t.slug}:{incident['id']}", incident["year"], email)
        elif not pending:
            notify(central_con, t.id, "missing",
                   f"Einsatz vom {when} ({what}): {', '.join(call_sign_of(v['name'], cfg) for v in moved)} "
                   f"laut {origin} ausgerückt – noch kein eigener Bericht erfasst.", record_id, email=email)
