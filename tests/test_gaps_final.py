# -*- coding: utf-8 -*-
"""Letzte Lücken: Zweige, die nur selten oder nur in Kombination erreicht werden."""
import dataclasses
import datetime as dt
import io
import logging
import runpy
import sys
from types import SimpleNamespace

import openpyxl
import pytest
from fastapi import HTTPException

from app import auth, db, importing, mail, main, records, report, store, tenancy, xlsx_report
from app.api import common, reports as reports_api
from app.tenant_config import Vehicle
from conftest import CFG, grant, login, make_tenant
from test_admin import _as, world  # noqa: F401  (Fixture world)
from test_api import client  # noqa: F401  (Fixture client)
from test_mail import smtp  # noqa: F401  (Fixture smtp)
from test_report import read



# ---------------------------------------------------------------- Verwaltung
def test_lead_sees_no_vg_administration(world):
    _as(world, "lead@example.org")
    overview = world.get("/api/admin").json()
    assert overview["vgs"] == [] and [t["slug"] for t in overview["tenants"]] == ["wehr-a1"]


def test_role_with_unknown_grant_target_is_rejected_after_ceiling_check(world):
    """Der Deckel prüft auch Rollen aus der Verteilung; eine unbekannte Rolle scheitert danach als 422."""
    grant("vglead@example.org", "viewer", tenancy.access_for(None, "t:wehr-b1").selected.id)   # Rolle in zweiter VG
    _as(world, "vglead@example.org")
    held = next(r["id"] for r in world.get("/api/admin/roles").json()["roles"] if r["key"] == "vg_lead")
    response = world.post("/api/admin/roles", json={"label": "Neu", "scope": "tenant", "vg": "vg-a", "permissions": [],
                                                    "granted_by": [held], "grants": [99999]})
    assert response.status_code == 422


def test_lead_cannot_revoke_role_it_may_not_grant(world):
    with tenancy.central() as con:
        a1 = con.execute("SELECT id FROM tenant WHERE slug = 'wehr-a1'").fetchone()[0]
    grant("zweiter@example.org", "lead", a1)
    _as(world, "lead@example.org")
    response = world.delete("/api/admin/memberships", params={
        "email": "zweiter@example.org", "scope": "tenant", "slug": "wehr-a1", "role": "lead"})
    assert response.status_code == 403 and "nicht entziehen" in response.json()["detail"]


def test_fee_schedule_can_be_created(world):
    from app import legacy
    _as(world, "vglead@example.org")
    created = world.post("/api/admin/vgs/vg-a/fees", json={
        "name": "Neue Satzung", "valid_from": "2031-01-01", "rates": legacy.FEE_SCHEDULE_2024["rates"]})
    assert created.status_code == 200
    assert "Neue Satzung" in [s["name"] for s in created.json()["schedules"]]


# ---------------------------------------------------------------- Sitzungen und Plattform
def test_claim_with_unknown_filename_yields_nothing():
    from app import preview_sessions
    sessions = preview_sessions.PreviewSessions()
    token = sessions.add([({"filename": "a.pdf"}, "slug")], "owner")
    with sessions.claim(token, "b.pdf", "owner") as entry:
        assert entry == (None, None)
    assert sessions.get(token, "a.pdf", "owner")[0]


def test_explicit_weekend_flag_and_pending_without_report_id(con):
    fields = {"number": 1, "started_at": "2025-03-12T10:00:00", "keyword": "B2"}
    assert store.normalize_fields(fields, weekend_or_holiday=True)["weekend_or_holiday"] == 1
    assert store.normalize_fields(fields, weekend_or_holiday=False)["weekend_or_holiday"] == 0
    pending_id = store.add_pending(con, {"keyword": "B", "subcode": "2"}, "x.pdf", b"x")
    assert store.pending_pdf(con, pending_id) == ("x.pdf", b"x")


def test_mail_module_runs_as_script(smtp, monkeypatch):
    mail.check_config()                                           # vollständige Konfiguration mit vorhandenem Schlüssel
    monkeypatch.setattr(sys, "argv", ["app.mail"])
    sys.modules.pop("app.mail", None)
    try:
        with pytest.raises(SystemExit):
            runpy.run_module("app.mail", run_name="__main__")
    finally:
        import app.mail  # noqa: F401  (Modul wieder laden)


def test_access_log_filter_leaves_dict_arguments_alone():
    record = logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1, "%(x)s", ({"x": "token=geheim"},), None)
    record.args = {"x": "token=geheim"}
    assert main._MaskLoginToken().filter(record) is True and record.args == {"x": "token=geheim"}


def test_unknown_asset_names_do_not_appear_in_branding(client):
    with db.connection(tenancy.tenant_path("wehr-a1")) as con:
        con.execute("INSERT INTO asset (name, content_type, data) VALUES ('sonstiges', 'image/png', x'00')")
    branding = client.get("/api/config").json()["branding"]
    assert set(branding) >= {"logo_light", "logo_dark", "icon"} and all(v is None for v in branding.values())


def test_logout_without_cookie_is_harmless(make_client, data_dir):
    c = make_client(login=True)
    assert c.post("/logout", follow_redirects=False).status_code in (200, 303)


# ---------------------------------------------------------------- Nachverarbeitung ohne Job-ID
def test_after_import_without_job_id_notifies_without_bookkeeping(client):
    tenant = tenancy.access_for(None, "t:wehr-a1").selected
    parsed = read()
    access = SimpleNamespace(email="fremd@example.org", is_member=lambda t: False)
    importing.after_import(access, tenant, parsed, 1, False)
    with tenancy.central() as con:
        assert con.execute("SELECT COUNT(*) FROM completed_import").fetchone()[0] == 0


def test_notify_others_stays_silent_when_vehicles_match(data_dir):
    OTHER = dataclasses.replace(CFG, fleet=(Vehicle("01/46"),), own_prefix="01/", unit_marker="FW NR#.MUS 01")
    make_tenant("wehr-a1")
    make_tenant("wehr-a2", cfg=OTHER)
    with db.connection(tenancy.tenant_path("wehr-a2")) as con:
        incident_id = store.create_incident(con, {"number": 1, "started_at": "2025-03-12T10:00:00", "keyword": "B",
                                                  "subcode": "2", "bks_record_id": "9000001"}, source="pdf")
        store.add_vehicle(con, incident_id, "01/46", "FL NR#.MUS 01/46-01", 6, "10:07:00", "10:12:00")
    tenants = list(tenancy.vg_tenants(tenancy.access_for(None, "t:wehr-a1").selected.vg_id))
    source = {"bks_record_id": "9000001", "keyword": "B", "subcode": "2", "first_alarm": dt.datetime(2025, 3, 12, 10)}
    vehicles = [{"name": "FL NR#.MUS 01/46-01", "crew": 6, "alerted": None, "departed": dt.datetime(2025, 3, 12, 10, 7),
                 "arrived": dt.datetime(2025, 3, 12, 10, 12), "finished": None}]
    with tenancy.central() as con:
        records.notify_others(con, source, vehicles, "Bericht", tenants)
        assert con.execute("SELECT COUNT(*) FROM notice").fetchone()[0] == 0


# ---------------------------------------------------------------- report und xlsx
def test_same_block_twice_is_registered_once():
    cfg = dataclasses.replace(CFG, fleet=(Vehicle("02/45"),))
    r = read()
    template = dict(r["vehicles"][0])
    r["vehicles"] = [{**template, "name": "FL NR#.MUS 02/99-01", "call_sign": None},
                     {**template, "name": "FL NR#.MUS 02/99-02", "call_sign": None}]
    r["people"] = []
    slots = report.assign_vehicles(r, cfg)
    assert r["new_vehicles"].count("02/99") == 1 and len(slots) == 1


def test_plausibility_without_start_or_end_adds_no_duration_warning():
    r = read()
    r["warnings"].clear()
    r["started_at"], r["ended_at"] = None, dt.datetime(2025, 3, 12, 11)
    report.check_plausibility(r, CFG)
    assert not any("Einsatzende liegt vor" in w or "über" in w for w in r["warnings"])


def test_blank_rows_in_workbook_are_skipped():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws["A1"], ws["A3"] = "oben", "unten"
    data = io.BytesIO()
    wb.save(data)
    sheets = xlsx_report.read_workbook(data.getvalue())
    assert [row[0] for row in next(iter(sheets.values()))] == ["oben", "unten"]


# ---------------------------------------------------------------- Vorgaben der VG: seltene Stichworte
def test_keyword_only_in_a_minority_of_tenants_is_not_lifted(data_dir):
    for slug in ("wehr-a1", "wehr-a2", "wehr-a3"):
        make_tenant(slug)
    for slug, codes in (("wehr-a1", ("B1", "X1.01")), ("wehr-a2", ("B1",)), ("wehr-a3", ("B1",))):
        with db.connection(tenancy.tenant_path(slug)) as con:
            con.executemany("INSERT INTO keyword (code, name, terms, sort_order) VALUES (?, ?, '', ?)",
                            [(c, f"Name {c}", i) for i, c in enumerate(codes, 1)])
    with tenancy.central() as con:
        con.execute("UPDATE vg SET defaults_lifted = 0")
    tenancy._configs.clear()
    tenancy.lift_vg_defaults()
    layer = tenancy.access_for(None, "t:wehr-a1").selected.layer
    assert "X1.01" not in {k["code"] for k in layer.keyword_list}


# ---------------------------------------------------------------- API: Übernahme-Fehler und Jobs
def test_upload_slot_is_released_when_collecting_fails(client, monkeypatch):
    def broken(uploads):
        raise OSError("Platte voll")

    original = reports_api.collect_uploads
    monkeypatch.setattr(reports_api, "collect_uploads", broken)
    from test_xlsx_report import make_workbook
    files = [("pdfs", ("17-25.xlsx", make_workbook(), "application/octet-stream"))]
    with pytest.raises(OSError):
        client.post("/api/reports", files=files)
    monkeypatch.setattr(reports_api, "collect_uploads", original)
    assert client.post("/api/reports", files=files).status_code == 200


def test_background_job_start_refusal_releases_everything(client, monkeypatch):
    def refuse(*args, **kwargs):
        raise HTTPException(429, "Zu viele")

    original = common.read_jobs.start
    monkeypatch.setattr(common.read_jobs, "start", refuse)
    from test_xlsx_report import make_workbook
    files = [("pdfs", ("17-25.xlsx", make_workbook(), "application/octet-stream"))]
    assert client.post("/api/reports?background=true", files=files).status_code == 429
    monkeypatch.setattr(common.read_jobs, "start", original)
    assert client.post("/api/reports", files=files).status_code == 200


def test_failed_job_status_is_returned_as_error(client):
    def fail(progress):
        raise HTTPException(422, "Bericht unlesbar")

    job = common.read_jobs.start(None, 1, fail)
    for _ in range(100):
        response = client.get(f"/api/reports/jobs/{job}")
        if response.status_code != 200 or response.json().get("done"):
            break
    assert response.status_code == 422 and response.json()["detail"] == "Bericht unlesbar"


def test_forward_acceptance_edge_cases(client, monkeypatch):
    a = tenancy.access_for(None, "t:wehr-a1")
    acceptance = SimpleNamespace(replace=False, revision=None, fields=None)
    gone = {"_action": "forward", "_target": "gibt-es-nicht", "filename": "x.pdf", "_data": b"x"}
    with pytest.raises(HTTPException) as missing:
        reports_api._accept_report(acceptance, a, gone, "wehr-a1")
    assert missing.value.status_code == 409

    def full(*args):
        raise ValueError("Zu viele Berichte")

    monkeypatch.setattr(reports_api, "forward", full)
    full_target = {**gone, "_target": "wehr-a1"}
    with pytest.raises(HTTPException) as refused:
        reports_api._accept_report(acceptance, a, full_target, "wehr-a1")
    assert refused.value.status_code == 409


def test_accepting_with_invalid_corrected_fields_is_unprocessable(client):
    from test_xlsx_report import make_workbook
    data = client.post("/api/reports", files=[("pdfs", ("17-25.xlsx", make_workbook(), "application/octet-stream"))]).json()
    response = client.post("/api/reports/accept", json={
        "token": data["token"], "filename": "17-25.xlsx",
        "fields": {"started_at": "2025-03-12T12:00:00", "ended_at": "2025-03-12T10:00:00"}})
    assert response.status_code == 422
