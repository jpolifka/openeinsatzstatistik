# -*- coding: utf-8 -*-
import re

import pytest

from app import auth, tenancy
from conftest import grant, make_tenant


@pytest.fixture
def client(make_client, monkeypatch):
    _, tenant_id = make_tenant("wehr-a1")
    grant("m.muster@example.org", "lead", tenant_id)
    monkeypatch.setattr(auth, "_used_links", {})
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


def test_tampered_or_wrong_purpose_token_is_rejected(client, caplog):
    token = _link_token(caplog, client)
    # Link-Token taugt nicht als Sitzungs-Cookie
    client.cookies.set(auth.COOKIE, token)
    assert client.get("/api/years").status_code == 401
    session = auth._sign("session", "m.muster@example.org", 60)
    client.cookies.set(auth.COOKIE, session[:-1] + ("0" if session[-1] != "0" else "1"))
    assert client.get("/api/years").status_code == 401
    client.cookies.set(auth.COOKIE, session)
    assert client.get("/api/years").status_code == 200


def test_logout_clears_session(client, caplog):
    client.post("/auth/verify", data={"token": _link_token(caplog, client)})
    client.post("/logout")
    assert client.get("/api/years").status_code == 401


def test_browser_navigation_to_api_redirects(client):
    response = client.get("/api/export", headers={"accept": "text/html"}, follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/login"


def test_failed_mail_allows_immediate_retry(client, monkeypatch):
    monkeypatch.setattr(auth, "RESEND_API_KEY", "test")
    monkeypatch.setattr(auth, "MAIL_FROM", "Test <test@example.org>")
    calls = []

    def fail(req, timeout):
        calls.append(req)
        raise OSError("kein Netz")

    monkeypatch.setattr(auth.urllib.request, "urlopen", fail)
    client.post("/login", data={"email": "m.muster@example.org"})
    client.post("/login", data={"email": "m.muster@example.org"})
    assert len(calls) == 2


def test_resend_key_without_sender_stops_start(monkeypatch):
    monkeypatch.setattr(auth, "RESEND_API_KEY", "test")
    monkeypatch.setattr(auth, "MAIL_FROM", "")
    with pytest.raises(RuntimeError):
        auth.check_config()


def test_login_without_base_url_stops_start(monkeypatch):
    monkeypatch.setattr(tenancy, "ADMIN_EMAILS", {"admin@example.org"})
    monkeypatch.setattr(auth, "BASE_URL", "")
    with pytest.raises(RuntimeError):
        auth.check_config()
