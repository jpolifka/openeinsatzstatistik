# -*- coding: utf-8 -*-
"""
Einsätze über Wehren hinweg: Stammdatensätze des BKS-Portals und Verzeichnis der eingelesenen Berichte.

Ein Einsatz hat im BKS-Portal einen Stammdatensatz (VG, ohne Einheit, mit allen Fahrzeugen und den
Zeiten der Leitstelle) und je beteiligter Einheit einen Haupt- bzw. Nebenbericht, der auf ihn
verweist. Beides liegt in der zentralen Datenbank und enthält keine Personen; Namen und
Anwesenheit bleiben in der Datenbank der jeweiligen Wehr.
"""
import json

from app.timeutil import to_iso


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

