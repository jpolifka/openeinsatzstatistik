# -*- coding: utf-8 -*-
"""Verwaltung: Einstellungen, Logos, Stichworte, Rollenvergabe und Superadmin-Funktionen."""
import os

import pytest

from app import db, tenancy
from conftest import grant, login, make_tenant

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 20


@pytest.fixture
def world(make_client):
    vg_a, a1 = make_tenant("wehr-a1", "vg-a")
    _, a2 = make_tenant("wehr-a2", "vg-a")
    vg_b, b1 = make_tenant("wehr-b1", "vg-b")
    grant("lead@example.org", "lead", a1)
    grant("editor@example.org", "editor", a1)
    grant("vglead@example.org", "vg_lead", vg_a)
    grant("other@example.org", "vg_lead", vg_b)
    return make_client(login=True)


def _as(client, email):
    client.cookies.clear()
    return login(client, email)


def _settings(client, slug="wehr-a1"):
    s = client.get(f"/api/admin/{slug}/settings").json()
    for key in ("slug", "palette", "unused_data"):
        s.pop(key)
    for v in s["fleet"]:
        v.pop("incidents")
    return s


def test_settings_access(world):
    assert _as(world, "lead@example.org").get("/api/admin/wehr-a1/settings").status_code == 200
    assert world.get("/api/admin/wehr-a2/settings").status_code == 403
    assert _as(world, "editor@example.org").get("/api/admin/wehr-a1/settings").status_code == 403
    assert world.get("/api/admin").status_code == 403
    assert _as(world, "vglead@example.org").get("/api/admin/wehr-a2/settings").status_code == 200
    assert world.get("/api/admin/wehr-b1/settings").status_code == 403
    overview = world.get("/api/admin").json()
    assert [t["slug"] for t in overview["tenants"]] == ["wehr-a1", "wehr-a2"] and overview["vgs"][0]["slug"] == "vg-a"


def test_settings_roundtrip_changes_config(world):
    _as(world, "lead@example.org")
    s = _settings(world)
    s["name"] = "Feuerwehr Musterstadt"
    s["colors"] = {"brand": "#004b8d"}
    s["fleet"] = [{"call_sign": "02/45", "label": "HLF 20", "in_service_from": "2024-01-01"},
                  {"call_sign": "02/99", "in_plan_crew": False, "in_service_until": "2025-06-30"}]
    s["substitutes"] = {"01/23": "02/45"}
    saved = world.put("/api/admin/wehr-a1/settings", json=s)
    assert saved.status_code == 200, saved.text
    assert saved.json()["colors"] == {"brand": "#004B8D"} and saved.json()["palette"]["--brand"] == "#004B8D"
    config = world.get("/api/config").json()
    assert config["vehicles"] == ["02/45", "02/99"] and config["plan_excluded_vehicles"] == ["02/99"]
    assert config["name"] == "Feuerwehr Musterstadt" and config["tenant"]["name"] == "Feuerwehr Musterstadt"
    assert world.get("/api/theme.css").text.startswith(":root{--brand:#004B8D;")


@pytest.mark.parametrize("change, message", [
    ({"colors": {"brand": "#FFD700"}}, "zu hell"),
    ({"colors": {"brand": "red;}body{display:none"}}, "#RRGGBB"),
    ({"fleet": [{"call_sign": "HLF"}]}, "wie 02/45"),
    ({"fleet": [{"call_sign": "02/45"}, {"call_sign": "02/45"}]}, "doppelt"),
    ({"fleet": [{"call_sign": "02/45", "in_service_from": "2025-01-01", "in_service_until": "2024-01-01"}]}, "außer Dienst"),
    ({"substitutes": {"01/23": "09/99"}}, "Block"),
    ({"plan_places": ["Nirgendwo"]}, "Ortsliste"),
    ({"response_limits": [8, 10], "default_limit": 12}, "Standardgrenze"),
    ({"second_limit": 9}, "zweite Zeitgrenze"),
    ({"day_hours": [18, 6]}, "Beginn vor Ende"),
    ({"own_prefix": "02"}, "Schrägstrich"),
])
def test_invalid_settings_are_rejected(world, change, message):
    _as(world, "lead@example.org")
    response = world.put("/api/admin/wehr-a1/settings", json={**_settings(world), **change})
    assert response.status_code == 422 and message in response.json()["detail"]


def test_theme_check_and_parse_test(world):
    _as(world, "lead@example.org")
    check = world.post("/api/admin/theme-check", json={"colors": {"brand": "#FFD700"}}).json()
    assert check["problems"] and check["palette"]["--brand"] == "#FFD700"
    line = "FL NR#.BHÖ 02/45-01 0 / 1 / 1 / 2 / 0 12.03.25 10:09:41 - - Ja - 12.03.25 10:48:21"
    found = world.post("/api/admin/parse-test", json={"line": line, "unit_prefix": "FL NR#.BHÖ ",
                                                      "own_prefix": "02/"}).json()["vehicles"]
    assert found == [{"name": "FL NR#.BHÖ 02/45-01", "call_sign": "02/45", "own": True}]


def test_logo_upload(world):
    _as(world, "lead@example.org")
    upload = lambda data, name="logo.png": world.put(  # noqa: E731
        "/api/admin/wehr-a1/assets/logo-light", files={"file": (name, data, "image/png")})
    assert upload(PNG).status_code == 200
    assert world.get("/api/config").json()["branding"]["logo_light"]
    assert upload(b"<svg xmlns='http://www.w3.org/2000/svg' onload='alert(1)'/>", "logo.svg").status_code == 422
    assert upload(PNG + b"0" * 600_000).status_code == 422
    assert world.put("/api/admin/wehr-a1/assets/unbekannt", files={"file": ("a.png", PNG)}).status_code == 404
    assert world.delete("/api/admin/wehr-a1/assets/logo-light").json() == {"ok": True}
    assert world.get("/api/config").json()["branding"]["logo_light"] is None
    assert _as(world, "editor@example.org").put("/api/admin/wehr-a1/assets/logo-light",
                                                  files={"file": ("a.png", PNG)}).status_code == 403


def test_keyword_catalog(world):
    _as(world, "lead@example.org")
    start = world.get("/api/admin/wehr-a1/keywords").json()
    assert not start["custom"] and start["template_missing"] == 0
    added = world.put("/api/admin/wehr-a1/keywords/b1.99", json={"name": "Neues Stichwort", "terms": "Test"}).json()
    assert added["custom"] and len(added["keywords"]) == len(start["keywords"]) + 1
    assert world.put("/api/admin/wehr-a1/keywords/Brand", json={"name": "x"}).status_code == 422
    world.put("/api/admin/wehr-a1/keywords/B1.01", json={"name": "Müllbrand", "terms": "", "active": False})
    catalog = {k["code"]: k for k in world.get("/api/config").json()["keyword_catalog"]}
    assert catalog["B1.99"]["active"] and catalog["B1.01"]["active"] is False and catalog["B1.01"]["name"] == "Müllbrand"
    deleted = world.delete("/api/admin/wehr-a1/keywords/B1.02").json()
    assert deleted["template_missing"] == 1
    assert world.post("/api/admin/wehr-a1/keywords/template").json()["template_missing"] == 0
    reset = world.delete("/api/admin/wehr-a1/keywords").json()
    assert not reset["custom"] and "B1.99" not in {k["code"] for k in reset["keywords"]}


def test_keyword_import(world):
    _as(world, "lead@example.org")
    csv_file = "Stichwort;Bezeichnung;Suchbegriffe\nB1;Grundstufe;\nB1.01;Müllbrand neu;Container\nBrand 9;x;\n"
    def send(mode, data=None):
        return world.post(f"/api/admin/wehr-a1/keywords/import?mode={mode}",
                          files={"file": ("aao.csv", (data or csv_file).encode(), "text/csv")})
    assert send("preview").status_code == 422          # „Brand 9“ ist kein Stichwort
    csv_file = csv_file.replace("Brand 9", "S9.01")
    preview = send("preview").json()
    assert preview["new"] == ["S9.01"] and preview["changed"] == ["B1.01"] and preview["unchanged"] == 1
    assert len(preview["missing"]) > 100
    merged = send("merge").json()
    assert {k["code"]: k["name"] for k in merged["keywords"]}["B1.01"] == "Müllbrand neu" and merged["custom"]
    replaced = send("replace").json()
    assert [k["code"] for k in replaced["keywords"]] == ["B1", "B1.01", "S9.01"]
    assert send("preview", "Stichwort;Bezeichnung\nB1;\n").status_code == 422


def test_role_grants_follow_the_rules(world):
    grant_ = lambda role, slug, scope="tenant", email="neu@example.org": world.post(  # noqa: E731
        "/api/admin/memberships", json={"email": email, "scope": scope, "slug": slug, "role": role})
    _as(world, "lead@example.org")
    assert grant_("editor", "wehr-a1").status_code == 200
    assert grant_("lead", "wehr-a1").status_code == 403            # Wehrführer vergibt keine Wehrführer
    assert grant_("viewer", "wehr-a2").status_code == 403          # fremde Wehr
    assert grant_("vg_stats", "vg-a", "vg").status_code == 403
    assert grant_("editor", "wehr-a1", email="kaputt").status_code == 422
    listed = world.get("/api/admin/memberships").json()["memberships"]
    assert {(m["email"], m["editable"]) for m in listed} >= {("lead@example.org", False), ("neu@example.org", True)}
    assert world.delete("/api/admin/memberships", params={"email": "lead@example.org", "scope": "tenant",
                                                           "slug": "wehr-a1"}).status_code == 403

    _as(world, "vglead@example.org")
    assert grant_("lead", "wehr-a2").status_code == 200
    assert grant_("vg_stats", "vg-a", "vg", "bm@example.org").status_code == 200
    assert grant_("lead", "wehr-b1").status_code == 403
    assert grant_("vg_lead", "vg-b", "vg").status_code == 403
    assert grant_("lead", "vg-a", "vg").status_code == 422         # Rolle passt nicht zum Bereich
    # Der letzte Wehrleiter kann sich nicht selbst entfernen
    response = world.delete("/api/admin/memberships", params={"email": "vglead@example.org", "scope": "vg",
                                                              "slug": "vg-a"})
    assert response.status_code == 403 and "Superadmin" in response.json()["detail"]
    assert world.delete("/api/admin/memberships", params={"email": "neu@example.org", "scope": "tenant",
                                                           "slug": "wehr-a1"}).status_code == 200
    assert tenancy.is_allowed("bm@example.org")
    assert world.delete("/api/admin/memberships", params={"email": "neu@example.org", "scope": "tenant",
                                                           "slug": "wehr-a2"}).status_code == 200
    with tenancy.central() as con:                                   # ohne Zuordnung kein Konto mehr
        assert not con.execute("SELECT 1 FROM account WHERE email = 'neu@example.org'").fetchone()
    assert not tenancy.is_allowed("neu@example.org")


def test_superadmin_manages_vgs_and_tenants(world, data_dir):
    _as(world, "lead@example.org")
    assert world.get("/api/super/overview").status_code == 403
    assert world.post("/api/super/vgs", json={"slug": "vg-c", "name": "VG C"}).status_code == 403
    _as(world, "admin@example.org")
    assert world.post("/api/super/vgs", json={"slug": "vg-c", "name": "VG C"}).status_code == 200
    assert world.post("/api/super/vgs", json={"slug": "vg-c", "name": "VG C"}).status_code == 422
    created = world.post("/api/super/tenants", json={"slug": "wehr-c1", "name": "Wehr C1", "vg": "vg-c",
                                                     "email": "c1@example.org"})
    assert created.status_code == 200 and tenancy.is_allowed("c1@example.org")
    assert world.post("/api/super/tenants", json={"slug": "wehr-c1", "name": "x", "vg": "vg-c"}).status_code == 422
    assert world.put("/api/super/tenants/wehr-c1", json={"active": False}).status_code == 200
    assert not tenancy.is_allowed("c1@example.org")
    assert world.delete("/api/super/tenants/wehr-c1", params={"confirm": "falsch"}).status_code == 422
    overview = world.delete("/api/super/tenants/wehr-c1", params={"confirm": "wehr-c1"}).json()
    assert "wehr-c1" not in [t["slug"] for t in overview["tenants"]]
    assert not os.path.exists(tenancy.tenant_path("wehr-c1"))
    assert len(os.listdir(data_dir / "deleted")) == 1
