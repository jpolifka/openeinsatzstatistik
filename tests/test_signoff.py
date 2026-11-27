# -*- coding: utf-8 -*-
"""Signatur von Einsätzen und Übungen, CSA als Fähigkeit mit Protokoll, CSA-Belastungsübung, Atemschutz für die Stellvertretung."""
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
    return client


def _as(client, email):
    client.cookies.clear()
    login(client, email)
    client.cookies.set("scope", "t:wehr-a1")
    return client


def _incident(client):
    return client.get("/api/incidents?year=2025").json()["incidents"][0]


def _events(slug="wehr-a1"):
    with db.connection(tenancy.tenant_path(slug)) as con:
        return [dict(r) for r in con.execute("SELECT * FROM audit_event ORDER BY id")]


def test_lead_and_deputy_sign_incident_editor_cannot(world):
    key = world.ids["incident"]
    _as(world, "editor@example.org")
    assert _incident(world)["can_sign"] is False
    assert world.post(f"/api/incidents/{key}/sign", json={"revision": 0}).status_code == 403
    for email in ("lead@example.org", "deputy@example.org"):
        _as(world, email)
        incident = _incident(world)
        assert incident["can_sign"] and incident["signature"] is None
        signed = world.post(f"/api/incidents/{key}/sign", json={"revision": incident["revision"]}).json()
        assert signed["signature"]["valid"] is True
        assert world.post(f"/api/incidents/{key}/sign", json={"revision": incident["revision"], "signed": False}).json()[
            "signature"] is None
    assert [e["action"] for e in _events()] == ["sign", "unsign", "sign", "unsign"]
    assert {e["email"] for e in _events()} == {"lead@example.org", "deputy@example.org"}


def test_signature_expires_with_change_and_stale_revision_is_refused(world):
    key = world.ids["incident"]
    _as(world, "lead@example.org")
    revision = _incident(world)["revision"]
    assert world.post(f"/api/incidents/{key}/sign", json={"revision": revision}).status_code == 200
    assert world.put(f"/api/incidents/{key}", json={"place": "Neudorf", "revision": revision}).status_code == 200
    assert _incident(world)["signature"]["valid"] is False                   # veraltet, aber sichtbar
    assert world.post(f"/api/incidents/{key}/sign", json={"revision": revision}).status_code == 409
    assert world.post(f"/api/incidents/{key}/sign", json={"revision": revision + 1}).status_code == 200
    assert world.post("/api/incidents/wehr-a1:999/sign", json={"revision": 0}).status_code == 404


def test_signature_goes_with_deleted_incident(world):
    key = world.ids["incident"]
    _as(world, "lead@example.org")
    assert world.post(f"/api/incidents/{key}/sign", json={"revision": 0}).status_code == 200
    assert world.delete(f"/api/incidents/{key}?revision=0").status_code == 200
    with db.connection(tenancy.tenant_path("wehr-a1")) as con:
        assert con.execute("SELECT COUNT(*) FROM signoff").fetchone()[0] == 0


def test_audit_is_append_only(world):
    _as(world, "lead@example.org")
    world.post(f"/api/incidents/{world.ids['incident']}/sign", json={"revision": 0})
    with db.connection(tenancy.tenant_path("wehr-a1")) as con:
        with pytest.raises(Exception, match="nur anhängbar"):
            con.execute("DELETE FROM audit_event")
        with pytest.raises(Exception, match="nur anhängbar"):
            con.execute("UPDATE audit_event SET email = 'x'")
    assert world.get("/api/signoff/events").json()["events"][0]["action"] == "sign"
    _as(world, "editor@example.org")
    assert world.get("/api/signoff/events").status_code == 403


def test_sign_training_and_expiry(world):
    _as(world, "lead@example.org")
    training = world.post("/api/trainings", json=TRAINING).json()
    assert training["csa_load"] is True and training["signature"] is None
    url = f"/api/trainings/{training['id']}"
    assert world.post(url + "/sign", json={"revision": training["revision"]}).json()["signature"]["valid"] is True
    changed = world.put(url, json={**TRAINING, "topic": "Neu", "revision": training["revision"]}).json()
    assert changed["signature"]["valid"] is False
    _as(world, "editor@example.org")
    assert world.post(url + "/sign", json={"revision": changed["revision"]}).status_code == 403
    assert world.get("/api/trainings?year=2025").json()["trainings"][0]["signature"]["valid"] is False


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
        assert rbac.SIGN in roles.permissions(roles.find("deputy_lead", None).id)
        assert rbac.SIGN not in roles.permissions(roles.find("editor", None).id)


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
