# -*- coding: utf-8 -*-
"""Atemschutz-Dokumentation: Rechte, Zugang über die E-Mail im Personalstamm und – vor allem – kein Zugriff auf andere
Personen, andere Wehren oder die Einsatzdaten."""
import pathlib
import re
import sqlite3

import pytest

from app import atemschutz, db, rbac, store, tenancy
from conftest import grant, login, make_tenant

ENTRY = {"kind": "strecke", "started_at": "2025-03-12T19:00", "duration_min": 20, "place": "Übungsstrecke Musterstadt",
         "start_bar": 300, "end_bar": 120}


@pytest.fixture
def world(make_client):
    vg_a, a1 = make_tenant("wehr-a1", "vg-a")
    vg_b, b1 = make_tenant("wehr-b1", "vg-b")
    grant("lead@example.org", "lead", a1)
    grant("deputy@example.org", "deputy_lead", a1)
    grant("editor@example.org", "editor", a1)
    grant("vglead@example.org", "vg_lead", vg_a)
    with db.connection(tenancy.tenant_path("wehr-a1")) as con:
        incident = store.create_incident(con, {"number": 1, "started_at": "2025-03-12T10:00:00",
                                               "ended_at": "2025-03-12T11:30:00", "keyword": "B2", "place": "Altenau"},
                                         source="pdf")
        other = store.create_incident(con, {"number": 2, "started_at": "2025-04-01T10:00:00", "keyword": "H1",
                                            "place": "Altenau"}, source="pdf")
        directory = store.MemberDirectory(con)
        anna, berta = directory.find_or_create("Beispiel", "Anna"), directory.find_or_create("Muster", "Berta")
        store.add_attendance(con, incident, anna)
        store.add_attendance(con, other, berta)
    client = make_client(login=True)
    client.ids = {"vg-a": vg_a, "a1": a1, "b1": b1, "incident": incident, "other": other, "anna": anna, "berta": berta}
    # Die Wehrführung pflegt die E-Mail, daraus entsteht der Zugang
    _as(client, "lead@example.org")
    for member, email in ((anna, "anna@example.org"), (berta, "berta@example.org")):
        assert _set_email(client, member, email).status_code == 200
    return client


def _as(client, email, scope="t:wehr-a1"):
    client.cookies.clear()
    login(client, email)
    client.cookies.set("scope", scope)
    return client


def _set_email(client, member_id, email, active=True, slug="wehr-a1"):
    with db.connection(tenancy.tenant_path(slug)) as con:
        row = con.execute("SELECT last_name, first_name FROM member WHERE id = ?", (member_id,)).fetchone()
    return client.put(f"/api/admin/{slug}/members/{member_id}",
                      json={"last_name": row["last_name"], "first_name": row["first_name"], "email": email,
                            "active": active})


def _rows(slug, sql, *args):
    with db.connection(tenancy.tenant_path(slug)) as con:
        return con.execute(sql, args).fetchall()


# ---------------------------------------------------------------- Rechte
def test_only_lead_has_agt_rights_and_nothing_is_inherited(world):
    with tenancy.central() as con:
        roles = rbac.Roles(con)
    holders = {}
    for role in roles:
        found = roles.permissions(role.id) & rbac.FIXED_PERMISSIONS
        if found:
            holders[role.key] = found
    assert holders == {"lead": {rbac.AGT_OWN, rbac.AGT_EVAL}, "deputy_lead": {rbac.AGT_EVAL}, "vg_lead": {rbac.AGT_OWN}, "agt_self": {rbac.AGT_OWN}}
    assert not any(p.scopes != ("tenant",) for p in rbac.PERMISSIONS.values() if p.key == rbac.AGT_EVAL)


def test_agt_self_has_nothing_else(world):
    with tenancy.central() as con:
        roles = rbac.Roles(con)
    assert roles.permissions(roles.find("agt_self", None).id) == {rbac.AGT_OWN}


def test_custom_roles_cannot_carry_agt_rights(world):
    with tenancy.central() as con:
        roles = rbac.Roles(con)
        with pytest.raises(rbac.Invalid):
            rbac.save_role(con, roles, None, vg_id=world.ids["vg-a"], scope="tenant", label="Eigene", description="",
                           parent_id=None, permissions=[rbac.AGT_EVAL], granted_by=[], grants=[])


def test_editing_a_system_role_keeps_its_agt_rights(world):
    with tenancy.central() as con:
        roles = rbac.Roles(con)
        lead = roles.find("lead", None)
        rbac.save_role(con, roles, lead.id, vg_id=None, scope="tenant", label=lead.label, description="",
                       parent_id=lead.parent_id, permissions=[rbac.STATS], granted_by=[], grants=[])
        assert rbac.AGT_EVAL in rbac.Roles(con).permissions(lead.id)


def test_superadmin_has_no_agt_rights_and_roles_page_hides_them(world):
    a = tenancy.access_for("admin@example.org", "t:wehr-a1")
    assert not a.tenants["wehr-a1"].permissions & rbac.FIXED_PERMISSIONS
    _as(world, "admin@example.org")
    assert world.get("/api/atemschutz/summary").status_code == 403
    page = world.get("/api/admin/roles").json()
    assert not {p["key"] for p in page["permissions"]} & rbac.FIXED_PERMISSIONS
    assert not any(set(r["permissions"]) & rbac.FIXED_PERMISSIONS for r in page["roles"])


def test_editor_has_no_access(world):
    _as(world, "editor@example.org")
    assert world.get("/api/atemschutz/me").status_code == 403
    assert world.get("/api/atemschutz/summary").status_code == 403


def test_deputy_may_evaluate_but_has_no_own_documentation(world):
    _as(world, "deputy@example.org")
    assert world.get("/api/atemschutz/me").status_code == 403
    assert world.get("/api/atemschutz/summary").status_code == 200


# ---------------------------------------------------------------- Zugang über die E-Mail
def test_email_creates_and_removes_the_only_membership(world):
    with tenancy.central() as con:
        rows = con.execute("SELECT r.key FROM membership m JOIN role r ON r.id = m.role_id WHERE m.email = ?",
                           ("anna@example.org",)).fetchall()
    assert [r["key"] for r in rows] == ["agt_self"]
    assert tenancy.is_allowed("anna@example.org")
    assert _set_email(world, world.ids["anna"], None).status_code == 200
    assert not tenancy.is_allowed("anna@example.org")
    assert _set_email(world, world.ids["anna"], "anna@example.org").status_code == 200
    assert _set_email(world, world.ids["anna"], "anna@example.org", active=False).status_code == 200      # ausgeschieden
    assert not tenancy.is_allowed("anna@example.org")


def test_changing_email_does_not_touch_other_roles(world):
    grant("anna@example.org", "editor", world.ids["a1"])
    assert _set_email(world, world.ids["anna"], "anna2@example.org").status_code == 200
    with tenancy.central() as con:
        keys = [r["key"] for r in con.execute("SELECT r.key FROM membership m JOIN role r ON r.id = m.role_id "
                                              "WHERE m.email = 'anna@example.org'")]
    assert keys == ["editor"]
    assert tenancy.is_allowed("anna2@example.org")


def test_email_must_be_valid_and_unique(world):
    assert _set_email(world, world.ids["anna"], "kaputt").status_code == 422
    assert _set_email(world, world.ids["anna"], "BERTA@example.org").status_code == 409
    update = world.put("/api/admin/wehr-a1/members/%d" % world.ids["anna"], json={"last_name": "Beispiel",
                                                                                   "first_name": "Anna"})
    assert update.status_code == 200
    assert next(m for m in update.json()["members"] if m["id"] == world.ids["anna"])["email"] == "anna@example.org"


def test_only_lead_can_set_email(world):
    _as(world, "editor@example.org")
    assert _set_email(world, world.ids["anna"], "x@example.org").status_code == 403


def test_member_without_email_has_no_own_view(world):
    _as(world, "lead@example.org")                      # Wehrführer ohne eigenen Eintrag im Personalstamm
    assert world.get("/api/atemschutz/me").json() == {"linked": False}
    assert world.post("/api/atemschutz/me/entries", json=ENTRY).status_code == 404


def test_merge_and_transfer_refuse_people_with_email_or_data(world):
    _as(world, "lead@example.org")
    assert world.post(f"/api/admin/wehr-a1/members/{world.ids['anna']}/merge",
                      json={"into": world.ids["berta"]}).status_code == 409
    _set_email(world, world.ids["anna"], None)
    _as(world, "anna@example.org")
    assert world.get("/api/atemschutz/me").status_code == 401        # Zugang entzogen, Sitzung gilt nicht mehr


def test_deleting_member_removes_access_and_data(world):
    _as(world, "berta@example.org")
    assert world.post("/api/atemschutz/me/entries", json=ENTRY).status_code == 200
    _as(world, "lead@example.org")
    # Berta hat Einsätze: nicht löschbar; Anna hat Einsätze: ebenso. Neue Person ohne Einsätze:
    created = world.post("/api/admin/wehr-a1/members", json={"last_name": "Neu", "first_name": "Nora",
                                                             "email": "nora@example.org"})
    assert created.status_code == 200
    nora = next(m["id"] for m in created.json()["members"] if m["last_name"] == "Neu")
    assert tenancy.is_allowed("nora@example.org")
    assert world.delete(f"/api/admin/wehr-a1/members/{nora}").status_code == 200
    assert not tenancy.is_allowed("nora@example.org")


# ---------------------------------------------------------------- eigene Einträge
def test_create_update_delete_own_entry(world):
    _as(world, "anna@example.org")
    created = world.post("/api/atemschutz/me/entries", json=ENTRY)
    assert created.status_code == 200, created.text
    entry = created.json()
    assert entry["ended_at"] == "2025-03-12T19:20:00" and entry["used_bar"] == 180 and "member_id" not in entry
    state = world.get("/api/atemschutz/me?year=2025").json()
    assert state["name"] == "Beispiel, Anna" and [e["id"] for e in state["entries"]] == [entry["id"]]
    assert state["totals"]["strecke"] == {"count": 1, "minutes": 20}
    assert world.put(f"/api/atemschutz/me/entries/{entry['id']}", json={**ENTRY, "duration_min": 25}).status_code == 428
    updated = world.put(f"/api/atemschutz/me/entries/{entry['id']}", json={**ENTRY, "duration_min": 25, "revision": 0})
    assert updated.status_code == 200 and updated.json()["revision"] == 1
    assert world.put(f"/api/atemschutz/me/entries/{entry['id']}",
                     json={**ENTRY, "revision": 0}).status_code == 409          # veraltet
    assert world.delete(f"/api/atemschutz/me/entries/{entry['id']}").status_code == 428
    assert world.delete(f"/api/atemschutz/me/entries/{entry['id']}?revision=0").status_code == 409
    assert world.delete(f"/api/atemschutz/me/entries/{entry['id']}?revision=1").status_code == 200
    assert world.get("/api/atemschutz/me?year=2025").json()["entries"] == []


@pytest.mark.parametrize("change", [
    {"kind": "xx"}, {"started_at": "kaputt"}, {"duration_min": 0}, {"duration_min": 1441}, {"duration_min": "20"},
    {"start_bar": 401}, {"end_bar": -1}, {"end_bar": 200, "start_bar": 100}, {"end_bar": None},
    {"external": True},                       # Fremdeintrag braucht die Organisation
    {"place": "x" * 121}])
def test_entry_validation(world, change):
    _as(world, "anna@example.org")
    assert world.post("/api/atemschutz/me/entries", json={**ENTRY, **change}).status_code == 422


def test_external_entry_for_works_fire_brigade(world):
    _as(world, "anna@example.org")
    body = {**ENTRY, "kind": "einsatz", "external": True, "organisation": "Werkfeuerwehr Muster AG", "keyword": "B3"}
    entry = world.post("/api/atemschutz/me/entries", json=body).json()
    assert entry["external"] is True and entry["organisation"] == "Werkfeuerwehr Muster AG"
    own = {**ENTRY, "organisation": "ignoriert"}
    assert world.post("/api/atemschutz/me/entries", json=own).json()["organisation"] is None


def test_unknown_fields_and_member_id_are_rejected(world):
    _as(world, "anna@example.org")
    for extra in ({"member_id": world.ids["berta"]}, {"email": "berta@example.org"}):
        assert world.post("/api/atemschutz/me/entries", json={**ENTRY, **extra}).status_code == 422
    assert world.put("/api/atemschutz/me/medical", json={}).status_code == 405


def test_member_id_in_query_is_ignored(world):
    _as(world, "berta@example.org")
    world.post("/api/atemschutz/me/entries", json=ENTRY)
    _as(world, "anna@example.org")
    state = world.get(f"/api/atemschutz/me?year=2025&member_id={world.ids['berta']}&email=berta@example.org").json()
    assert state["name"] == "Beispiel, Anna" and state["entries"] == []


# ---------------------------------------------------------------- Übernahme aus der Statistik
def test_take_over_incident_where_person_took_part(world):
    _as(world, "anna@example.org")
    candidates = world.get("/api/atemschutz/me/candidates?year=2025").json()["candidates"]
    assert [(c["source"], c["id"], c["keyword"]) for c in candidates] == [("incident", world.ids["incident"], "B2")]
    body = {"source": {"kind": "incident", "id": world.ids["incident"]}, "start_bar": 280, "end_bar": 90,
            "keyword": "manipuliert", "place": "manipuliert", "started_at": "2020-01-01T00:00", "kind": "uebung"}
    entry = world.post("/api/atemschutz/me/entries", json=body)
    assert entry.status_code == 200, entry.text
    entry = entry.json()
    # Stichwort, Beginn und Ort kommen aus der Statistik, nicht vom Client
    assert (entry["kind"], entry["keyword"], entry["place"], entry["started_at"], entry["duration_min"]) == \
           ("einsatz", "B2", "Altenau", "2025-03-12T10:00:00", 90)
    assert entry["source_kind"] == "incident" and entry["start_bar"] == 280
    assert world.post("/api/atemschutz/me/entries", json=body).status_code == 422          # nicht doppelt
    again = world.get("/api/atemschutz/me/candidates?year=2025").json()["candidates"]
    assert again[0]["taken"] is True
    shorter = world.put(f"/api/atemschutz/me/entries/{entry['id']}",
                        json={**ENTRY, "kind": "strecke", "started_at": "1999-01-01T00:00", "duration_min": 45,
                              "revision": 0})
    assert shorter.json()["kind"] == "einsatz" and shorter.json()["started_at"] == "2025-03-12T10:00:00"
    assert shorter.json()["duration_min"] == 45


def test_cannot_take_over_incident_of_someone_else(world):
    _as(world, "anna@example.org")
    body = {"source": {"kind": "incident", "id": world.ids["other"]}, "duration_min": 10}
    assert world.post("/api/atemschutz/me/entries", json=body).status_code == 404
    body["source"] = {"kind": "incident", "id": 99999}
    assert world.post("/api/atemschutz/me/entries", json=body).status_code == 404
    body["source"] = {"kind": "x", "id": 1}
    assert world.post("/api/atemschutz/me/entries", json=body).status_code == 404


def test_take_over_training(world):
    _as(world, "lead@example.org")
    created = world.post("/api/trainings", json={"topic": "Atemschutzübung", "started_at": "2025-05-05T19:00",
                                                 "ended_at": "2025-05-05T21:00", "member_ids": [world.ids["anna"]],
                                                 "new_members": []})
    assert created.status_code == 200
    _as(world, "anna@example.org")
    candidate = next(c for c in world.get("/api/atemschutz/me/candidates?year=2025").json()["candidates"]
                     if c["source"] == "training")
    entry = world.post("/api/atemschutz/me/entries", json={"source": {"kind": "training", "id": candidate["id"]}}).json()
    assert (entry["kind"], entry["keyword"], entry["duration_min"]) == ("uebung", "Atemschutzübung", 120)
    _as(world, "berta@example.org")
    assert world.get("/api/atemschutz/me/candidates?year=2025").json()["candidates"][0]["source"] == "incident"


# ---------------------------------------------------------------- keine Zugriffe auf andere Personen
def test_foreign_entry_ids_are_not_found_and_stay_untouched(world):
    _as(world, "berta@example.org")
    foreign = world.post("/api/atemschutz/me/entries", json=ENTRY).json()
    _as(world, "anna@example.org")
    url = f"/api/atemschutz/me/entries/{foreign['id']}"
    assert world.put(url, json={**ENTRY, "duration_min": 99, "revision": 0}).status_code == 404
    assert world.delete(url + "?revision=0").status_code == 404
    assert world.get("/api/atemschutz/me?year=2025").json()["entries"] == []
    row = _rows("wehr-a1", "SELECT duration_min, revision FROM agt_entry WHERE id = ?", foreign["id"])[0]
    assert tuple(row) == (20, 0)


def test_foreign_medical_and_reminder_stay_untouched(world, monkeypatch):
    monkeypatch.setattr("app.mail.SMTP_HOST", "smtp.example.org")
    _as(world, "berta@example.org")
    medical = world.post("/api/atemschutz/me/medical", json={"examined_on": "2025-02-01", "valid_until": "2028-02-01"})
    assert medical.status_code == 200
    medical_id = medical.json()["medical"][0]["id"]
    assert world.put("/api/atemschutz/me/reminder", json={"offsets": [30]}).json() == {"reminder": [30]}
    _as(world, "anna@example.org")
    assert world.delete(f"/api/atemschutz/me/medical/{medical_id}").status_code == 404
    state = world.get("/api/atemschutz/me").json()
    assert state["medical"] == [] and state["reminder"] == []
    assert _rows("wehr-a1", "SELECT COUNT(*) FROM agt_medical")[0][0] == 1
    assert world.put("/api/atemschutz/me/reminder", json={"offsets": []}).status_code == 200
    assert _rows("wehr-a1", "SELECT COUNT(*) FROM agt_reminder")[0][0] == 1       # Annas Löschwunsch betrifft Berta nicht


def test_other_wehr_and_vg_view_never_reach_data(world):
    _as(world, "berta@example.org")
    world.post("/api/atemschutz/me/entries", json=ENTRY)
    # Wehrleiter der VG: eigene Einträge nur dort, wo seine E-Mail im Stamm steht – nie die von Berta
    _as(world, "vglead@example.org")
    assert world.get("/api/atemschutz/me").json() == {"linked": False}
    _as(world, "vglead@example.org", scope="vg:vg-a")                     # Gesamtansicht: keine einzelne Wehr
    assert world.get("/api/atemschutz/me").status_code == 403
    assert world.get("/api/atemschutz/summary").status_code == 403
    # Wehr einer anderen VG gewählt: ohne Zuordnung dort wird die Auswahl ignoriert, nichts aus Wehr B1
    _as(world, "berta@example.org", scope="t:wehr-b1")
    assert world.get("/api/config").json()["tenant"]["slug"] == "wehr-a1"


def test_same_email_in_two_wehren_is_separated(world):
    make_tenant("wehr-a2", "vg-a")
    grant("lead@example.org", "lead", tenancy_id(world, "wehr-a2"))
    with db.connection(tenancy.tenant_path("wehr-a2")) as con:
        member = store.MemberDirectory(con).find_or_create("Beispiel", "Anna")
    _as(world, "lead@example.org", scope="t:wehr-a2")
    assert _set_email(world, member, "anna@example.org", slug="wehr-a2").status_code == 200
    _as(world, "anna@example.org", scope="t:wehr-a1")
    world.post("/api/atemschutz/me/entries", json=ENTRY)
    _as(world, "anna@example.org", scope="t:wehr-a2")
    assert world.get("/api/atemschutz/me?year=2025").json()["entries"] == []
    assert _rows("wehr-a2", "SELECT COUNT(*) FROM agt_entry")[0][0] == 0


def tenancy_id(world, slug):
    with tenancy.central() as con:
        return con.execute("SELECT id FROM tenant WHERE slug = ?", (slug,)).fetchone()["id"]


# ---------------------------------------------------------------- nur eigene Ansicht, keine Wehrdaten
def test_agt_self_cannot_read_anything_else(world):
    _as(world, "anna@example.org")
    for path in ("/api/evaluation", "/api/incidents", "/api/members?tenant=wehr-a1", "/api/trainings", "/api/export", "/api/years",
                 "/api/records", "/api/admin/wehr-a1/members", "/api/admin/wehr-a1/settings", "/api/atemschutz/summary"):
        assert world.get(path).status_code in (403, 404), path
    config = world.get("/api/config").json()
    assert config["permissions"] == [rbac.AGT_OWN] and config["tenant"]["slug"] == "wehr-a1"
    assert world.get("/api/theme.css").status_code == 200


# ---------------------------------------------------------------- Auswertung der Wehrführung
def test_summary_has_only_totals(world):
    _as(world, "anna@example.org")
    world.post("/api/atemschutz/me/entries", json={**ENTRY, "notes": "geheim", "place": "Geheimort"})
    world.post("/api/atemschutz/me/medical", json={"examined_on": "2025-02-01", "valid_until": "2026-02-01"})
    _as(world, "lead@example.org")
    response = world.get("/api/atemschutz/summary?year=2025")
    assert response.status_code == 200
    anna = next(p for p in response.json()["people"] if p["id"] == world.ids["anna"])
    assert anna["kinds"]["strecke"] == {"count": 1, "minutes": 20} and anna["minutes"] == 20
    assert anna["valid_until"] == "2026-02-01" and anna["linked"] is True
    assert "geheim" not in response.text.lower() and "geheimort" not in response.text.lower()
    assert "start_bar" not in response.text and "@" not in response.text           # auch keine E-Mail-Adressen
    audit = _rows("wehr-a1", "SELECT email, action FROM agt_audit WHERE action = 'agt.summary.view'")
    assert [tuple(r) for r in audit] == [("lead@example.org", "agt.summary.view")]


def test_lead_sees_all_entries_of_a_person_without_notes(world):
    _as(world, "anna@example.org")
    world.post("/api/atemschutz/me/entries", json={**ENTRY, "notes": "geheim", "place": "Übungsort"})
    world.post("/api/atemschutz/me/medical", json={"examined_on": "2025-02-01", "valid_until": "2026-02-01"})
    anna = world.ids["anna"]
    _as(world, "lead@example.org")
    r = world.get(f"/api/atemschutz/people/{anna}?year=2025")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] and len(body["entries"]) == 1 and body["entries"][0]["place"] == "Übungsort"
    assert body["medical"] == [{"examined_on": "2025-02-01", "valid_until": "2026-02-01"}]
    assert "geheim" not in r.text and "@" not in r.text
    audit = _rows("wehr-a1", "SELECT email, action, member_id FROM agt_audit WHERE action = 'agt.person.view'")
    assert [tuple(x) for x in audit] == [("lead@example.org", "agt.person.view", anna)]
    assert world.get("/api/atemschutz/people/99999").status_code == 404
    for email in ("editor@example.org", "anna@example.org"):
        _as(world, email)
        assert world.get(f"/api/atemschutz/people/{anna}").status_code == 403


def test_audit_log_is_append_only_and_free_of_values(world):
    _as(world, "anna@example.org")
    world.post("/api/atemschutz/me/entries", json=ENTRY)
    rows = _rows("wehr-a1", "SELECT * FROM agt_audit")
    assert rows and all("Übungsstrecke" not in str(tuple(r)) for r in rows)
    with db.connection(tenancy.tenant_path("wehr-a1")) as con:
        with pytest.raises(sqlite3.DatabaseError, match="nur anhängbar"):
            con.execute("DELETE FROM agt_audit")
        with pytest.raises(sqlite3.DatabaseError, match="nur anhängbar"):
            con.execute("UPDATE agt_audit SET email = 'x'")


# ---------------------------------------------------------------- G26.3 und Erinnerung
def test_medical_validation_and_current(world):
    _as(world, "anna@example.org")
    post = lambda **b: world.post("/api/atemschutz/me/medical", json=b)       # noqa: E731
    assert post(examined_on="2025-02-30", valid_until="2026-02-01").status_code == 422
    assert post(examined_on="2025-02-01", valid_until="2025-01-01").status_code == 422
    assert post(examined_on="2025-02-01", valid_until="2031-02-01").status_code == 422
    assert post(examined_on="01.02.2025", valid_until="2026-02-01").status_code == 422
    post(examined_on="2023-02-01", valid_until="2024-02-01")
    medical = post(examined_on="2025-02-01", valid_until="2026-02-01").json()["medical"]
    assert [m["valid_until"] for m in medical] == ["2026-02-01", "2024-02-01"]


def test_reminder_needs_mail_and_valid_offsets(world, monkeypatch):
    _as(world, "anna@example.org")
    assert world.put("/api/atemschutz/me/reminder", json={"offsets": [30]}).status_code == 422      # kein SMTP
    monkeypatch.setattr("app.mail.SMTP_HOST", "smtp.example.org")
    assert world.put("/api/atemschutz/me/reminder", json={"offsets": [7]}).status_code == 422
    assert world.put("/api/atemschutz/me/reminder", json={"offsets": [14, 60, 30]}).json() == {"reminder": [60, 30, 14]}
    assert world.put("/api/atemschutz/me/reminder", json={"offsets": []}).json() == {"reminder": []}


# ---------------------------------------------------------------- Quelltextwächter
def test_every_sql_on_agt_tables_is_bound_to_a_member():
    """Jede SQL-Anweisung auf agt_* in app/ enthält `member_id = ?` – außer in den Auswertungsfunktionen der Allowlist."""
    root = pathlib.Path(__file__).resolve().parent.parent / "app"
    source = (root / "atemschutz.py").read_text(encoding="utf-8")
    body = source.split("# ---------------------------------------------------------------- Auswertung der Wehrführung")[0]
    statements = re.findall(r'"((?:SELECT|INSERT|UPDATE|DELETE)[^"]*agt_[^"]*)"(?:\s*\n\s*"[^"]*")*', body)
    assert statements
    for statement in re.findall(r'con\.execute\(\s*((?:f?"[^"]*"\s*)+)', body):
        text = "".join(re.findall(r'"([^"]*)"', statement))
        if "agt_" in text and "agt_audit" not in text:
            assert "member_id" in text, text
    # Außerhalb des Moduls darf kein anderer Code agt_entry/agt_medical/agt_reminder lesen (außer Personalstamm, Erinnerung)
    allowed = {"atemschutz.py", "db.py", "agt_reminders.py"}
    for path in root.rglob("*.py"):
        if path.name in allowed or path.name == "people.py":
            continue
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"agt_(entry|medical|reminder)\b", text), path


def test_summary_functions_are_the_only_cross_person_queries():
    root = pathlib.Path(__file__).resolve().parent.parent / "app"
    source = (root / "atemschutz.py").read_text(encoding="utf-8")
    tail = source.split("# ---------------------------------------------------------------- Auswertung der Wehrführung")[1]
    names = re.findall(r"^def (\w+)", tail, flags=re.M)
    assert tuple(names) == atemschutz.SUMMARY_FUNCTIONS


def test_atemschutz_never_enters_evaluations(world):
    """Weder Einsatzauswertung noch Export lesen aus agt_*: Einträge ändern nichts an den Kennzahlen."""
    _as(world, "lead@example.org")
    before = world.get("/api/evaluation").text
    _as(world, "anna@example.org")
    world.post("/api/atemschutz/me/entries", json={"source": {"kind": "incident", "id": world.ids["incident"]},
                                                   "duration_min": 5})
    _as(world, "lead@example.org")
    assert world.get("/api/evaluation").text == before
    assert "agt_" not in world.get("/api/members?tenant=wehr-a1").text


def test_email_never_leaks_through_other_endpoints(world):
    _as(world, "lead@example.org")
    for path in ("/api/members?tenant=wehr-a1", "/api/incidents", "/api/trainings", "/api/evaluation", "/api/config"):
        assert "@example.org" not in world.get(path).text.replace("lead@example.org", ""), path


def test_migration_adds_columns_to_existing_database():
    con = db.connect(":memory:")
    db.migrate(con, db.TENANT_MIGRATIONS[:-1])
    con.execute("INSERT INTO member (name, last_name, first_name, sort_order) VALUES ('Muster, Max', 'Muster', 'Max', 1)")
    con.commit()
    db.migrate(con)
    assert con.execute("SELECT email FROM member").fetchone()[0] is None
    con.execute("UPDATE member SET email = 'Max@Example.org'")
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO member (name, last_name, first_name, sort_order, email) "
                    "VALUES ('Muster, Eva', 'Muster', 'Eva', 2, 'max@example.org')")


# ---------------------------------------------------------------- Erinnerungsmail
def _sent_mails(world, today, monkeypatch, valid_until="2026-02-01", offsets=(60, 30, 14), login_first=True):
    from app import agt_reminders
    monkeypatch.setattr("app.mail.SMTP_HOST", "smtp.example.org")
    if login_first:
        tenancy.record_login("anna@example.org")
    _as(world, "anna@example.org")
    world.post("/api/atemschutz/me/medical", json={"examined_on": "2025-02-01", "valid_until": valid_until})
    world.put("/api/atemschutz/me/reminder", json={"offsets": list(offsets)})
    sent = []
    tenants = tenancy.vg_tenants(world.ids["vg-a"])
    count = agt_reminders.run_once(tenants, today, send=lambda *a, **k: sent.append(a))
    return count, sent, tenants


def test_reminder_sent_once_per_step_only_to_own_logged_in_address(world, monkeypatch):
    import datetime as dt
    from app import agt_reminders
    count, sent, tenants = _sent_mails(world, dt.date(2025, 12, 5), monkeypatch)      # 58 Tage vorher → Stufe 60
    assert count == 1 and sent[0][0] == "anna@example.org" and "01.02.2026" in sent[0][2]
    assert "Beispiel" not in sent[0][2] and "Beispiel" not in sent[0][3]             # kein Name, keine Fremdangaben
    assert agt_reminders.run_once(tenants, dt.date(2025, 12, 6), send=lambda *a, **k: sent.append(a)) == 0   # nicht doppelt
    assert agt_reminders.run_once(tenants, dt.date(2026, 1, 2), send=lambda *a, **k: sent.append(a)) == 1    # Stufe 30
    assert agt_reminders.run_once(tenants, dt.date(2026, 1, 20), send=lambda *a, **k: sent.append(a)) == 1   # Stufe 14
    assert agt_reminders.run_once(tenants, dt.date(2026, 2, 2), send=lambda *a, **k: sent.append(a)) == 0    # abgelaufen
    assert len(sent) == 3


def test_reminder_does_not_catch_up_missed_steps(world, monkeypatch):
    import datetime as dt
    count, sent, _ = _sent_mails(world, dt.date(2026, 1, 25), monkeypatch)            # nur noch 7 Tage → eine Mail
    assert count == 1


def test_reminder_needs_login_opt_in_and_current_access(world, monkeypatch):
    import datetime as dt
    assert _sent_mails(world, dt.date(2025, 12, 5), monkeypatch, login_first=False)[0] == 0      # nie angemeldet
    assert _sent_mails(world, dt.date(2025, 12, 5), monkeypatch, offsets=())[0] == 0             # kein Opt-in
    assert _sent_mails(world, dt.date(2025, 10, 5), monkeypatch)[0] == 0                         # noch zu früh


def test_reminder_not_sent_after_access_is_removed(world, monkeypatch):
    import datetime as dt
    from app import agt_reminders
    _, _, tenants = _sent_mails(world, dt.date(2025, 1, 1), monkeypatch)
    _as(world, "lead@example.org")
    _set_email(world, world.ids["anna"], "anna-neu@example.org")                    # Adresse geändert
    tenancy.record_login("anna-neu@example.org")
    sent = []
    # die neue Adresse hat Opt-in nicht geerbt? Sie gehört zur Person: Mail geht an die aktuelle, angemeldete Adresse
    agt_reminders.run_once(tenants, dt.date(2025, 12, 5), send=lambda *a, **k: sent.append(a))
    assert [m[0] for m in sent] == ["anna-neu@example.org"]
    _set_email(world, world.ids["anna"], "anna-neu@example.org", active=False)
    sent.clear()
    agt_reminders.run_once(tenants, dt.date(2026, 1, 2), send=lambda *a, **k: sent.append(a))
    assert sent == []


def test_failed_mail_is_retried(world, monkeypatch):
    import datetime as dt
    import smtplib
    from app import agt_reminders
    _, _, tenants = _sent_mails(world, dt.date(2025, 1, 1), monkeypatch)

    def broken(*a, **k):
        raise smtplib.SMTPException("kaputt")
    assert agt_reminders.run_once(tenants, dt.date(2025, 12, 5), send=broken) == 0
    sent = []
    assert agt_reminders.run_once(tenants, dt.date(2025, 12, 6), send=lambda *a, **k: sent.append(a)) == 1


def test_due_offset_rules():
    import datetime as dt
    from app.agt_reminders import due_offset
    valid = dt.date(2026, 3, 1)
    assert due_offset(valid, (60, 30, 14), dt.date(2025, 12, 1)) == (None, [])
    assert due_offset(valid, (60, 30, 14), dt.date(2026, 1, 1)) == (60, [60])
    assert due_offset(valid, (60, 30, 14), dt.date(2026, 2, 10)) == (30, [30, 60])
    assert due_offset(valid, (60, 30, 14), dt.date(2026, 2, 10), sent={30, 60}) == (None, [30, 60])
    assert due_offset(valid, (60, 30, 14), dt.date(2026, 3, 2)) == (None, [])


# ---------------------------------------------------------------- Wehrwechsel
def _second_wehr(world):
    make_tenant("wehr-a2", "vg-a")
    grant("lead@example.org", "lead", tenancy_id(world, "wehr-a2"))


def test_transfer_moves_atemschutz_data_anonymised(world, monkeypatch):
    monkeypatch.setattr("app.mail.SMTP_HOST", "smtp.example.org")
    _second_wehr(world)
    _as(world, "anna@example.org")
    world.post("/api/atemschutz/me/entries", json={"source": {"kind": "incident", "id": world.ids["incident"]},
                                                   "duration_min": 40, "start_bar": 300, "end_bar": 100, "notes": "mit Max M."})
    world.post("/api/atemschutz/me/entries", json={**ENTRY, "external": True, "organisation": "Werkfeuerwehr", "kind": "uebung"})
    world.post("/api/atemschutz/me/medical", json={"examined_on": "2025-02-01", "valid_until": "2026-02-01"})
    world.put("/api/atemschutz/me/reminder", json={"offsets": [30]})
    _as(world, "lead@example.org")
    done = world.post(f"/api/admin/wehr-a1/members/{world.ids['anna']}/transfer", json={"to_slug": "wehr-a2"})
    assert done.status_code == 200, done.text
    # alt: nichts mehr, kein Zugang
    for table in ("agt_entry", "agt_medical", "agt_reminder"):
        assert _rows("wehr-a1", f"SELECT COUNT(*) FROM {table} WHERE member_id = ?", world.ids["anna"])[0][0] == 0
    assert _rows("wehr-a1", "SELECT email, active FROM member WHERE id = ?", world.ids["anna"])[0][0] is None
    # neu: übernommen ohne Quellverweis und Notizen
    rows = _rows("wehr-a2", "SELECT * FROM agt_entry ORDER BY started_at")
    assert len(rows) == 2 and all(r["source_kind"] is None and r["source_id"] is None and r["notes"] is None and r["keyword"] is None for r in rows)
    assert {r["duration_min"] for r in rows} == {40, 20} and {r["organisation"] for r in rows} == {None, "Werkfeuerwehr"}
    assert [tuple(r) for r in _rows("wehr-a2", "SELECT examined_on, valid_until FROM agt_medical")] == [("2025-02-01", "2026-02-01")]
    assert [r[0] for r in _rows("wehr-a2", "SELECT offsets FROM agt_reminder")] == ["[30]"]
    # Zugang folgt der Person
    _as(world, "anna@example.org", scope="t:wehr-a2")
    state = world.get("/api/atemschutz/me?year=2025").json()
    assert state["linked"] and len(state["entries"]) == 2 and state["medical"][0]["valid_until"] == "2026-02-01"
    _as(world, "anna@example.org", scope="t:wehr-a1")
    assert world.get("/api/config").json()["tenant"]["slug"] == "wehr-a2"           # in a1 keine Zuordnung mehr
    assert [tuple(r) for r in _rows("wehr-a1", "SELECT action FROM agt_audit WHERE action = 'agt.transfer.out'")]


def test_transfer_conflicting_email_in_target_changes_nothing(world):
    _second_wehr(world)
    _as(world, "anna@example.org")
    world.post("/api/atemschutz/me/entries", json=ENTRY)
    with db.connection(tenancy.tenant_path("wehr-a2")) as con:
        member = store.MemberDirectory(con).find_or_create("Beispiel", "Anna")
        con.execute("UPDATE member SET email = 'andere@example.org' WHERE id = ?", (member,))
    _as(world, "lead@example.org")
    done = world.post(f"/api/admin/wehr-a1/members/{world.ids['anna']}/transfer", json={"to_slug": "wehr-a2"})
    assert done.status_code == 409
    assert _rows("wehr-a1", "SELECT COUNT(*) FROM agt_entry")[0][0] == 1
    assert _rows("wehr-a2", "SELECT COUNT(*) FROM agt_entry")[0][0] == 0


def test_transfer_twice_does_not_duplicate(world):
    _second_wehr(world)
    _as(world, "anna@example.org")
    world.post("/api/atemschutz/me/entries", json=ENTRY)
    with db.connection(tenancy.tenant_path("wehr-a1")) as con:
        package = atemschutz.Own(con, world.ids["anna"]).export_anonymous()
    with db.connection(tenancy.tenant_path("wehr-a2")) as con:
        member = store.MemberDirectory(con).find_or_create("Beispiel", "Anna")
        own = atemschutz.Own(con, member)
        own.absorb(package)
        own.absorb(package)
        assert len(own.entries(2025)) == 1


# ---------------------------------------------------------------- Prüfansicht der Superadmins
def test_superadmin_check_shows_numbers_only(world):
    _as(world, "anna@example.org")
    world.post("/api/atemschutz/me/entries", json={**ENTRY, "notes": "geheim", "place": "Geheimort"})
    world.post("/api/atemschutz/me/medical", json={"examined_on": "2025-02-01", "valid_until": "2026-02-01"})
    _as(world, "admin@example.org")
    response = world.get("/api/super/atemschutz")
    assert response.status_code == 200
    data = response.json()
    assert data["deviations"] == []
    t = next(t for t in data["tenants"] if t["slug"] == "wehr-a1")
    assert (t["members"], t["with_email"], t["persons_with_data"], t["entries"], t["medical"]) == (2, 2, 1, 1, 1)
    assert t["email_without_access"] == 0 and t["access_without_person"] == 0
    text = response.text.lower()
    assert "geheim" not in text and "anna@example.org" not in text and "berta@example.org" not in text and "beispiel" not in text
    assert any(e["action"] == "agt.check.view" and e["email"] == "admin@example.org" for e in t["events"])


def test_superadmin_check_finds_mismatches_and_wrong_rights(world):
    with db.connection(tenancy.tenant_path("wehr-a1")) as con:
        con.execute("UPDATE member SET email = 'ohne-zugang@example.org' WHERE id = ?", (world.ids["anna"],))   # Stamm ohne Zuordnung
    with tenancy.central() as con:
        con.execute("INSERT OR IGNORE INTO role_permission (role_id, permission) SELECT id, 'agt.evaluate' FROM role WHERE key = 'editor'")
    _as(world, "admin@example.org")
    data = world.get("/api/super/atemschutz").json()
    t = next(t for t in data["tenants"] if t["slug"] == "wehr-a1")
    assert t["email_without_access"] == 1 and t["access_without_person"] == 1          # Annas alte Zuordnung ist verwaist
    assert any(d.startswith("editor") for d in data["deviations"])


@pytest.mark.parametrize("email", ["lead@example.org", "vglead@example.org", "anna@example.org"])
def test_only_superadmin_may_open_the_check(world, email):
    _as(world, email)
    assert world.get("/api/super/atemschutz").status_code == 403


# ---------------------------------------------------------------- Einsicht der Superadmins (offen, lesend, protokolliert)
def test_superadmin_insight_is_read_only_logged_and_visible_to_the_person(world):
    _as(world, "anna@example.org")
    world.post("/api/atemschutz/me/entries", json={**ENTRY, "notes": "Notiz", "keyword": "Strecke"})
    assert world.get("/api/atemschutz/me").json()["admin_access"] == []
    _as(world, "admin@example.org")
    people = world.get("/api/super/atemschutz/wehr-a1/people").json()["people"]
    anna = next(p for p in people if p["id"] == world.ids["anna"])
    assert anna["entries"] == 1
    person = world.get(f"/api/super/atemschutz/wehr-a1/people/{world.ids['anna']}").json()
    assert person["name"] == "Beispiel, Anna" and person["entries"][0]["notes"] == "Notiz" and person["email"] == "anna@example.org"
    # nur lesend
    assert world.post(f"/api/super/atemschutz/wehr-a1/people/{world.ids['anna']}", json={}).status_code == 405
    assert world.get("/api/super/atemschutz/wehr-a1/people/9999").status_code == 404
    assert world.get("/api/super/atemschutz/gibt-es-nicht/people").status_code == 404
    # die Person sieht die Einsicht, die Prüfansicht listet sie
    _as(world, "anna@example.org")
    access = world.get("/api/atemschutz/me").json()["admin_access"]
    assert [a["email"] for a in access] == ["admin@example.org"]
    _as(world, "berta@example.org")
    assert world.get("/api/atemschutz/me").json()["admin_access"] == []                   # nur bei der betroffenen Person
    _as(world, "admin@example.org")
    events = next(t for t in world.get("/api/super/atemschutz").json()["tenants"] if t["slug"] == "wehr-a1")["events"]
    assert {"agt.admin.list", "agt.admin.view"} <= {e["action"] for e in events}


@pytest.mark.parametrize("email", ["lead@example.org", "vglead@example.org", "anna@example.org", "editor@example.org"])
def test_only_superadmin_has_the_insight(world, email):
    _as(world, email)
    assert world.get("/api/super/atemschutz/wehr-a1/people").status_code == 403
    assert world.get(f"/api/super/atemschutz/wehr-a1/people/{world.ids['berta']}").status_code == 403
    assert _rows("wehr-a1", "SELECT COUNT(*) FROM agt_audit WHERE action LIKE 'agt.admin.%'")[0][0] == 0
