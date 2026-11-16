# -*- coding: utf-8 -*-
"""Verwaltung: Eingabeprüfung, Fehlerfälle und seltene Wege der Admin-Endpunkte."""
import dataclasses
import io

import openpyxl
import pytest

from app import db, records, tenancy, tenant_lifecycle
from app.tenant_config import TenantConfig
from conftest import CFG, grant, login, make_tenant
from test_admin import _as, _fleet_payload, _settings, world  # noqa: F401  (Fixture world)


# ---------------------------------------------------------------- Einstellungen einer Wehr
@pytest.mark.parametrize("change, message", [
    ({"places": [{"name": " "}]}, "eindeutigen Namen"),
    ({"places": [{"name": "Altenau"}, {"name": "altenau"}]}, "eindeutigen Namen"),
    ({"plan_min_level": 9}, "Mindest-Alarmstufe"),
    ({"numbering": "zufall"}, "Nummerierung"),
    ({"unit_marker": "", "own_prefix": "2/"}, "Eigener Präfix"),
    ({"fleet": [{"call_sign": "02/45", "replaced_by": "02/99"}]}, "Nachfolger"),
])
def test_more_invalid_settings(world, change, message):
    _as(world, "lead@example.org")
    response = world.put("/api/admin/wehr-a1/settings", json={**_settings(world), **change})
    assert response.status_code == 422 and message in response.json()["detail"], response.text


def test_numbering_by_date_renumbers_existing_years(world):
    with db.connection(tenancy.tenant_path("wehr-a1")) as con:
        for number, day in ((7, "2025-05-01"), (9, "2025-02-01")):
            con.execute("INSERT INTO incident (year, number, started_at, source) VALUES (2025, ?, ?, 'pdf')",
                        (number, f"{day}T10:00:00"))
    _as(world, "lead@example.org")
    assert world.put("/api/admin/wehr-a1/settings", json={**_settings(world), "numbering": "by_date"}).status_code == 200
    with db.connection(tenancy.tenant_path("wehr-a1")) as con:
        rows = con.execute("SELECT number FROM incident ORDER BY started_at").fetchall()
    assert [r[0] for r in rows] == [1, 2]


def test_settings_without_plan_release_keep_release_state(world):
    _as(world, "vglead@example.org")
    created = world.post("/api/admin/roles", json={"label": "Einsteller", "scope": "tenant", "vg": "vg-a",
                                                   "permissions": ["tenant.settings"]})
    assert created.status_code == 200, created.text
    with tenancy.central() as con:
        a1 = con.execute("SELECT id FROM tenant WHERE slug = 'wehr-a1'").fetchone()[0]
    grant("einsteller@example.org", "einsteller", a1)
    _as(world, "einsteller@example.org")
    current = _settings(world)
    assert current["response_plan_public"] is False
    saved = world.put("/api/admin/wehr-a1/settings", json={**current, "response_plan_public": True})
    assert saved.status_code == 200 and saved.json()["response_plan_public"] is False


def test_unconfigured_tenant_shows_vg_code_and_master_vehicles(world):
    vg_id, _ = make_tenant("wehr-leer", "vg-a", cfg=TenantConfig(name=""))
    with tenancy.central() as con:
        records.save_master(con, vg_id, {"bks_record_id": "9000001", "keyword": "B", "subcode": "2", "town": "Musterstadt",
                                         "vehicles": [{"name": "FL NR#.MUS 01/46-01", "crew": 2, "alerted": None,
                                                       "departed": None, "arrived": None, "finished": None}]})
        tenancy.save_vg_settings(con, vg_id, {"bks_code": "NR#.ABC"})
    tenancy.forget_vg_config(vg_id)
    _as(world, "vglead@example.org")
    settings = world.get("/api/admin/wehr-leer/settings").json()
    assert settings["bks_code"] == "NR#.ABC"
    assert "FL NR#.MUS 01/46-01" in [v["name"] for v in settings["known_vehicles"]]
    assert "Musterstadt" in settings["known_places"]


def test_theme_check_reports_unparsable_colors(world):
    _as(world, "lead@example.org")
    result = world.post("/api/admin/theme-check", json={"colors": {"brand": "kein-farbwert"}}).json()
    assert result["palette"] is None and result["problems"]


# ---------------------------------------------------------------- Stichwortkatalog
def _xlsx(rows):
    wb = openpyxl.Workbook()
    for row in rows:
        wb.active.append(row)
    data = io.BytesIO()
    wb.save(data)
    return data.getvalue()


def _import(client, name, data, mode="preview", base="/api/admin/wehr-a1"):
    return client.post(f"{base}/keywords/import?mode={mode}", files={"file": (name, data, "application/octet-stream")})


def test_keyword_import_from_excel_and_error_cases(world):
    _as(world, "lead@example.org")
    ok = _import(world, "katalog.xlsx", _xlsx([("Stichwort", "Bezeichnung", "Suchbegriffe"),
                                               ("S9.01", "Neues Stichwort", "Test")]))
    assert ok.status_code == 200 and ok.json()["new"] == ["S9.01"]
    broken = _import(world, "kaputt.xlsx", b"kein excel")
    assert broken.status_code == 422 and "nicht lesen" in broken.json()["detail"]
    assert _import(world, "a.csv", "B1;A\nB1;B\n".encode()).status_code == 422                  # doppelt
    assert _import(world, "a.csv", "Stichwort;Bezeichnung\n".encode()).status_code == 422       # keine Stichworte
    assert _import(world, "a.csv", ("B1;" + "x" * 300 + "\n").encode()).status_code == 422
    assert _import(world, "a.csv", b"B1;ok\n", mode="irgendwas").status_code == 422
    assert _import(world, "a.csv", b"x" * (2 * 1024 * 1024 + 1)).status_code == 422
    many = "\n".join(f"B{i % 10}.{i % 100:02d};n" for i in range(5001)).encode()
    too_many = _import(world, "a.csv", many)
    assert too_many.status_code == 422 and "5000" in too_many.json()["detail"]


def test_vg_keyword_catalog_management(world):
    _as(world, "vglead@example.org")
    base = "/api/admin/vgs/vg-a/keywords"
    assert world.put(f"{base}/S9.01", json={"name": "Neu", "terms": ""}).status_code == 200
    assert "S9.01" not in {k["code"] for k in world.delete(f"{base}/S9.01").json()["keywords"]}
    assert world.post(f"{base}/template").status_code == 200
    imported = _import(world, "a.csv", b"S9.02;Importiert\n", mode="merge", base="/api/admin/vgs/vg-a")
    assert imported.status_code == 200 and "S9.02" in imported.json()["new"]
    assert world.delete(base).status_code == 200


# ---------------------------------------------------------------- Superadmin
def test_superadmin_edge_cases(world, data_dir):
    _as(world, "admin@example.org")
    assert world.post("/api/super/vgs", json={"slug": "Ungültig!", "name": "VG X"}).status_code == 422
    renamed = world.put("/api/super/vgs/vg-b", json={"slug": "vg-b", "name": "Umbenannte VG"})
    assert "Umbenannte VG" in [v["name"] for v in renamed.json()["vgs"]]
    base = {"slug": "wehr-z", "name": "Wehr Z", "vg": "vg-a"}
    assert world.post("/api/super/tenants", json={**base, "vg": "gibt-es-nicht"}).status_code == 422
    assert world.post("/api/super/tenants", json={**base, "slug": "wehr-a1"}).status_code == 422
    assert world.post("/api/super/tenants", json={**base, "slug": "Ungültig Slug!"}).status_code == 422
    assert world.post("/api/super/tenants", json=base).status_code == 200

    assert world.put("/api/super/tenants/gibt-es-nicht", json={"name": "x"}).status_code == 404
    assert world.put("/api/super/tenants/wehr-z", json={"vg": "gibt-es-nicht"}).status_code == 422
    # Verschieben nur mit Bestätigung des Kurznamens (Schutz vor Fehlklick), und es steht im Protokoll
    assert world.put("/api/super/tenants/wehr-z", json={"vg": "vg-b"}).status_code == 422
    moved = world.put("/api/super/tenants/wehr-z", json={"name": "Wehr Zett", "vg": "vg-b"}, params={"confirm": "wehr-z"})
    assert all("blocked" in v for v in moved.json()["vgs"])
    with tenancy.central() as con:
        assert con.execute("SELECT 1 FROM role_event WHERE action = 'Wehr verschoben'").fetchone()
    entry = next(t for t in moved.json()["tenants"] if t["slug"] == "wehr-z")
    assert (entry["name"], entry["vg"]) == ("Wehr Zett", "vg-b")
    assert world.delete("/api/super/tenants/gibt-es-nicht", params={"confirm": "gibt-es-nicht"}).status_code == 404

    with tenancy.central() as con:
        tenant_lifecycle.begin_archive(con, "wehr-z", None)
    assert world.put("/api/super/tenants/wehr-z", json={"name": "x"}).status_code == 409
    pending = world.get("/api/super/overview").json()
    assert pending["pending_archives"] == ["wehr-z"]
    assert next(t for t in pending["tenants"] if t["slug"] == "wehr-z")["incidents"] is None


def test_ending_unknown_session_is_harmless(world):
    _as(world, "admin@example.org")
    assert world.delete("/api/super/sessions/987654").status_code == 200
    assert world.delete("/api/super/sessions").status_code == 422          # weder Adresse noch „alle anderen“


# ---------------------------------------------------------------- Rollen und Zuordnungen
def test_role_endpoints_report_missing_and_foreign_roles(world):
    _as(world, "vglead@example.org")
    assert world.post("/api/admin/roles", json={"label": "Rolle X", "scope": "tenant", "vg": "gibt-es-nicht",
                                                "permissions": []}).status_code == 404
    assert world.put("/api/admin/roles/99999", json={"label": "Rolle X", "scope": "tenant"}).status_code == 404
    _as(world, "other@example.org")                               # Wehrleiter einer anderen VG
    created = world.post("/api/admin/roles", json={"label": "Fremde Rolle", "scope": "tenant", "vg": "vg-b",
                                                   "permissions": []})
    assert created.status_code == 200
    role_id = next(r["id"] for r in world.get("/api/admin/roles").json()["roles"] if r["label"] == "Fremde Rolle")
    _as(world, "vglead@example.org")
    assert world.put(f"/api/admin/roles/{role_id}", json={"label": "Fremde Rolle", "scope": "tenant"}).status_code == 403


def test_role_can_be_deleted_when_unused(world):
    _as(world, "vglead@example.org")
    world.post("/api/admin/roles", json={"label": "Wegwerfrolle", "scope": "tenant", "vg": "vg-a", "permissions": []})
    role_id = next(r["id"] for r in world.get("/api/admin/roles").json()["roles"] if r["label"] == "Wegwerfrolle")
    assert world.delete(f"/api/admin/roles/{role_id}").status_code == 200
    assert "Wegwerfrolle" not in [r["label"] for r in world.get("/api/admin/roles").json()["roles"]]
    system = next(r["id"] for r in world.get("/api/admin/roles").json()["roles"] if r["key"] == "viewer")
    assert world.delete(f"/api/admin/roles/{system}").status_code in (403, 422)


def test_membership_errors(world):
    _as(world, "vglead@example.org")
    body = {"email": "neu@example.org", "scope": "kreis", "slug": "x", "role": "viewer"}
    assert world.post("/api/admin/memberships", json=body).status_code == 404
    revoke = lambda **kw: world.delete("/api/admin/memberships", params={  # noqa: E731
        "email": "gibt-es@example.org", "scope": "tenant", "slug": "wehr-a1", "role": "viewer", **kw})
    assert revoke().status_code == 404                              # Rolle da, Zuordnung nicht
    assert revoke(role="gibt-es-nicht").status_code == 404
    grant("hat@example.org", "viewer", 1)
    assert _as(world, "lead@example.org").delete("/api/admin/memberships", params={
        "email": "hat@example.org", "scope": "tenant", "slug": "wehr-a1", "role": "viewer"}).status_code == 200


def test_effective_permissions_of_person_without_membership(world):
    _as(world, "vglead@example.org")
    result = world.get("/api/admin/users/effective", params={"email": "niemand@example.org"}).json()
    assert result["areas"] == [] and result["superadmin"] is False


# ---------------------------------------------------------------- VG: Gebührenordnung, Vorgaben, Fahrzeuge
def test_fee_schedule_update_of_unknown_version(world):
    _as(world, "vglead@example.org")
    from app import legacy
    response = world.put("/api/admin/vgs/vg-a/fees/99999", json={
        "name": "x", "valid_from": "2030-01-01", "rates": legacy.FEE_SCHEDULE_2024["rates"]})
    assert response.status_code == 404


def test_vg_settings_validation(world):
    _as(world, "vglead@example.org")
    base = world.get("/api/admin/vgs/vg-a/settings").json()
    put = lambda **change: world.put("/api/admin/vgs/vg-a/settings", json={**base, **change})  # noqa: E731
    assert put(bks_code="NR# ungültig").status_code == 422
    assert put(tenants=[{"slug": "wehr-b1", "station": "01"}], bks_code="NR#.ABC").status_code == 404
    assert put(tenants=[{"slug": "wehr-a1", "station": "1"}], bks_code="NR#.ABC").status_code == 422
    assert put(tenants=[{"slug": "wehr-a1", "plan_places": ["Nirgendwo"]}], bks_code="NR#.ABC").status_code == 422


def test_vg_fleet_error_names_the_tenant(world):
    _as(world, "vglead@example.org")
    data = world.get("/api/admin/vgs/vg-a/fleet").json()
    broken = _fleet_payload(data, wehr_a2=lambda fleet: fleet + [{"call_sign": "<b>"}])
    response = world.put("/api/admin/vgs/vg-a/fleet", json=broken)
    assert response.status_code == 422 and response.json()["detail"].startswith("Wehr wehr-a2:")


def test_slugs_are_generated(world):
    """Kurznamen bildet die App selbst: <vg>-<wehr>-<lfd>; gleicher Ortsname in zwei VGs bleibt eindeutig."""
    _as(world, "admin@example.org")
    created = world.post("/api/super/vgs", json={"name": "VG Musterstadt"}).json()
    assert "musterstadt" in [v["slug"] for v in created["vgs"]]
    first = world.post("/api/super/tenants", json={"name": "Feuerwehr Bergheim", "vg": "musterstadt"}).json()
    again = world.post("/api/super/tenants", json={"name": "Feuerwehr Bergheim", "vg": "musterstadt"}).json()
    other = world.post("/api/super/tenants", json={"name": "Feuerwehr Bergheim", "vg": "vg-b"}).json()
    slugs = [t["slug"] for t in other["tenants"]]
    assert {"musterstadt-bergheim-01", "musterstadt-bergheim-02", "b-bergheim-01"} <= set(slugs)
    clash = world.post("/api/super/tenants", json={"slug": "musterstadt-bergheim-01", "name": "Bergheim", "vg": "vg-b"})
    assert clash.status_code == 422 and "Vorschlag" in clash.json()["detail"]
