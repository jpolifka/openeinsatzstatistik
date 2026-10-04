# -*- coding: utf-8 -*-
import re

import pytest

from app import auth, mail, tenancy
from conftest import grant, make_tenant


@pytest.fixture
def client(make_client, monkeypatch):
    _, tenant_id = make_tenant("wehr-a1")
    grant("m.muster@example.org", "lead", tenant_id)
    monkeypatch.setattr(auth, "_last_mail", {})
    return make_client(login=True)


def _link_token(caplog, client, email="m.muster@example.org"):
    client.post("/login", data={"email": email})
    found = re.findall(r"token=(\S+)", caplog.text)
    return found[-1] if found else None


def test_without_login_api_and_pages_are_closed(client):
    assert client.get("/api/years").status_code == 401
    page = client.get("/", follow_redirects=False)
    assert page.status_code == 303 and page.headers["location"] == "/login"
    assert client.get("/health").status_code == 200
    assert client.get("/login").status_code == 200


@pytest.mark.parametrize("host", ["testserver/static/", "testserver/login?", "testserver/auth/#"])
def test_host_cannot_turn_api_into_public_path(client, host):
    assert client.get("/api/config", headers={"host": host}).status_code == 401


def test_access_dependency_rejects_missing_session(client):
    from fastapi import HTTPException
    from starlette.requests import Request
    with pytest.raises(HTTPException) as error:
        auth.access(Request({"type": "http", "headers": []}))
    assert error.value.status_code == 401


def test_magic_link_logs_in_once(client, caplog):
    token = _link_token(caplog, client, " M.Muster@example.org ")
    assert token
    # Vorab-Aufruf durch Mailscanner verbraucht den Link nicht
    assert "Jetzt anmelden" in client.get(f"/auth/verify?token={token}").text
    response = client.post("/auth/verify", data={"token": token}, follow_redirects=False)
    assert response.status_code == 303 and auth.COOKIE in response.cookies
    assert client.get("/api/years").status_code == 200
    assert client.get("/api/config").json()["user"] == "m.muster@example.org"

    client.cookies.clear()
    again = client.post("/auth/verify", data={"token": token}, follow_redirects=False)
    assert again.status_code == 200 and auth.COOKIE not in again.cookies


def test_unknown_address_gets_no_link(client, caplog):
    assert _link_token(caplog, client, "fremd@example.org") is None


def test_used_magic_link_stays_consumed_after_process_cache_reset(client, caplog, monkeypatch):
    token = _link_token(caplog, client)
    assert auth._use_link(token) == "m.muster@example.org"
    monkeypatch.setattr(auth, "_key", None)
    assert auth._use_link(token) is None


def test_removed_address_loses_session(client, caplog):
    client.post("/auth/verify", data={"token": _link_token(caplog, client)})
    assert client.get("/api/years").status_code == 200
    with tenancy.central() as con:
        con.execute("DELETE FROM membership WHERE email = 'm.muster@example.org'")
    assert client.get("/api/years").status_code == 401


def test_deactivated_tenant_closes_access(client, caplog):
    client.post("/auth/verify", data={"token": _link_token(caplog, client)})
    with tenancy.central() as con:
        con.execute("UPDATE tenant SET active = 0")
    assert client.get("/api/years").status_code == 401


def test_superadmin_logs_in_without_membership(client, caplog):
    client.post("/auth/verify", data={"token": _link_token(caplog, client, "admin@example.org")})
    assert client.get("/api/config").json()["superadmin"] is True


def test_link_token_or_guessed_value_is_no_session(client, caplog):
    token = _link_token(caplog, client)
    # Link-Token taugt nicht als Sitzungs-Cookie, ein erratener Wert auch nicht
    for value in (token, "x" * 43, "a" * 500):
        client.cookies.set(auth.COOKIE, value)
        assert client.get("/api/years").status_code == 401
    client.cookies.set(auth.COOKIE, auth.create_session("m.muster@example.org"))
    assert client.get("/api/years").status_code == 200


def test_session_cookie_is_random_and_stored_hashed(client):
    first = auth.create_session("m.muster@example.org")
    assert first != auth.create_session("m.muster@example.org")
    with tenancy.central() as con:
        hashes = [r[0] for r in con.execute("SELECT token_hash FROM session")]
    assert first not in hashes and auth._hash(first) in hashes


def test_expired_session_is_rejected_and_cleaned_up(client):
    client.cookies.set(auth.COOKIE, auth.create_session("m.muster@example.org"))
    with tenancy.central() as con:
        con.execute("UPDATE session SET expires = 1")
    assert client.get("/api/years").status_code == 401
    auth.create_session("m.muster@example.org")
    with tenancy.central() as con:
        assert con.execute("SELECT COUNT(*) FROM session WHERE expires < 100").fetchone()[0] == 0


def test_logout_clears_session(client, caplog):
    client.post("/auth/verify", data={"token": _link_token(caplog, client)})
    stolen = client.cookies.get(auth.COOKIE)
    client.post("/logout")
    assert client.get("/api/years").status_code == 401
    # Ein vorher kopiertes Cookie ist ebenfalls wertlos (serverseitig beendet)
    client.cookies.set(auth.COOKIE, stolen)
    assert client.get("/api/years").status_code == 401


def test_browser_navigation_to_api_redirects(client):
    response = client.get("/api/export", headers={"accept": "text/html"}, follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/login"


def test_failed_mail_allows_immediate_retry(client, monkeypatch):
    monkeypatch.setattr(mail, "SMTP_HOST", "smtp.example.org")
    calls = []

    def fail(to, subject, text, html):
        calls.append(to)
        raise OSError("kein Netz")

    monkeypatch.setattr(mail, "send", fail)
    client.post("/login", data={"email": "m.muster@example.org"})
    client.post("/login", data={"email": "m.muster@example.org"})
    assert calls == ["m.muster@example.org"] * 2


def test_old_resend_key_stops_start(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "test")
    with pytest.raises(RuntimeError, match="SMTP"):
        auth.check_config()


def test_login_without_base_url_stops_start(monkeypatch):
    monkeypatch.setattr(tenancy, "ADMIN_EMAILS", {"admin@example.org"})
    monkeypatch.setattr(auth, "BASE_URL", "")
    with pytest.raises(RuntimeError):
        auth.check_config()
