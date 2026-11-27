# -*- coding: utf-8 -*-
"""Abzeichnung von Atemschutz-Einträgen durch die Wehrführung, CSA als Fähigkeit mit Protokoll, CSA-Belastungsübung."""
import pytest

from app import db, rbac, store, tenancy
from conftest import grant, login, make_tenant

TRAINING = {"topic": "CSA-Belastung", "started_at": "2025-05-10T09:00", "ended_at": "2025-05-10T11:00",
            "member_ids": [], "new_members": [], "csa_load": True}


@pytest.fixture
def world(make_client):
    vg, a1 = make_tenant("wehr-a1", "vg-a")
    grant("lead@example.org", "lead", a1)
    grant("deputy@example.org", "deputy_lead", a1)
    grant("editor@example.org", "editor", a1)
    with db.connection(tenancy.tenant_path("wehr-a1")) as con:
        incident = store.create_incident(con, {"number": 1, "started_at": "2025-03-12T10:00:00", "keyword": "B2",
                                               "place": "Altenau"}, source="pdf")
        anna = store.MemberDirectory(con).find_or_create("Beispiel", "Anna")
    client = make_client(login=True)
    client.ids = {"incident": f"wehr-a1:{incident}", "anna": anna}
    _as(client, "lead@example.org")          # die Wehrführung pflegt die E-Mail, daraus entsteht der Zugang
    assert client.put(f"/api/admin/wehr-a1/members/{anna}", json={"last_name": "Beispiel", "first_name": "Anna",
                                                               "email": "anna@example.org"}).status_code == 200
    return client


def _as(client, email):
    client.cookies.clear()
    login(client, email)
    client.cookies.set("scope", "t:wehr-a1")
    return client


def _events(slug="wehr-a1"):
    with db.connection(tenancy.tenant_path(slug)) as con:
        return [dict(r) for r in con.execute("SELECT * FROM audit_event ORDER BY id")]


def _entry(world, email="anna@example.org", **fields):
    _as(world, email)
    body = {"kind": "strecke", "started_at": "2025-03-12T19:00", "duration_min": 20, "start_bar": 300, "end_bar": 120,
            "notes": "geheim", **fields}
    return world.post("/api/atemschutz/me/entries", json=body).json()


def test_lead_and_deputy_cosign_with_name_editor_cannot(world):
    entry = _entry(world)
    assert entry["cosign"] is None
    _as(world, "editor@example.org")
    assert world.get("/api/atemschutz/cosign").status_code == 403
    assert world.post(f"/api/atemschutz/cosign/{entry['id']}", json={"revision": entry["revision"]}).status_code == 403
    for email, name in (("lead@example.org", "Wehrführer, Willi"), ("deputy@example.org", "deputy@example.org")):
        if name != "deputy@example.org":
            with db.connection(tenancy.tenant_path("wehr-a1")) as con:
                lead = store.MemberDirectory(con).find_or_create("Wehrführer", "Willi")
                con.execute("UPDATE member SET email = ? WHERE id = ?", (email, lead))
        _as(world, email)
        listed = world.get("/api/atemschutz/cosign?year=2025").json()["entries"]
        assert listed[0]["person"] == "Beispiel, Anna" and "notes" not in listed[0]
        assert world.post(f"/api/atemschutz/cosign/{entry['id']}", json={"revision": entry["revision"]}).status_code == 200
        assert world.get("/api/atemschutz/cosign?year=2025").json()["entries"][0]["cosign"]["name"] == name
        _as(world, "anna@example.org")
        own = world.get("/api/atemschutz/me?year=2025").json()["entries"][0]
        assert own["cosign"]["name"] == name and own["cosign"]["valid"] is True
    _as(world, "lead@example.org")
    assert world.delete(f"/api/atemschutz/cosign/{entry['id']}").status_code == 200
    assert world.delete(f"/api/atemschutz/cosign/{entry['id']}").status_code == 404
    actions = [r["action"] for r in _audit()]
    assert "agt.cosign.sign" in actions and "agt.cosign.unsign" in actions and "agt.cosign.view" in actions


def _audit():
    with db.connection(tenancy.tenant_path("wehr-a1")) as con:
        return [dict(r) for r in con.execute("SELECT * FROM agt_audit ORDER BY id")]


def test_cosign_expires_with_change_and_stale_revision_is_refused(world):
    entry = _entry(world)
    _as(world, "lead@example.org")
    url = f"/api/atemschutz/cosign/{entry['id']}"
    assert world.post(url, json={"revision": entry["revision"]}).status_code == 200
    _as(world, "anna@example.org")
    changed = world.put(f"/api/atemschutz/me/entries/{entry['id']}",
                        json={**ENTRY_BODY, "revision": entry["revision"]}).json()
    assert changed["cosign"]["valid"] is False                                 # veraltet, aber sichtbar
    _as(world, "lead@example.org")
    assert world.get("/api/atemschutz/cosign?year=2025").json()["entries"][0]["cosign"]["valid"] is False
    assert world.post(url, json={"revision": entry["revision"]}).status_code == 409
    assert world.post(url, json={"revision": changed["revision"]}).status_code == 200
    assert world.post("/api/atemschutz/cosign/9999", json={"revision": 0}).status_code == 404


ENTRY_BODY = {"kind": "strecke", "started_at": "2025-03-12T19:00", "duration_min": 25, "start_bar": 300, "end_bar": 100}


def test_nobody_cosigns_own_entry_and_cosign_goes_with_entry(world):
    with db.connection(tenancy.tenant_path("wehr-a1")) as con:
        lead = store.MemberDirectory(con).find_or_create("Wehrführer", "Willi")
        con.execute("UPDATE member SET email = 'lead@example.org' WHERE id = ?", (lead,))
    entry = _entry(world, "lead@example.org")
    assert world.post(f"/api/atemschutz/cosign/{entry['id']}", json={"revision": entry["revision"]}).status_code == 422
    other = _entry(world)
    _as(world, "lead@example.org")
    assert world.post(f"/api/atemschutz/cosign/{other['id']}", json={"revision": other["revision"]}).status_code == 200
    _as(world, "anna@example.org")
    assert world.delete(f"/api/atemschutz/me/entries/{other['id']}?revision={other['revision']}").status_code == 200
    with db.connection(tenancy.tenant_path("wehr-a1")) as con:
        assert con.execute("SELECT COUNT(*) FROM agt_cosign").fetchone()[0] == 0


def test_incidents_and_trainings_carry_no_signature_any_more(world):
    _as(world, "lead@example.org")
    assert "signature" not in world.get("/api/incidents?year=2025").json()["incidents"][0]
    assert world.post(f"/api/incidents/{world.ids['incident']}/sign", json={"revision": 0}).status_code in (404, 405)
    with tenancy.central() as con:
        roles = rbac.Roles(con)
        assert not any(p == "signoff.sign" for r in ("lead", "deputy_lead") for p in roles.permissions(roles.find(r, None).id))


def test_csa_flag_is_audited_and_drives_yearly_status(world):
    _as(world, "lead@example.org")
    anna = world.ids["anna"]
    url = f"/api/admin/wehr-a1/members/{anna}"
    body = {"last_name": "Beispiel", "first_name": "Anna", "active": True}
    assert world.put(url, json=body).status_code == 200                       # ohne csa: unverändert, kein Eintrag
    assert _events() == []
    assert world.put(url, json={**body, "csa": True}).json()["members"][0]["csa"] is True
    assert world.put(url, json={**body, "csa": True}).status_code == 200      # gleich geblieben: kein neuer Eintrag
    status = world.get("/api/trainings?year=2025").json()["csa"]
    assert status == [{"id": anna, "name": "Beispiel, Anna", "done": False, "last": None}]
    world.post("/api/trainings", json={**TRAINING, "member_ids": [anna]})
    world.post("/api/trainings", json={**TRAINING, "csa_load": False, "started_at": "2025-06-01T09:00",
                                       "ended_at": "2025-06-01T10:00", "member_ids": [anna]})
    assert world.get("/api/trainings?year=2025").json()["csa"][0]["last"] == "2025-05-10T09:00:00"
    assert world.get("/api/trainings?year=2024").json()["csa"][0]["done"] is False
    world.put(url, json={**body, "csa": False})
    assert world.get("/api/trainings?year=2025").json()["csa"] == []
    assert [(e["action"], e["kind"], e["ref_id"]) for e in _events()] == [("csa.set", "member", anna),
                                                                          ("csa.unset", "member", anna)]


def test_csa_requires_settings_right(world):
    _as(world, "editor@example.org")
    r = world.put(f"/api/admin/wehr-a1/members/{world.ids['anna']}",
                  json={"last_name": "Beispiel", "first_name": "Anna", "csa": True})
    assert r.status_code == 403


def test_deputy_sees_atemschutz_summary_but_not_own_data(world):
    _as(world, "deputy@example.org")
    assert world.get("/api/atemschutz/summary").status_code == 200
    assert world.get("/api/atemschutz/me").status_code == 403
    with tenancy.central() as con:
        roles = rbac.Roles(con)
        assert rbac.AGT_EVAL in roles.permissions(roles.find("deputy_lead", None).id)
        assert rbac.AGT_EVAL not in roles.permissions(roles.find("editor", None).id)


def test_notify_person_when_email_is_set(world, monkeypatch):
    from app.admin import people
    mail = people.mail          # das Modul, das die Verwaltung wirklich nutzt
    sent = []
    monkeypatch.setattr(mail, "enabled", lambda: True)
    monkeypatch.setattr(mail, "send", lambda to, subject, text, html, **kw: sent.append(to))
    _as(world, "lead@example.org")
    url = f"/api/admin/wehr-a1/members/{world.ids['anna']}"
    body = {"last_name": "Beispiel", "first_name": "Anna", "email": "anna@example.org"}
    assert "notice" not in world.put(url, json=body).json()                    # ohne Häkchen keine Mail
    assert sent == []
    world.put(url, json={**body, "email": None})
    assert world.put(url, json={**body, "notify": True}).json()["notice"] == "sent"
    assert sent == ["anna@example.org"]
    assert "notice" not in world.put(url, json={**body, "notify": True}).json()   # Adresse unverändert: nichts
    assert len(sent) == 1
    world.put(url, json={**body, "email": None})
    monkeypatch.setattr(mail, "send", lambda *a, **k: (_ for _ in ()).throw(OSError("aus")))
    assert world.put(url, json={**body, "notify": True}).json()["notice"] == "failed"   # Speichern gelingt trotzdem
    world.put(url, json={**body, "email": None})
    monkeypatch.setattr(mail, "enabled", lambda: False)
    assert world.put(url, json={**body, "notify": True}).json()["notice"] == "unavailable"


def test_user_list_hides_atemschutz_access_and_ranks_roles(world):
    with tenancy.central() as con:
        tenant = con.execute("SELECT id FROM tenant WHERE slug = 'wehr-a1'").fetchone()[0]
        tenancy.add_account(con, "agt@example.org")
        tenancy.grant(con, "agt@example.org", "agt_self", tenant)
    _as(world, "lead@example.org")
    items = world.get("/api/admin/memberships").json()["memberships"]
    assert "agt@example.org" not in {m["email"] for m in items}
    rank = {m["role"]: m["rank"] for m in items}
    assert rank["lead"] > rank["editor"]
