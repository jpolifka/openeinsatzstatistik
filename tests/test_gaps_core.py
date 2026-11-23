# -*- coding: utf-8 -*-
"""Lücken in records, tenancy, tenant_config und tenant_lifecycle."""
import dataclasses
import datetime as dt
from pathlib import Path

import pytest

from app import db, records, store, tenancy, tenant_lifecycle
from app.tenant_config import Vehicle
from conftest import CFG, make_tenant

OTHER = dataclasses.replace(CFG, fleet=(Vehicle("01/46"),), own_prefix="01/", unit_marker="FW NR#.MUS 01")


def _tenants(vg_slug="vg-a"):
    with tenancy.central() as con:
        vg_id = con.execute("SELECT id FROM vg WHERE slug = ?", (vg_slug,)).fetchone()[0]
    return vg_id, list(tenancy.vg_tenants(vg_id))


def _incident(slug, **fields):
    values = {"number": 1, "started_at": "2025-03-12T10:00:00", "keyword": "B", "subcode": "2",
              "bks_record_id": "9000001", "place": "Altenau", **fields}
    with db.connection(tenancy.tenant_path(slug)) as con:
        return store.create_incident(con, values, source="pdf")


# ---------------------------------------------------------------- records
def test_check_reports_keyword_conflict_without_master(data_dir):
    make_tenant("wehr-a1")
    make_tenant("wehr-a2", cfg=OTHER)
    _incident("wehr-a1", keyword="B", subcode="2")
    _incident("wehr-a2", keyword="H", subcode="1")
    vg_id, tenants = _tenants()
    with tenancy.central() as con:
        result = records.check(con, vg_id, "9000001", tenants)
    kinds = {(f["tenant"], f["kind"], f["stored"]) for f in result["findings"]}
    assert {("wehr-a1", "keyword", "B.2"), ("wehr-a2", "keyword", "H.1")} <= kinds
    assert result["record"] == {"bks_record_id": "9000001"}


def test_check_against_master_reports_keyword_missing_people_and_number(data_dir):
    make_tenant("wehr-a1")
    _incident("wehr-a1", keyword="B", subcode="2", number=None)
    vg_id, tenants = _tenants()
    master = {"bks_record_id": "9000001", "keyword": "H", "subcode": "1", "first_alarm": dt.datetime(2025, 3, 12, 10),
              "vehicles": [{"name": "FL NR#.MUS 02/45-01", "crew": 2, "alerted": None, "departed": None,
                            "arrived": None, "finished": None}]}
    with tenancy.central() as con:
        records.save_master(con, vg_id, master, "a@example.org")
        result = records.check(con, vg_id, "9000001", tenants)
    by_kind = {f["kind"]: f for f in result["findings"]}
    assert by_kind["keyword"]["source"] == "H.1" and by_kind["keyword"]["stored"] == "B.2"
    assert by_kind["unedited"]["field"] == "Anwesenheit"
    assert by_kind["no_number"]["stored"] == "fehlt"


def test_open_notices_of_nobody_is_empty(data_dir):
    with tenancy.central() as con:
        assert records.open_notices(con, []) == []


def test_notify_others_marks_pending_report_as_not_missing(data_dir):
    """Liegt der Bericht der anderen Wehr bereits zur Übernahme bereit, gibt es keinen Hinweis „fehlt“."""
    _, a1 = make_tenant("wehr-a1")
    make_tenant("wehr-a2", cfg=OTHER)
    _, tenants = _tenants()
    target = next(t for t in tenants if t.slug == "wehr-a2")
    with target.connection() as con:
        store.add_pending(con, {"bks_report_id": "9000009", "bks_record_id": "9000001", "keyword": "B"}, "x.pdf", b"x")
    source = {"bks_record_id": "9000001", "keyword": "B", "subcode": "2", "first_alarm": dt.datetime(2025, 3, 12, 10)}
    vehicles = [{"name": "FL NR#.MUS 01/46-01", "crew": 3, "alerted": None, "departed": None, "arrived": None,
                 "finished": None}]
    with tenancy.central() as con:
        records.notify_others(con, source, vehicles, "Bericht von Wehr wehr-a1", tenants, exclude=a1)
        assert records.open_notices(con, [target.id]) == []


# ---------------------------------------------------------------- tenant_config
def test_block_and_new_call_sign_edge_cases():
    assert CFG.block_of("") is None and CFG.block_of(None) is None
    assert CFG.new_call_sign("Sonderfahrzeug ohne Nummer") == "Sonderfahrzeug ohne Nummer"
    assert CFG.new_call_sign("FL NR#.MUS 02/45-01", taken={"02/45", "02/45-01"}) == "FL NR#.MUS 02/45-01"


# ---------------------------------------------------------------- tenancy
def test_setting_keys_are_validated_and_removable(data_dir):
    vg_id, _ = make_tenant("wehr-a1")
    with tenancy.central() as con:
        with pytest.raises(KeyError):
            tenancy.save_vg_settings(con, vg_id, {"gibt_es_nicht": 1})
    tenant = tenancy.access_for(None, "t:wehr-a1").selected
    with tenant.connection() as con:
        with pytest.raises(KeyError):
            tenancy.save_tenant_values(con, {"gibt_es_nicht": 1})
        tenancy.save_tenant_values(con, {"plan_places": ["Altenau"]})
        assert con.execute("SELECT COUNT(*) FROM setting WHERE key = 'plan_places'").fetchone()[0] == 1
        tenancy.save_tenant_values(con, {"plan_places": None})
        assert con.execute("SELECT COUNT(*) FROM setting WHERE key = 'plan_places'").fetchone()[0] == 0


def test_lift_without_station_code_keeps_vg_code_out(data_dir):
    """Wehr mit Einstellungen, deren Präfixe keine VG-Kennung ergeben: sie erbt die Kennung der VG nicht."""
    odd = dataclasses.replace(CFG, unit_marker="", unit_prefix="XX ", own_prefix="", control_center="FL NR#.ABC")
    make_tenant("wehr-a1", cfg=odd)
    with tenancy.central() as con:
        con.execute("UPDATE vg SET defaults_lifted = 0")
    tenancy._configs.clear()
    tenancy.lift_vg_defaults()
    with tenancy.access_for(None, "t:wehr-a1").selected.connection() as con:
        stored = con.execute("SELECT value FROM setting WHERE key = 'bks_code'").fetchone()
    assert stored is not None and stored[0] == '""'            # bewusst leer, nicht die Kennung der VG


def test_grant_of_unknown_role_is_rejected(data_dir):
    _, tenant_id = make_tenant("wehr-a1")
    with tenancy.central() as con:
        with pytest.raises(ValueError, match="gibt es in diesem Bereich nicht"):
            tenancy.grant(con, "a@example.org", "gibt_es_nicht", tenant_id)


def test_access_requires_one_selected_tenant(data_dir):
    vg_id, a1 = make_tenant("wehr-a1")
    make_tenant("wehr-a2", cfg=OTHER)
    with tenancy.central() as con:
        tenancy.grant(con, "vg@example.org", "vg_stats", vg_id)
    overview = tenancy.access_for("vg@example.org", "vg:vg-a")
    with pytest.raises(tenancy.Forbidden, match="einzelne Wehr"):
        overview.current("stats.view")
    nobody = tenancy.access_for("keiner@example.org")
    with pytest.raises(tenancy.Forbidden, match="Keine Wehr zugeordnet"):
        nobody.current("stats.view")
    with pytest.raises(tenancy.Forbidden):
        nobody.tenant("wehr-a1", "stats.view")


# ---------------------------------------------------------------- tenant_lifecycle
def test_begin_archive_of_unknown_tenant(data_dir):
    with tenancy.central() as con:
        with pytest.raises(KeyError):
            tenant_lifecycle.begin_archive(con, "gibt-es-nicht", None)


def test_finish_without_job_is_a_noop(data_dir):
    assert tenant_lifecycle.finish_archive("gibt-es-nicht") is True


def test_finish_refuses_when_source_and_archive_exist(data_dir):
    make_tenant("wehr-a")
    with tenancy.central() as con:
        tenant_lifecycle.begin_archive(con, "wehr-a", None)
        target = con.execute("SELECT target FROM tenant_archive").fetchone()[0]
    (data_dir / "deleted" / target).mkdir(parents=True)
    assert tenant_lifecycle.finish_archive("wehr-a") is False
    assert Path(tenancy.tenant_path("wehr-a")).exists()


def test_finish_refuses_when_archive_database_is_missing(data_dir):
    make_tenant("wehr-a")
    with tenancy.central() as con:
        tenant_lifecycle.begin_archive(con, "wehr-a", None)
        target = con.execute("SELECT target FROM tenant_archive").fetchone()[0]
    Path(tenancy.tenant_path("wehr-a")).unlink()
    assert tenant_lifecycle.finish_archive("wehr-a") is False
    with tenancy.central() as con:
        assert con.execute("SELECT COUNT(*) FROM tenant WHERE slug = 'wehr-a'").fetchone()[0] == 1
    assert target


def test_finish_with_tenant_row_already_gone_clears_job(data_dir):
    make_tenant("wehr-a")
    with tenancy.central() as con:
        tenant_lifecycle.begin_archive(con, "wehr-a", None)
        con.execute("PRAGMA foreign_keys = OFF")
        con.execute("DELETE FROM tenant WHERE slug = 'wehr-a'")
    assert tenant_lifecycle.finish_archive("wehr-a") is True
    with tenancy.central() as con:
        assert con.execute("SELECT COUNT(*) FROM tenant_archive").fetchone()[0] == 0


def test_retry_archives_finishes_open_jobs(data_dir):
    make_tenant("wehr-a")
    with tenancy.central() as con:
        tenant_lifecycle.begin_archive(con, "wehr-a", None)
    tenant_lifecycle.retry_archives()
    with tenancy.central() as con:
        assert con.execute("SELECT COUNT(*) FROM tenant WHERE slug = 'wehr-a'").fetchone()[0] == 0
