# -*- coding: utf-8 -*-
"""Gesamtansicht einer VG: Summen über Wehren, gemeinsame Einsätze, Exporte und Verteilung der PDFs."""
import dataclasses
import io

import openpyxl
import pytest

from app import db, report, store, tenancy
from app.tenant_config import Vehicle
from conftest import CFG, grant, login, make_tenant
from test_report import FULL, LEFT

# Zweite Wehr derselben VG mit eigenen Fahrzeugen, Orten und Bedarfsplan
OTHER = dataclasses.replace(CFG, fleet=(Vehicle("01/46"),), own_prefix="01/", unit_marker="FW NR#.BHÖ 01",
                            places=(("Bad Hönningen", "bad hönn"),), plan_places=("Bad Hönningen",))


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
    _incident("wehr-a1", 1, "Rheinbrohl", "1250000001")
    _incident("wehr-a1", 2, "Hammerstein", None, arrived="10:12:00")
    _incident("wehr-a2", 1, "Bad Hönningen", "1250000001")          # gemeinsamer Einsatz mit A1
    _incident("wehr-b1", 1, "Rheinbrohl", "1250000001")             # andere VG: zählt nicht mit
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
    assert set(e["response_plan"]["places"]) == {"Rheinbrohl", "Hammerstein", "Arienheller", "Bad Hönningen"}
    assert e["attendance"] is None                             # Kameraden nur je Wehr
    assert "Muster" not in str(e)


def test_vg_evaluation_filter_by_tenant(vg):
    e = vg.get("/api/evaluation?year=2025&tenants=wehr-a2").json()
    assert e["statistics"]["count"] == 1 and e["tenants"]["unique"] == 1
    assert vg.get("/api/evaluation?year=2025&tenants=wehr-b1").status_code == 400


def test_vg_incidents_list_all_tenants(vg):
    incidents = vg.get("/api/incidents?year=2025").json()["incidents"]
    assert sorted(i["tenant"] for i in incidents) == ["wehr-a1", "wehr-a1", "wehr-a2"]
    config = vg.get("/api/config").json()
    assert config["vg"]["name"] == "VG vg-a" and len(config["tenants"]) == 2
    assert "Bad Hönningen" in config["places"] and "Rheinbrohl" in config["places"]


def test_vg_export_has_sheets_per_tenant(vg):
    response = vg.get("/api/export?year=2025")
    assert response.status_code == 200
    workbook = openpyxl.load_workbook(io.BytesIO(response.content))
    assert workbook.sheetnames == ["Übersicht", "Einsätze Wehr wehr-a1", "Anwesenheit Wehr wehr-a1",
                                   "Einsätze Wehr wehr-a2", "Anwesenheit Wehr wehr-a2"]
    summary = workbook["Übersicht"]
    assert [summary.cell(r, 1).value for r in (4, 5, 6)] == ["Wehr wehr-a1", "Wehr wehr-a2", "Summe (Beteiligungen)"]
    assert summary["B6"].value == 3
    assert "ohne Doppelte" in summary["A8"].value and summary["A8"].value.endswith(": 2")
    # Anwesenheit verweist auf die Einsatzübersicht ihrer Wehr
    assert workbook["Anwesenheit Wehr wehr-a2"]["A4"].value == "='Einsätze Wehr wehr-a2'!A4"


def test_statistics_role_gets_summary_without_names(vg):
    login(vg, "vgstats@example.org")
    assert vg.get("/api/export?year=2025").status_code == 403
    assert vg.get("/api/incidents?year=2025").status_code == 403
    response = vg.get("/api/export/summary?year=2025")
    assert response.status_code == 200
    workbook = openpyxl.load_workbook(io.BytesIO(response.content))
    cells = [str(c) for row in workbook["Übersicht"].iter_rows(values_only=True) for c in row]
    assert "Wehr wehr-a1" in cells and not any("Muster" in c for c in cells)


def test_reports_are_matched_to_the_reporting_tenant():
    candidates = [("wehr-a1", CFG), ("wehr-a2", OTHER)]
    texts = (FULL, LEFT, "")
    # Ohne Kopfzeile der Einheit: die meisten eigenen Fahrzeuge (zwei 02/.. gegen ein 01/..)
    assert report.match_tenant(texts, "17-25.pdf", candidates) == "wehr-a1"
    header = "FW NR#.BHÖ 01 Bad Hönningen Alarmierung: 12.03.2025 10:05:00 Einsatznummer: 1\n"
    assert report.match_tenant((header + FULL, LEFT, ""), "17-25.pdf", candidates) == "wehr-a2"
    foreign = dataclasses.replace(CFG, unit_prefix="FL NR#.XYZ ", own_prefix="05/", unit_marker="FW NR#.XYZ 05")
    assert report.match_tenant(texts, "17-25.pdf", [("fremd", foreign)]) is None


def test_report_of_other_unit_gets_warning():
    header = "FW NR#.BHÖ 01 Bad Hönningen Alarmierung: 12.03.2025 10:05:00 Einsatznummer: 1\n"
    r = report.read_text((header + FULL, LEFT, ""), "17-25.pdf", CFG)
    assert any("Bad Hönningen" in w and "Feuerwehr Rheinbrohl" in w for w in r["warnings"])
    assert not any("Einheit" in w for w in report.read_text((FULL, LEFT, ""), "17-25.pdf", CFG)["warnings"])


def test_upload_in_vg_view_distributes_reports(vg, monkeypatch):
    from app import main
    header = "FW NR#.BHÖ 01 Bad Hönningen Alarmierung: 12.03.2025 10:05:00 Einsatznummer: 1\n" \
             "Einsatznummer Leitstelle: 1250000001\n"
    texts = {"a1.pdf": (FULL, LEFT, ""), "a2.pdf": (header + FULL, LEFT, ""), "fremd.pdf": ("", "", "")}
    monkeypatch.setattr(main.pdf_report, "extract_text", lambda path: texts[path.rsplit("/", 1)[-1]])
    data = vg.post("/api/reports", files=[("pdfs", (name, b"x", "application/pdf")) for name in texts]).json()
    assert [(r["filename"], r["tenant"], r["tenant_name"]) for r in data["reports"]] == \
        [("a1.pdf", "wehr-a1", "Wehr wehr-a1"), ("a2.pdf", "wehr-a2", "Wehr wehr-a2")]
    assert [e["file"] for e in data["errors"]] == ["fremd.pdf"]
    # A1 hat den Einsatz der Leitstelle schon; B1 (andere VG) ist für den Wehrleiter nicht sichtbar
    assert data["reports"][1]["shared_with"] == ["Wehr wehr-a1"]
    saved = vg.post("/api/reports/accept", json={"token": data["token"], "filename": "a2.pdf", "fields": {}}).json()
    assert saved["id"].startswith("wehr-a2:") and saved["dispatch_number"] == "1250000001"
