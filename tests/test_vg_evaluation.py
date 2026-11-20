# -*- coding: utf-8 -*-
"""Gesamtansicht einer VG: Summen über Wehren, gemeinsame Einsätze, Exporte und Verteilung der PDFs."""
from app import pdf_report
import dataclasses
import io

import openpyxl
import pytest

from app import db, report, store, tenancy
from app.tenant_config import Vehicle
from conftest import CFG, grant, login, make_incident, make_tenant
from test_report import FULL, LEFT

# Zweite Wehr derselben VG mit eigenen Fahrzeugen, Orten und Bedarfsplan
OTHER = dataclasses.replace(CFG, fleet=(Vehicle("01/46"),), own_prefix="01/", unit_marker="FW NR#.MUS 01",
                            places=(("Bad Neustadt", "bad hönn"),), plan_places=("Bad Neustadt",))


def _incident(slug, number, place, dispatch_number=None, arrived="10:07:00"):
    with db.connection(tenancy.tenant_path(slug)) as con:
        incident_id = store.create_incident(con, {
            "number": number, "started_at": "2025-03-12T10:00:00", "ended_at": "2025-03-12T11:00:00",
            "keyword": "B2", "place": place, "dispatch_number": dispatch_number}, source="pdf")
        call_sign = "02/45" if slug == "wehr-a1" else "01/46"
        store.add_vehicle(con, incident_id, call_sign, None, 6, None, arrived)
        store.add_attendance(con, incident_id, store.MemberDirectory(con).find_or_create("Muster", "Max"))


@pytest.fixture
def vg(make_client):
    vg_id, _ = make_tenant("wehr-a1", "vg-a")
    make_tenant("wehr-a2", "vg-a", cfg=OTHER)
    make_tenant("wehr-b1", "vg-b")
    _incident("wehr-a1", 1, "Altenau", "1250000001")
    _incident("wehr-a1", 2, "Probenhausen", None, arrived="10:12:00")
    _incident("wehr-a2", 1, "Bad Neustadt", "1250000001")          # gemeinsamer Einsatz mit A1
    _incident("wehr-b1", 1, "Altenau", "1250000001")             # andere VG: zählt nicht mit
    grant("vglead@example.org", "vg_lead", vg_id)
    grant("vgstats@example.org", "vg_stats", vg_id)
    return login(make_client(login=True), "vglead@example.org")


def test_vg_evaluation_sums_tenants_and_counts_joint_incidents_once(vg):
    e = vg.get("/api/evaluation?year=2025").json()
    assert e["statistics"]["count"] == 3                      # Beteiligungen
    assert (e["tenants"]["participations"], e["tenants"]["unique"], e["tenants"]["without_dispatch_number"]) == \
        (3, 2, 1)
    assert [(r["slug"], r["count"]) for r in e["tenants"]["rows"]] == [("wehr-a1", 2), ("wehr-a2", 1)]
    # Bedarfsplan: jede Wehr mit ihren eigenen Orten – alle drei Einsätze zählen, einer zu spät
    assert e["response_plan"]["total"]["count"] == 3 and e["response_plan"]["total"]["on_time"] == 2
    assert set(e["response_plan"]["places"]) == {"Altenau", "Probenhausen", "Beispieldorf", "Bad Neustadt"}
    assert e["attendance"] is None                             # Kameraden nur je Wehr
    assert "Muster" not in str(e)
    # Zeiten, Belastung und Datenabdeckung über alle Wehren; Überschneidungen je Wehr gerechnet
    assert e["timing"]["total"] == 3 and e["timing"]["arrival"]["valid"] == 3
    assert e["workload"]["total"] == 3 and e["workload"]["overlap"]["incidents_with_overlap"] == 2   # nur A1 hat zwei
    assert e["coverage"]["total"] == 3


def test_vg_evaluation_filter_by_tenant(vg):
    e = vg.get("/api/evaluation?year=2025&tenants=wehr-a2").json()
    assert e["statistics"]["count"] == 1 and e["tenants"]["unique"] == 1
    assert vg.get("/api/evaluation?year=2025&tenants=wehr-b1").status_code == 400


def test_vg_incidents_list_all_tenants(vg):
    incidents = vg.get("/api/incidents?year=2025").json()["incidents"]
    assert sorted(i["tenant"] for i in incidents) == ["wehr-a1", "wehr-a1", "wehr-a2"]
    config = vg.get("/api/config").json()
    assert config["vg"]["name"] == "VG vg-a" and len(config["tenants"]) == 2
    assert "Bad Neustadt" in config["places"] and "Altenau" in config["places"]


def test_vg_export_has_sheets_per_tenant(vg):
    response = vg.get("/api/export?year=2025")
    assert response.status_code == 200
    workbook = openpyxl.load_workbook(io.BytesIO(response.content))
    # Wehrleiter/in hat Personenrechte: je Wehr mit Anwesenheit
    assert workbook.sheetnames == ["Übersicht", "Einsätze Wehr wehr-a1", "Anwesenheit Wehr wehr-a1",
                                   "Einsätze Wehr wehr-a2", "Anwesenheit Wehr wehr-a2"]
    summary = workbook["Übersicht"]
    assert [summary.cell(r, 1).value for r in (4, 5, 6)] == ["Wehr wehr-a1", "Wehr wehr-a2", "Summe (Beteiligungen)"]
    assert summary["B6"].value == 3
    assert "ohne Doppelte" in summary["A8"].value and summary["A8"].value.endswith(": 2")


def test_combined_export_attendance_refers_to_its_tenant():
    """Mit Anwesenheit (members nicht None) verweist sie auf die Einsatzübersicht ihrer Wehr."""
    from app import excel_export
    incident = make_incident()
    target = io.BytesIO()
    parts = [(dataclasses.replace(CFG, name="Wehr A"), [incident], []), (dataclasses.replace(CFG, name="Wehr B"), [incident], None)]
    excel_export.write_combined_workbook(parts, [], {}, 2025, 10, target)
    workbook = openpyxl.load_workbook(io.BytesIO(target.getvalue()))
    assert workbook.sheetnames == ["Übersicht", "Einsätze Wehr A", "Anwesenheit Wehr A", "Einsätze Wehr B"]
    assert workbook["Anwesenheit Wehr A"]["A4"].value == "='Einsätze Wehr A'!A4"


def test_statistics_role_gets_summary_without_names(vg):
    login(vg, "vgstats@example.org")
    assert vg.get("/api/export?year=2025").status_code == 403
    assert vg.get("/api/incidents?year=2025").status_code == 403
    response = vg.get("/api/export/summary?year=2025")
    assert response.status_code == 200
    workbook = openpyxl.load_workbook(io.BytesIO(response.content))
    cells = [str(c) for row in workbook["Übersicht"].iter_rows(values_only=True) for c in row]
    assert "Wehr wehr-a1" in cells and not any("Muster" in c for c in cells)


def test_summary_export_is_a_full_report(vg):
    response = vg.get("/api/export/summary?year=2025")
    workbook = openpyxl.load_workbook(io.BytesIO(response.content))
    assert workbook.sheetnames == ["Übersicht", "Statistik", "Eintreffen und Zeiten", "Belastung", "Abbrüche und Anlagen",
                                   "Fahrzeuge und Atemschutz", "Brand und Rettung", "Einsätze", "Einsatzfahrzeuge"]
    incidents = workbook["Einsätze"]
    assert incidents.max_row == 3 + 3 and incidents["A3"].value == "Wehr"          # drei Einsätze, Kopfzeile in Zeile 3


def test_statistics_role_report_has_no_lists(vg):
    login(vg, "vgstats@example.org")
    workbook = openpyxl.load_workbook(io.BytesIO(vg.get("/api/export/summary?year=2025").content))
    assert "Einsätze" not in workbook.sheetnames and "Einsatzfahrzeuge" not in workbook.sheetnames
    assert "Statistik" in workbook.sheetnames


def test_summary_export_respects_selection_and_limit(vg):
    response = vg.get("/api/export/summary?year=2025&tenants=wehr-a2&limit=10")
    assert response.status_code == 200
    workbook = openpyxl.load_workbook(io.BytesIO(response.content))
    assert workbook["Übersicht"]["A4"].value == "Wehr wehr-a2"
    assert workbook["Übersicht"]["A5"].value == "Summe (Beteiligungen)"
    assert workbook["Übersicht"]["B5"].value == 1
    assert vg.get("/api/export/summary?year=2025&limit=999").status_code == 422
    assert vg.get("/api/export/summary?year=2025&tenants=wehr-b1").status_code == 400


def test_reports_are_matched_to_the_reporting_tenant():
    candidates = [("wehr-a1", CFG), ("wehr-a2", OTHER)]
    texts = (FULL, LEFT, "")
    # Ohne Kopfzeile der Einheit: die meisten eigenen Fahrzeuge (zwei 02/.. gegen ein 01/..)
    assert report.match_tenant(report.pdf_parser(texts, "17-25.pdf"), candidates) == ("wehr-a1", "vehicles")
    header = "FW NR#.MUS 01 Bad Neustadt Alarmierung: 12.03.2025 10:05:00 Einsatznummer: 1\n"
    assert report.match_tenant(report.pdf_parser((header + FULL, LEFT, ""), "17-25.pdf"), candidates) == ("wehr-a2", "unit")
    foreign = dataclasses.replace(CFG, unit_prefix="FL NR#.XYZ ", own_prefix="05/", unit_marker="FW NR#.XYZ 05")
    assert report.match_tenant(report.pdf_parser(texts, "17-25.pdf"), [("fremd", foreign)]) == (None, None)
    # Bericht der FEZ mit mitalarmierten Fahrzeugen: keine Zuordnung über die Fahrzeuge
    fez = "Feuerwehrhaus: FW NR#.MUS 00 FEZ VG\n"
    assert report.match_tenant(report.pdf_parser((fez + FULL, LEFT, ""), "17-25.pdf"), candidates) == (None, None)
    # Wehr ohne BKS-Kennung: weiterhin über ihre Fahrzeuge
    unmarked = dataclasses.replace(CFG, unit_marker="")
    assert report.match_tenant(report.pdf_parser((fez + FULL, LEFT, ""), "17-25.pdf"), [("ohne", unmarked)]) == ("ohne", "vehicles")


def test_upload_in_vg_view_distributes_reports(vg, monkeypatch):
    from app import main
    header = "FW NR#.MUS 01 Bad Neustadt Alarmierung: 12.03.2025 10:05:00 Einsatznummer: 1\n" \
             "Einsatznummer Leitstelle: 1250000001\n"
    texts = {"a1.pdf": (FULL, LEFT, ""), "a2.pdf": (header + FULL, LEFT, ""), "fremd.pdf": ("", "", "")}
    monkeypatch.setattr(pdf_report, "extract_text", lambda path: texts[path.rsplit("/", 1)[-1]])
    data = vg.post("/api/reports", files=[("pdfs", (name, b"x", "application/pdf")) for name in texts]).json()
    assert [(r["filename"], r["tenant"], r["tenant_name"]) for r in data["reports"]] == \
        [("a1.pdf", "wehr-a1", "Wehr wehr-a1"), ("a2.pdf", "wehr-a2", "Wehr wehr-a2")]
    assert [e["file"] for e in data["errors"]] == ["fremd.pdf"]
    assert any("über die Fahrzeuge im Bericht zugeordnet" in w for w in data["reports"][0]["warnings"])
    # A1 hat den Einsatz der Leitstelle schon; B1 (andere VG) ist für den Wehrleiter nicht sichtbar
    assert data["reports"][1]["shared_with"] == ["Wehr wehr-a1"]
    saved = vg.post("/api/reports/accept", json={"token": data["token"], "filename": "a2.pdf", "fields": {}}).json()
    assert saved["id"].startswith("wehr-a2:") and saved["dispatch_number"] == "1250000001"


# Mehrfachbericht im Aufbau des BKS-Portals: Stammdatensatz und je Einheit ein Bericht
MASTER = "EINSATZBERICHT\nStammdatensatz 9000001\nEinsatznummer Leitstelle: 1250000009\n"


def _bks(kind, report_id, unit):
    return f"EINSATZBERICHT\n{kind} {report_id}\nDatensatz: 9000001\nFeuerwehrhaus: {unit}\n"


def test_multi_report_is_distributed_and_updates_on_reimport(vg, monkeypatch):
    from app import main, records
    texts = {"stamm.pdf": (MASTER + FULL.split("Anwesenheitsliste")[0], LEFT, ""),
             "a2.pdf": (_bks("Hauptbericht", "9000002", "FW NR#.MUS 01 Musterstadt") + FULL, LEFT, ""),
             "a1.pdf": (_bks("Nebenbericht", "9000003", "FW NR#.MUS 02 Musterdorf") + FULL, LEFT, ""),
             "fez.pdf": (_bks("Nebenbericht", "9000004", "FW NR#.MUS 00 FEZ VG") + FULL, LEFT, "")}
    monkeypatch.setattr(pdf_report, "extract_text", lambda path: texts[path.rsplit("/", 1)[-1]])
    files = [("pdfs", (name, b"x", "application/pdf")) for name in texts]
    data = vg.post("/api/reports", files=files).json()
    assert [(r["filename"], r["tenant"]) for r in data["reports"] if not r.get("action")] == [("a2.pdf", "wehr-a2"), ("a1.pdf", "wehr-a1")]
    assert data["errors"] == []
    assert [n["file"] for n in data["notes"]] == ["fez.pdf"]
    assert "FEZ VG" in data["notes"][0]["message"]
    a1 = data["reports"][2]
    assert (a1["bks_report_id"], a1["bks_record_id"]) == ("9000003", "9000001")
    assert a1["bks_url"].endswith("/einsatzbericht/9000003?from_nid=9336")
    assert not any("Fahrzeuge im Bericht" in w for w in a1["warnings"])
    assert vg.post("/api/reports/accept", json={"token": data["token"], "filename": "stamm.pdf", "fields": {}}).status_code == 200
    with tenancy.central() as con:
        master = records.load_master(con, con.execute("SELECT id FROM vg WHERE slug = 'vg-a'").fetchone()[0], "9000001")
    assert master["dispatch_number"] == "1250000009" and len(master["vehicles"]) == 4

    saved = vg.post("/api/reports/accept", json={"token": data["token"], "filename": "a1.pdf", "fields": {}}).json()
    with tenancy.central() as con:
        rows = con.execute("SELECT t.slug, r.kind FROM record_report r JOIN tenant t ON t.id = r.tenant_id "
                           "WHERE r.bks_record_id = '9000001'").fetchall()
        assert [tuple(r) for r in rows] == [("wehr-a1", "secondary")]

    # Erneut eingelesen, mit geänderter Nummer: über den BKS-Bericht gefunden und aktualisiert
    texts["a1.pdf"] = (texts["a1.pdf"][0].replace("17/25", "18/25"), LEFT.replace("17/25", "18/25"), "")
    data = vg.post("/api/reports", files=[("pdfs", ("a1.pdf", b"x", "application/pdf"))]).json()
    assert data["reports"][0]["existing"]["id"] == saved["id"]
    body = {"token": data["token"], "filename": "a1.pdf", "fields": {}, "replace": True, "revision": data["reports"][0]["existing"]["revision"]}
    updated = vg.post("/api/reports/accept", json=body).json()
    assert updated["id"] == saved["id"] and updated["number"] == 18


def test_single_tenant_skips_report_of_other_unit(make_client, monkeypatch):
    from app import main
    make_tenant("wehr-a1")
    client = make_client()
    texts = {"fez.pdf": (_bks("Nebenbericht", "9000004", "FW NR#.MUS 00 FEZ VG") + FULL, LEFT, "")}
    monkeypatch.setattr(pdf_report, "extract_text", lambda path: texts[path.rsplit("/", 1)[-1]])
    data = client.post("/api/reports", files=[("pdfs", ("fez.pdf", b"x", "application/pdf"))]).json()
    assert data["reports"] == [] and data["errors"] == []
    assert "gehört nicht zu Wehr wehr-a1" in data["notes"][0]["message"]
