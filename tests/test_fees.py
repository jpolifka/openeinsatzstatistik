# -*- coding: utf-8 -*-
"""Kostenersatz nach der Gebührenordnung der VG (Satzung Bad Hönningen 2024 als Beispiel)."""
import dataclasses

import pytest

from app import db, fees, legacy, main, tenancy
from app.tenant_config import Vehicle
from conftest import CFG, grant, login, make_tenant
from test_report import FULL, LEFT

# Bezeichnungen der Fahrzeuge = Fahrzeugtypen der Gebührenordnung
FLEET = dataclasses.replace(CFG, fleet=(Vehicle("02/45", "HLF 20"), Vehicle("02/24", "MTF"), Vehicle("02/71")))
REPORT = "EINSATZBERICHT\nNebenbericht 9000003\nDatensatz: 9000001\nFeuerwehrhaus: FW NR#.BHÖ 02 Musterdorf\n"


@pytest.mark.parametrize("minutes, hours", [(0, 0), (20, .5), (30, .5), (31, 1), (60, 1), (70, 1.5), (100, 2),
                                            (36.3, 1), (90, 1.5), (90.2, 2)])
def test_billed_hours_round_up_to_half_hours(minutes, hours):
    assert fees.billed_hours(minutes) == hours


@pytest.fixture
def vg(make_client, monkeypatch):
    vg_id, tenant_id = make_tenant("wehr-a1", cfg=FLEET)
    grant("vglead@example.org", "vg_lead", vg_id)
    grant("lead@example.org", "lead", tenant_id)
    with tenancy.central() as con:
        legacy.seed_fee_schedule(con, vg_id)
        fees.save_schedule(con, vg_id, "Entwurf 2030", "2030-01-01",
                           {**legacy.FEE_SCHEDULE_2024["rates"], "personnel": 40}, "test")
    client = login(make_client(login=True), "vglead@example.org")
    client.cookies.set("scope", "vg:vg-a")
    return client


def _incident(client, monkeypatch, text=FULL, left=LEFT):
    monkeypatch.setattr(main.pdf_report, "extract_text", lambda path: (REPORT + text, left, ""))
    data = client.post("/api/reports", files=[("pdfs", ("a1.pdf", b"x", "application/pdf"))]).json()
    client.post("/api/reports/accept", json={"token": data["token"], "filename": "a1.pdf", "fields": {}})


def _fees(client, **body):
    return client.post("/api/records/9000001/fees", json=body)


def test_costs_of_vehicles_and_personnel(vg, monkeypatch):
    _incident(vg, monkeypatch)
    result = _fees(vg).json()
    assert result["schedule"]["name"] == "Satzung vom 16.05.2024"           # gilt am 12.03.2025
    rows = [(p["kind"], p["label"], p["count"], p["hours"], p["rate"], p["amount"]) for p in result["positions"]]
    # 02/45: Ausrücken 10:12 bis Ende 10:48 (37 Min. -> 1 h); 3 Personen 10:08 bis 11:05 (57 Min. -> 1 h)
    assert rows == [("vehicle", "02/24 MTF", 1, 1, 37.0, 37.0), ("vehicle", "02/45 HLF 20", 1, 1, 447.0, 447.0),
                    ("personnel", "Einsatzkräfte (ehrenamtlich)", 3, 1, 33.45, 100.35)]
    assert (result["net"], result["total"], result["hints"]) == (584.35, 584.35, [])
    assert [s["name"] for s in result["schedules"]] == ["Entwurf 2030", "Satzung vom 16.05.2024"]

    result = _fees(vg, schedule_id=result["schedules"][0]["id"], vat_percent=19,
                   expenses=[{"label": "Bindemittel", "amount": 100}]).json()
    assert [p["amount"] for p in result["positions"] if p["kind"] in ("expense", "surcharge")] == [100.0, 10.0]
    assert result["positions"][2]["rate"] == 40.0
    assert (result["net"], result["vat"], result["total"]) == (714.0, 135.66, 849.66)


def test_alarm_system_is_capped_and_fire_watch_has_own_rate(vg, monkeypatch):
    _incident(vg, monkeypatch, FULL.replace("B2.08", "B2.07"), LEFT.replace("B2.08", "B2.07"))
    result = _fees(vg).json()
    assert result["bma_cap"] and result["total"] == 400.0
    assert _fees(vg, bma_cap=False).json()["total"] == 584.35          # kein Fehlalarm: volle Kosten

    with db.connection(tenancy.tenant_path("wehr-a1")) as con:
        con.execute("UPDATE incident SET keyword = 'S1', subcode = '00'")
    result = _fees(vg).json()
    assert result["positions"][-1]["label"] == "Brandsicherheitswache" and result["positions"][-1]["rate"] == 12.0


def test_missing_vehicle_type_gives_hint(vg, monkeypatch):
    _incident(vg, monkeypatch, FULL.replace("02/24-01", "02/71-01"))
    result = _fees(vg).json()
    assert any("02/71" in h and "Fahrzeugtyp" in h for h in result["hints"])


def test_only_vg_lead_maintains_and_calculates(vg, monkeypatch):
    _incident(vg, monkeypatch)
    schedules = vg.get("/api/admin/vgs/vg-a/fees").json()["schedules"]
    draft = schedules[0]
    rates = {**draft["rates"], "vehicles": draft["rates"]["vehicles"] + [{"code": "HLF 20", "rate": 1}]}
    assert vg.put(f"/api/admin/vgs/vg-a/fees/{draft['id']}",
                  json={"name": "x", "valid_from": "2030-01-01", "rates": rates}).status_code == 422
    assert vg.delete(f"/api/admin/vgs/vg-a/fees/{draft['id']}").status_code == 200
    assert len(vg.get("/api/admin/vgs/vg-a/fees").json()["schedules"]) == 1

    lead = login(vg, "lead@example.org")
    lead.cookies.set("scope", "t:wehr-a1")
    assert lead.get("/api/admin/vgs/vg-a/fees").status_code == 403
    assert _fees(lead).status_code == 403


def test_suggest_type_prefers_fee_schedule():
    fee_types = ["LF 10", "HLF 20", "TLF 16/25", "DLK 23/12"]
    assert fees.suggest_type(["TLF 3000", "TLF 16/24Tr", "TLF16/25"], fee_types) == "TLF 16/25"
    assert fees.suggest_type(["HLF 20", "HLF 20/16", "LF 24"], fee_types) == "HLF 20"
    assert fees.suggest_type(["LF 10", "HLF 10"], fee_types + ["HLF 10"]) == ""      # zwei möglich
    assert fees.suggest_type(["TSF"], fee_types) == "TSF"
