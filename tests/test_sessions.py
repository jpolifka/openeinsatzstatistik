# -*- coding: utf-8 -*-
"""Sitzungen einsehen und beenden (nur Superadmin)."""
import pytest

from app import auth
from conftest import grant, login, make_tenant


@pytest.fixture
def setup(make_client, monkeypatch):
    _, tenant_id = make_tenant("wehr-a1")
    grant("m.muster@example.org", "lead", tenant_id)
    monkeypatch.setattr(auth, "_last_mail", {})
    admin = login(make_client(login=True), "admin@example.org")
    user = login(make_client(login=True), "m.muster@example.org")
    return admin, user


def test_only_superadmin_sees_and_ends_sessions(setup):
    admin, user = setup
    assert user.get("/api/super/sessions").status_code == 403
    assert user.delete("/api/super/sessions/1").status_code == 403
    assert user.delete("/api/super/sessions?others=true").status_code == 403
    listed = admin.get("/api/super/sessions").json()
    assert {s["email"] for s in listed["sessions"]} == {"admin@example.org", "m.muster@example.org"}
    assert [s["email"] for s in listed["sessions"] if s["current"]] == ["admin@example.org"]
    assert "token" not in str(listed) and "token_hash" not in str(listed)


def test_end_single_session_logs_user_out(setup):
    admin, user = setup
    assert user.get("/api/years").status_code == 200
    target = next(s for s in admin.get("/api/super/sessions").json()["sessions"] if s["email"] == "m.muster@example.org")
    result = admin.delete(f"/api/super/sessions/{target['id']}").json()
    assert all(s["email"] != "m.muster@example.org" for s in result["sessions"])
    assert user.get("/api/years").status_code == 401


def test_own_session_is_not_ended_by_id(setup):
    admin, _ = setup
    own = next(s for s in admin.get("/api/super/sessions").json()["sessions"] if s["current"])
    assert admin.delete(f"/api/super/sessions/{own['id']}").status_code == 422
    assert admin.get("/api/years").status_code == 200


def test_end_all_sessions_of_address_keeps_own(setup):
    admin, user = setup
    auth.create_session("m.muster@example.org")
    admin.delete("/api/super/sessions", params={"email": " M.Muster@example.org "})
    assert user.get("/api/years").status_code == 401
    # auch die eigene Adresse: die aktuelle Sitzung bleibt
    auth.create_session("admin@example.org")
    result = admin.delete("/api/super/sessions", params={"email": "admin@example.org"}).json()
    assert [s["email"] for s in result["sessions"]] == ["admin@example.org"] and result["sessions"][0]["current"]


def test_end_all_others(setup):
    admin, user = setup
    admin.delete("/api/super/sessions", params={"others": "true"})
    assert user.get("/api/years").status_code == 401
    assert admin.get("/api/years").status_code == 200
    assert admin.delete("/api/super/sessions").status_code == 422        # weder Adresse noch „alle anderen“
