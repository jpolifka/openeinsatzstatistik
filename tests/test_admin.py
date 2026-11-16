# -*- coding: utf-8 -*-
"""Verwaltung: Einstellungen, Logos, Stichworte, Rollenvergabe und Superadmin-Funktionen."""
import os

import pytest

from app import db, legacy, tenancy
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
    for key in ("slug", "palette", "unused_data", "known_vehicles", "call_sign_directory", "fee_types"):
        s.pop(key)
    for v in s["fleet"]:
        v.pop("incidents")
        v.pop("description")
        v.pop("suggested_name")
        v.pop("types")
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
    ({"fleet": [{"name": "kaputt!"}]}, "wie im BKS-Bericht"),
    ({"fleet": [{"name": ""}]}, "braucht einen Funkrufnamen"),
    ({"fleet": [{"name": "RP WW 01/23-06"}, {"name": "RP WW 01/23-06"}]}, "doppelt"),
    ({"fleet": [{"call_sign": "02/45"}, {"name": "FL NR#.MUS 02/45-01"}]}, "schon in der Liste"),
    ({"fleet": [{"call_sign": "02/45"}, {"call_sign": "02/45"}]}, "doppelt"),
    ({"fleet": [{"call_sign": "02/45", "in_service_from": "2025-01-01", "in_service_until": "2024-01-01"}]}, "außer Dienst"),
    ({"substitutes": {"01/23": "09/99"}}, "Block"),
    ({"substitutes": {"01/23": ["02/45"]}}, "Fahrzeug der Liste"),
    ({"fleet": [{"call_sign": "<img src=x onerror=alert(1)>"}]}, "Kurzname"),
    ({"places": [{"name": "<img src=x onerror=alert(1)>"}]}, "Ortsnamen"),
    ({"plan_places": ["Nirgendwo"]}, "Ortsliste"),
    ({"response_limits": [8, 10], "default_limit": 12}, "Standardgrenze"),
    ({"second_limit": 9}, "zweite Zeitgrenze"),
    ({"day_hours": [18, 6]}, "Beginn vor Ende"),
    ({"unit_marker": "NR#.MUS 02"}, "Kopfzeile"),
    ({"name": "   "}, "Namen der Wehr"),
])
def test_invalid_settings_are_rejected(world, change, message):
    _as(world, "lead@example.org")
    response = world.put("/api/admin/wehr-a1/settings", json={**_settings(world), **change})
    assert response.status_code == 422 and message in response.json()["detail"]


def test_theme_check_and_parse_test(world):
    _as(world, "lead@example.org")
    check = world.post("/api/admin/theme-check", json={"colors": {"brand": "#FFD700"}}).json()
    assert check["problems"] and check["palette"]["--brand"] == "#FFD700"
    line = "FL NR#.MUS 02/45-01 0 / 1 / 1 / 2 / 0 12.03.25 10:09:41 - - Ja - 12.03.25 10:48:21"
    found = world.post("/api/admin/parse-test", json={"line": line, "unit_marker": "FW NR#.MUS 02"}).json()
    assert [(v["name"], v["call_sign"], v["own"]) for v in found["vehicles"]] == [("FL NR#.MUS 02/45-01", "02/45", True)]
    # nur Funkrufnamen oder ganzer Berichtstext: Fahrzeuge der VG, fremde und die berichtende Einheit
    text = "FW NR#.MUS 02 Musterstadt Alarmierung: …\nFL NR#.MUS 01/46-01\nRP WW 01/23-06\nFL NR#.MUS 01/46-01"
    found = world.post("/api/admin/parse-test", json={"line": text, "unit_marker": "FW NR#.MUS 02"}).json()
    assert [(v["name"], v["call_sign"], v["own"]) for v in found["vehicles"]] == \
        [("FL NR#.MUS 01/46-01", "01/46", False), ("RP WW 01/23-06", None, False)]
    assert found["units"] == [{"unit": "FW NR#.MUS 02", "own": True}]


def test_unit_marker_sets_prefixes(world):
    _as(world, "lead@example.org")
    saved = world.put("/api/admin/wehr-a1/settings", json={**_settings(world), "unit_marker": " FW NR#.XYZ 05 ",
                                                           "unit_prefix": "egal", "own_prefix": "egal"})
    assert saved.status_code == 200, saved.text
    assert (saved.json()["unit_marker"], saved.json()["unit_prefix"], saved.json()["own_prefix"]) == \
        ("FW NR#.XYZ 05", "FL NR#.XYZ ", "05/")


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
    # Stichwort der VG löschen heißt: gilt in dieser Wehr nicht; nochmals löschen hebt das auf
    off = {k["code"]: k for k in world.delete("/api/admin/wehr-a1/keywords/B1.02").json()["keywords"]}["B1.02"]
    assert off["active"] is False and off["source"] == "changed"
    on = {k["code"]: k for k in world.delete("/api/admin/wehr-a1/keywords/B1.02").json()["keywords"]}["B1.02"]
    assert on["active"] and on["source"] == "vg"
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
    assert [k["code"] for k in replaced["keywords"] if k["active"]] == ["B1", "B1.01", "S9.01"]
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
                                                           "slug": "wehr-a1", "role": "lead"}).status_code == 403

    _as(world, "vglead@example.org")
    assert grant_("lead", "wehr-a2").status_code == 200
    assert grant_("vg_stats", "vg-a", "vg", "bm@example.org").status_code == 200
    assert grant_("lead", "wehr-b1").status_code == 403
    assert grant_("vg_lead", "vg-b", "vg").status_code == 403
    assert grant_("lead", "vg-a", "vg").status_code == 422         # Rolle passt nicht zum Bereich
    # Eigene Zuordnungen ändert jemand anderes
    response = world.delete("/api/admin/memberships", params={"email": "vglead@example.org", "scope": "vg",
                                                              "slug": "vg-a", "role": "vg_lead"})
    assert response.status_code == 403 and "Superadmin" in response.json()["detail"]
    assert world.delete("/api/admin/memberships", params={"email": "neu@example.org", "scope": "tenant",
                                                           "slug": "wehr-a1", "role": "editor"}).status_code == 200
    assert tenancy.is_allowed("bm@example.org")
    assert world.delete("/api/admin/memberships", params={"email": "neu@example.org", "scope": "tenant",
                                                           "slug": "wehr-a2", "role": "lead"}).status_code == 200
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
    with tenancy.central() as con:
        c1_id = con.execute("SELECT id FROM tenant WHERE slug = 'wehr-c1'").fetchone()[0]
    assert world.put("/api/super/tenants/wehr-c1", json={"active": False}).status_code == 200
    assert not tenancy.is_allowed("c1@example.org")
    assert world.delete("/api/super/tenants/wehr-c1", params={"confirm": "falsch"}).status_code == 422
    overview = world.delete("/api/super/tenants/wehr-c1", params={"confirm": "wehr-c1"}).json()
    assert "wehr-c1" not in [t["slug"] for t in overview["tenants"]]
    assert not os.path.exists(tenancy.tenant_path("wehr-c1"))
    assert len(os.listdir(data_dir / "deleted")) == 1
    # Neue Wehr bekommt nicht die ID der gelöschten – sonst sähe ihre Wehrführung deren Rollen-Protokoll
    world.post("/api/super/tenants", json={"slug": "wehr-c2", "name": "Wehr C2", "vg": "vg-c",
                                           "email": "c2@example.org"})
    with tenancy.central() as con:
        assert con.execute("SELECT id FROM tenant WHERE slug = 'wehr-c2'").fetchone()[0] > c1_id
    events = _as(world, "c2@example.org").get("/api/admin/role-events").json()["events"]
    assert not any("c1@example.org" in e["detail"] for e in events)


def test_fleet_with_full_call_signs(world):
    """Neue Fahrzeuge bekommen den Kurznamen aus dem Funkrufnamen; bestehende behalten ihren."""
    with tenancy.central() as con:                              # Gebührenordnung für die Vorbelegung des Typs
        legacy.seed_fee_schedule(con, con.execute("SELECT id FROM vg WHERE slug = 'vg-a'").fetchone()[0])
    _as(world, "lead@example.org")
    s = _settings(world)
    s["fleet"] = [{"call_sign": "02/45", "name": "FL NR#.MUS 02/45-01", "label": "HLF 20"}, {"call_sign": "02/24"},
                  {"name": "FL NR#.MUS 01/23-01"}, {"name": "RP WW 01/23-06", "label": "TLF 3000"},
                  {"name": "RP WW 01/23-07", "replaced_by": "RP WW 01/23-06"}]
    s["substitutes"] = {"FL NR#.MUS 01/46-01": "RP WW 01/23-06"}
    saved = world.put("/api/admin/wehr-a1/settings", json=s)
    assert saved.status_code == 200, saved.text
    fleet = saved.json()["fleet"]
    assert [(v["call_sign"], v["name"]) for v in fleet] == [
        ("02/45", "FL NR#.MUS 02/45-01"), ("02/24", ""), ("01/23", "FL NR#.MUS 01/23-01"),
        ("01/23-06", "RP WW 01/23-06"), ("01/23-07", "RP WW 01/23-07")]
    assert fleet[1]["suggested_name"] == "FL NR#.MUS 02/24-01"
    assert fleet[4]["replaced_by"] == "01/23-06"
    assert saved.json()["substitutes"] == {"FL NR#.MUS 01/46-01": "01/23-06"}
    known = {v["name"]: v for v in saved.json()["known_vehicles"]}
    assert known["RP WW 01/23-06"]["description"].startswith("Rheinpfalz (Land) · WW · Standort 01 · 23 Tanklösch")
    assert fleet[0]["description"].endswith("Nr. 1")
    assert "FL NR#.MUS 02/24-01" in known                     # Vorschlag zum alten Kurznamen 02/24
    assert known["RP WW 01/23-06"]["types"] == ["TLF 3000", "TLF 16/24Tr", "TLF 16/25"]
    assert known["RP WW 01/23-06"]["label"] == "TLF 16/25"    # der einzige Typ, der in der Gebührenordnung steht
    assert fleet[0]["types"] == ["LF 10", "HLF 10", "LF 16/12", "LF 16"]
    assert "HLF 20" in saved.json()["fee_types"]
    config = world.get("/api/config").json()
    assert config["vehicle_names"]["01/23-06"] == "RP WW 01/23-06"


def _fleet_payload(data, **changes):
    """Antwort von /fleet als Eingabe; changes: slug -> Funktion, die die Fahrzeugliste ändert."""
    return {"tenants": [{"slug": t["slug"], "fleet_version": t["fleet_version"], "substitutes": t["substitutes"],
                         "fleet": changes.get(t["slug"].replace("-", "_"), lambda f: f)(t["fleet"])}
                        for t in data["tenants"]]}


def test_vg_fleet_overview_and_move(world):
    """Wehrleitung: alle Fahrzeuge der VG in einer Tabelle; Fahrzeug wechselt die Wehr, Einsätze bleiben."""
    from conftest import CFG
    with db.connection(tenancy.tenant_path("wehr-a1")) as con:
        incident_id = con.execute("INSERT INTO incident (year, number, source) VALUES (2025, 1, 'pdf')").lastrowid
        con.execute("INSERT INTO vehicle (incident_id, call_sign, name) VALUES (?, '01/10', 'FL NR#.MUS 01/10-01')",
                    (incident_id,))
        con.execute("INSERT INTO vehicle (incident_id, call_sign, name) VALUES (?, '-', 'RP WW 01/23-06')", (incident_id,))
    assert _as(world, "lead@example.org").get("/api/admin/vgs/vg-a/fleet").status_code == 403
    assert _as(world, "other@example.org").get("/api/admin/vgs/vg-a/fleet").status_code == 403
    _as(world, "vglead@example.org")
    data = world.get("/api/admin/vgs/vg-a/fleet").json()
    assert [t["slug"] for t in data["tenants"]] == ["wehr-a1", "wehr-a2"]
    kdow = next(v for v in data["tenants"][0]["fleet"] if v["call_sign"] == "01/10")
    assert kdow["suggested_name"] == "FL NR#.MUS 01/10-01" and kdow["incidents"] == 1
    assert {"name": "RP WW 01/23-06", "vg": False} == {k: v for k, v in data["unassigned"][0].items() if k in ("name", "vg")}

    moved = world.put("/api/admin/vgs/vg-a/fleet", json=_fleet_payload(
        data, wehr_a1=lambda f: [v for v in f if v["call_sign"] != "01/10"] + [{"name": "RP WW 01/23-06"}],
        wehr_a2=lambda f: f + [{"name": "FL NR#.MUS 01/10-01"}]))
    assert moved.status_code == 200, moved.text
    a1, a2 = (t["fleet"] for t in moved.json()["tenants"])
    # wehr-a2 führt 01/10 schon mit Kurznamen: der Eintrag bekommt den Funkrufnamen, kein zweiter Block
    assert [v["call_sign"] for v in a2] == list(CFG.vehicles)
    assert next(v["name"] for v in a2 if v["call_sign"] == "01/10") == "FL NR#.MUS 01/10-01"
    assert "01/10" not in [v["call_sign"] for v in a1] and ("01/23-06", "RP WW 01/23-06") in [
        (v["call_sign"], v["name"]) for v in a1]
    with db.connection(tenancy.tenant_path("wehr-a1")) as con:      # Einsatzdaten bleiben bei der alten Wehr
        assert con.execute("SELECT COUNT(*) FROM vehicle WHERE call_sign = '01/10'").fetchone()[0] == 1

    data = moved.json()
    twice = world.put("/api/admin/vgs/vg-a/fleet", json=_fleet_payload(data, wehr_a2=lambda f: f + [{"name": "RP WW 01/23-06"}]))
    assert twice.status_code == 422 and "Wehr wehr-a1" in twice.json()["detail"]
    foreign = _fleet_payload(data)
    foreign["tenants"][0]["slug"] = "wehr-b1"
    assert world.put("/api/admin/vgs/vg-a/fleet", json=foreign).status_code == 404
    with db.connection(tenancy.tenant_path("wehr-a2")) as con:      # inzwischen per Import geändert
        con.execute("INSERT INTO fleet (call_sign, name, label, sort_order) VALUES ('02/99', 'FL NR#.MUS 02/99-01', '', 99)")
    tenancy.forget_config("wehr-a2")
    assert world.put("/api/admin/vgs/vg-a/fleet", json=_fleet_payload(data)).status_code == 409


def test_vg_settings_and_tenant_overrides(world):
    """Vorgaben der VG gelten in allen Wehren; abweichende Werte der Wehr bleiben und werden angezeigt."""
    assert _as(world, "lead@example.org").get("/api/admin/vgs/vg-a/settings").status_code == 403
    _as(world, "vglead@example.org")
    vg = world.get("/api/admin/vgs/vg-a/settings").json()
    vg["day_hours"], vg["bks_code"] = [7, 19], "NR#.ABC"
    vg["tenants"] = [{"slug": "wehr-a1", "station": "03", "plan_places": ["Altenau"]}]
    saved = world.put("/api/admin/vgs/vg-a/settings", json=vg)
    assert saved.status_code == 200, saved.text
    a1 = next(t for t in saved.json()["tenants"] if t["slug"] == "wehr-a1")
    # beide Wehren sind mit eigener Kennung NR#.MUS eingerichtet: Abweichung, nur der Standort ändert sich
    assert a1["unit_marker"] == "FW NR#.MUS 03" and a1["plan_places"] == ["Altenau"]
    a2 = next(t for t in saved.json()["tenants"] if t["slug"] == "wehr-a2")
    assert a2["unit_marker"] == "FW NR#.MUS 02" and a2["overrides"]["bks_code"] == "NR#.MUS"

    _as(world, "lead@example.org")
    s = _settings(world)
    assert s["day_hours"] == [7, 19] and "day_hours" not in s["overrides"] and s["inherited"]["day_hours"] == [7, 19]
    s["day_hours"] = [8, 20]
    assert world.put("/api/admin/wehr-a1/settings", json=s).status_code == 200
    assert "day_hours" in _settings(world)["overrides"]
    _as(world, "vglead@example.org")
    vg["day_hours"], vg["tenants"] = [8, 20], []                # VG zieht nach: Abweichung entfällt
    world.put("/api/admin/vgs/vg-a/settings", json=vg)
    assert "day_hours" not in _as(world, "lead@example.org").get("/api/admin/wehr-a1/settings").json()["overrides"]
    _as(world, "vglead@example.org")
    assert world.put("/api/admin/vgs/vg-a/settings", json={**vg, "bks_code": "",
                     "tenants": [{"slug": "wehr-a1", "station": "04"}]}).status_code == 422
    found = world.post("/api/admin/parse-test", json={"line": "FW NR#.MUS 03 FL NR#.MUS 02/45-01 RP WW 01/23-06",
                                                      "vg": "vg-a"}).json()
    assert found["units"] == [{"unit": "FW NR#.MUS 03", "tenant": "Wehr wehr-a1"}]
    assert [v["tenant"] for v in found["vehicles"]] == ["Wehr wehr-a2", None]


def test_settings_do_not_overwrite_newer_fleet(world):
    """Fahrzeug kommt beim Import dazu, während die Einstellungen offen sind: Speichern wird abgelehnt (409)."""
    _as(world, "lead@example.org")
    s = _settings(world)
    with db.connection(tenancy.tenant_path("wehr-a1")) as con:
        con.execute("INSERT INTO fleet (call_sign, name, label, sort_order) VALUES ('02/99', 'FL NR#.MUS 02/99-01', '', 99)")
    tenancy.forget_config("wehr-a1")
    response = world.put("/api/admin/wehr-a1/settings", json=s)
    assert response.status_code == 409 and "neu laden" in response.json()["detail"]
    fresh = _settings(world)
    assert "02/99" in [v["call_sign"] for v in fresh["fleet"]]
    assert world.put("/api/admin/wehr-a1/settings", json=fresh).status_code == 200
