# -*- coding: utf-8 -*-
"""Kostenersatz nach der Gebührenordnung der VG (Satzung Bad Hönningen 2024 als Beispiel)."""
from app import pdf_report
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


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True, -1])
def test_fee_rates_reject_nonfinite_and_invalid_values(value):
    rates = {**legacy.FEE_SCHEDULE_2024["rates"], "personnel": value}
    with pytest.raises(ValueError):
        fees.check_rates(rates)


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
    monkeypatch.setattr(pdf_report, "extract_text", lambda path: (REPORT + text, left, ""))
    data = client.post("/api/reports", files=[("pdfs", ("a1.pdf", b"x", "application/pdf"))]).json()
    client.post("/api/reports/accept", json={"token": data["token"], "filename": "a1.pdf", "fields": {}})


def _fees(client, **body):
    return client.post("/api/records/9000001/fees", json=body)


def test_costs_of_vehicles_and_personnel(vg, monkeypatch):
    _incident(vg, monkeypatch)
    result = _fees(vg).json()
    assert result["schedule"]["name"] == "Satzung vom 16.05.2024"           # gilt am 12.03.2025
    rows = [(p["kind"], p["label"], p["count"], p["hours"], p["rate"], p["amount"]) for p in result["positions"]]
    # 02/45: Ausrücken 10:12 bis Ende 10:48 (37 Min. -> 1 h); 2 Personen (Stärke auf den Fahrzeugen, nicht die Anwesenheitsliste) 10:08 bis 11:05 (57 Min. -> 1 h)
    assert rows == [("vehicle", "02/24 MTF", 1, 1, 37.0, 37.0), ("vehicle", "02/45 HLF 20", 1, 1, 447.0, 447.0),
                    ("personnel", "Einsatzkräfte (ehrenamtlich)", 2, 1, 33.45, 66.9)]
    assert (result["net"], result["total"], result["hints"]) == (550.9, 550.9, [])
    assert [s["name"] for s in result["schedules"]] == ["Entwurf 2030", "Satzung vom 16.05.2024"]

    result = _fees(vg, schedule_id=result["schedules"][0]["id"], vat_percent=19,
                   expenses=[{"label": "Bindemittel", "amount": 100}]).json()
    assert [p["amount"] for p in result["positions"] if p["kind"] in ("expense", "surcharge")] == [100.0, 10.0]
    assert result["positions"][2]["rate"] == 40.0
    assert (result["net"], result["vat"], result["total"]) == (674.0, 128.06, 802.06)


def test_only_deployed_vehicles_and_their_crew_are_billed(vg, monkeypatch):
    """Anwesende im Gerätehaus und nicht eingesetzte Fahrzeuge (nur bereit) werden nicht abgerechnet."""
    _incident(vg, monkeypatch)
    with db.connection(tenancy.tenant_path("wehr-a1")) as con:
        con.execute("DELETE FROM attendance")
        con.execute("UPDATE vehicle SET deployed = 1, crew = 3")
        con.execute("UPDATE vehicle SET deployed = 0, crew = 5 WHERE call_sign = '02/24'")
    result = _fees(vg).json()
    assert [p["label"] for p in result["positions"] if p["kind"] == "vehicle"] == ["02/45 HLF 20"]
    assert [p["count"] for p in result["positions"] if p["kind"] == "personnel"] == [3]
    assert any("02/24" in h and "nicht eingesetzt" in h for h in result["hints"])


def test_alarm_system_is_capped_and_fire_watch_has_own_rate(vg, monkeypatch):
    _incident(vg, monkeypatch, FULL.replace("B2.08", "B2.07"), LEFT.replace("B2.08", "B2.07"))
    result = _fees(vg).json()
    assert result["bma_cap"] and result["total"] == 400.0
    assert _fees(vg, bma_cap=False).json()["total"] == 550.9          # kein Fehlalarm: volle Kosten

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


def test_vehicle_minutes_use_incident_end_with_date():
    """Ohne eigenes Ende gilt das Einsatzende mit Datum – auch über 24 Stunden (nicht modulo 24 h)."""
    import datetime as dt
    start, end = dt.datetime(2025, 3, 12, 22, 0), dt.datetime(2025, 3, 14, 0, 30)
    assert fees._vehicle_minutes({"departed": "22:10:00"}, start, end) == 26 * 60 + 20
    assert fees._vehicle_minutes({"departed": "00:10:00"}, start, end) == 24 * 60 + 20   # nach Mitternacht
    assert fees._vehicle_minutes({"departed": "22:10:00", "finished": "23:40:00"}, start, end) == 90


def test_substitute_and_schedule_hints(vg, monkeypatch):
    """Ersatzfahrzeug wird nach seinem eigenen Typ berechnet; Einsatz vor der Gebührenordnung gibt einen Hinweis."""
    with tenancy.central() as con:
        vg_id = con.execute("SELECT id FROM vg WHERE slug = 'vg-a'").fetchone()[0]
    with db.connection(tenancy.tenant_path("wehr-a1")) as con:
        con.execute("INSERT INTO setting (key, value) VALUES ('substitutes', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value", ('{"FL NR#.BHÖ 02/24-01": "02/45"}',))
        con.execute("UPDATE fleet SET name = 'FL NR#.BHÖ 02/24-01' WHERE call_sign = '02/24'")   # Typ MTF
    tenancy.forget_config("wehr-a1")
    _incident(vg, monkeypatch, FULL.replace("FL NR#.BHÖ 02/45-01", "FL NR#.BHÖ 02/19-01"))
    with db.connection(tenancy.tenant_path("wehr-a1")) as con:
        con.execute("UPDATE vehicle SET call_sign = '02/45', name = 'FL NR#.BHÖ 02/24-01' WHERE call_sign = '02/24'")
    result = _fees(vg).json()
    vehicle = next(p for p in result["positions"] if p["kind"] == "vehicle" and "Ersatz" in p["label"])
    assert vehicle["label"].endswith("MTF") and vehicle["rate"] == 37.0
    with tenancy.central() as con:
        con.execute("UPDATE fee_schedule SET valid_from = '2026-01-01' WHERE vg_id = ? AND valid_from < '2030'", (vg_id,))
    response = _fees(vg)
    assert response.status_code == 422
    assert "keine gültige Gebührenordnung" in response.json()["detail"]
    assert _fees(vg, schedule_id=999999).status_code == 422
