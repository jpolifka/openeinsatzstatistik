# -*- coding: utf-8 -*-
import re

import pytest

from app import auth, mail, tenancy
from conftest import grant, login, make_tenant


@pytest.fixture
def client(make_client, monkeypatch):
    _, tenant_id = make_tenant("wehr-a1")
    grant("m.muster@example.org", "lead", tenant_id)
    monkeypatch.setattr(auth, "_last_mail", {})
    monkeypatch.setattr(auth, "_sent", [])      # sonst erschöpfen mehrere Tests die Grenze je Adresse
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

    def fail(to, subject, text, html, **kwargs):
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


def test_start_without_login_needs_explicit_opt_out(monkeypatch):
    monkeypatch.setattr(tenancy, "ADMIN_EMAILS", set())
    monkeypatch.setattr(auth, "BASE_URL", "http://localhost:8112")
    monkeypatch.setattr(auth, "AUTH_DISABLED", False)
    with pytest.raises(RuntimeError, match="AUTH_DISABLED"):
        auth.check_config()
    monkeypatch.setattr(auth, "AUTH_DISABLED", True)
    auth.check_config()                                  # lokale Entwicklung: erlaubt
    monkeypatch.setattr(auth, "BASE_URL", "https://einsatz.example.org")
    with pytest.raises(RuntimeError):                    # öffentliche Adresse ohne Anmeldung nie
        auth.check_config()


def test_disabling_login_and_admins_together_is_refused(monkeypatch):
    monkeypatch.setattr(tenancy, "ADMIN_EMAILS", {"admin@example.org"})
    monkeypatch.setattr(auth, "BASE_URL", "http://localhost:8112")
    monkeypatch.setattr(auth, "AUTH_DISABLED", True)
    with pytest.raises(RuntimeError, match="widersprechen"):
        auth.check_config()


def _subdomain(vg, sub):
    with tenancy.central() as con:
        tenancy.set_vg_subdomain(con, con.execute("SELECT id FROM vg WHERE slug = ?", (vg,)).fetchone()[0], sub)


def test_link_target_comes_from_membership_not_from_host_header(client, monkeypatch):
    monkeypatch.setattr(auth, "BASE_URL", "https://login.example.org")
    monkeypatch.setattr(auth, "BASE_DOMAIN", "example.org")
    _subdomain("vg-a", "musterstadt")
    mine = "https://musterstadt.example.org"
    assert auth.link_base("m.muster@example.org", "musterstadt.example.org") == mine
    assert auth.link_base("m.muster@example.org", "Musterstadt.Example.ORG:443") == mine
    # Fremde, Geschwister- und Phantasie-Hosts erzeugen nie ein Ziel – es bleibt bei der eigenen VG
    for fremd in ("evil.example.org", "evil.com", "musterstadt.example.org.evil.com", "xmusterstadt.example.org",
                  "", None, "a.example.org/x", "a@example.org", "example.org"):
        assert auth.link_base("m.muster@example.org", fremd) == mine
    # Ohne Zuordnung zu einer VG mit Subdomain oder ohne BASE_DOMAIN: BASE_URL
    assert auth.link_base("fremd@example.org", "musterstadt.example.org") == "https://login.example.org"
    monkeypatch.setattr(auth, "BASE_DOMAIN", "")
    assert auth.link_base("m.muster@example.org", "musterstadt.example.org") == "https://login.example.org"


def test_link_target_vg_without_subdomain_uses_base_url(client, monkeypatch):
    monkeypatch.setattr(auth, "BASE_URL", "https://login.example.org")
    monkeypatch.setattr(auth, "BASE_DOMAIN", "example.org")
    assert auth.link_base("m.muster@example.org", "wehr-a1.example.org") == "https://login.example.org"


def test_subdomain_is_unique_and_checked(client):
    make_tenant("wehr-b1", "vg-b")
    _subdomain("vg-a", "Musterstadt")
    with pytest.raises(ValueError, match="schon"):
        _subdomain("vg-b", "musterstadt")
    for bad in ("a.b", "-a", "a b", "a/b", "ä"):
        with pytest.raises(ValueError, match="Subdomain"):
            _subdomain("vg-b", bad)
    _subdomain("vg-b", "")                       # leer = keine


def test_superadmin_sets_subdomain(client):
    login(client, "admin@example.org")
    r = client.post("/api/super/vgs", json={"name": "VG Neustadt", "subdomain": "Neustadt"})
    assert r.status_code == 200
    assert {v["slug"]: v["subdomain"] for v in r.json()["vgs"]}["neustadt"] == "neustadt"
    assert client.post("/api/super/vgs", json={"name": "VG Zwei", "subdomain": "neustadt"}).status_code == 422
    assert client.put("/api/super/vgs/neustadt", json={"name": "VG Neustadt", "subdomain": "a.b"}).status_code == 422


def test_login_link_points_to_configured_vg_host(client, monkeypatch, caplog):
    monkeypatch.setattr(auth, "BASE_URL", "http://localhost")
    monkeypatch.setattr(auth, "BASE_DOMAIN", "localhost")
    _subdomain("vg-a", "wehr1")
    client.post("/login", data={"email": "m.muster@example.org"}, headers={"host": "evil.localhost"})
    assert "http://wehr1.localhost/auth/verify?token=" in caplog.text
    assert "evil.localhost" not in caplog.text


def test_old_allowed_domains_setting_is_refused(monkeypatch):
    monkeypatch.setenv("ALLOWED_DOMAINS", "example.org")
    with pytest.raises(RuntimeError, match="BASE_DOMAIN"):
        auth.check_config()


def test_auth_disabled_needs_loopback_binding(monkeypatch):
    """BASE_URL lokal, aber Dienst im Netz veröffentlicht (APP_BIND=0.0.0.0): ohne Anmeldung nie."""
    monkeypatch.setattr(tenancy, "ADMIN_EMAILS", set())
    monkeypatch.setattr(auth, "BASE_URL", "http://localhost:8112")
    monkeypatch.setattr(auth, "AUTH_DISABLED", True)
    for bind in ("0.0.0.0", "192.168.1.5", "::"):
        monkeypatch.setattr(auth, "APP_BIND", bind)
        with pytest.raises(RuntimeError, match="APP_BIND"):
            auth.check_config()
    for bind in ("", "127.0.0.1", "[::1]".strip("[]")):
        monkeypatch.setattr(auth, "APP_BIND", bind)
        auth.check_config()


def test_public_base_url_must_be_https(monkeypatch):
    monkeypatch.setattr(tenancy, "ADMIN_EMAILS", {"admin@example.org"})
    monkeypatch.setattr(auth, "AUTH_DISABLED", False)
    monkeypatch.setattr(auth.mail, "SMTP_HOST", "smtp.example.org")
    monkeypatch.setattr(auth, "BASE_URL", "http://einsatz.example.org")
    with pytest.raises(RuntimeError, match="https"):
        auth.check_config()
