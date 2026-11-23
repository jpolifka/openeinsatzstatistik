# -*- coding: utf-8 -*-
"""Lücken in mail, auth und main: DNS-Prüfung, Kommandozeile, Tokens, Sitzungen, Startprüfungen."""
import base64
import smtplib
import time

import dns.exception
import dns.resolver
import pytest
from fastapi.testclient import TestClient

from app import auth, db, mail, main, tenancy
from conftest import login
from test_mail import _dns, smtp  # noqa: F401  (Fixture smtp)


# ---------------------------------------------------------------- mail
def test_txt_joins_chunks_and_swallows_missing_names(monkeypatch):
    class Answer:
        def __init__(self, *chunks):
            self.strings = chunks

    monkeypatch.setattr(mail.dns.resolver, "resolve", lambda name, kind, lifetime: [Answer(b"v=spf1 ", b"-all")])
    assert mail.txt("example.org") == ["v=spf1 -all"]

    def missing(name, kind, lifetime):
        raise dns.resolver.NXDOMAIN()

    monkeypatch.setattr(mail.dns.resolver, "resolve", missing)
    assert mail.txt("example.org") == []


def test_check_covers_missing_sender_spf_count_and_unsigned_mail(smtp, monkeypatch):
    original = mail.MAIL_FROM
    monkeypatch.setattr(mail, "MAIL_FROM", "")
    assert mail.check() == [(False, "MAIL_FROM fehlt")]
    monkeypatch.setattr(mail, "MAIL_FROM", original)
    monkeypatch.setattr(mail, "DKIM_SELECTOR", "")
    monkeypatch.setattr(mail, "txt", _dns({"example.org": ["v=spf1 a", "v=spf1 mx"],
                                           "_dmarc.example.org": ["v=DMARC1; p=none; adkim=s; aspf=s"]}))
    results = mail.check()
    assert results[0][0] is False and "2 Einträge" in results[0][1]
    assert results[1][0] is None and "signiert nicht" in results[1][1]
    assert results[2][0] is True and "DKIM und SPF" in results[2][1]


def test_check_reports_unreachable_dns(smtp, monkeypatch):
    def broken(name):
        raise dns.exception.Timeout()

    monkeypatch.setattr(mail, "txt", broken)
    assert mail.check() == [(None, "DNS nicht erreichbar (Timeout) – Prüfung übersprungen")]


def test_log_check_logs_each_result(smtp, monkeypatch, caplog):
    monkeypatch.setattr(mail, "txt", _dns({"example.org": ["v=spf1 a"]}))
    with caplog.at_level("INFO", logger="openeinsatzstatistik"):
        mail.log_check()
    assert any("Mailversand: SPF" in r.message for r in caplog.records)
    monkeypatch.setattr(mail, "SMTP_HOST", "")
    caplog.clear()
    mail.log_check()
    assert not caplog.records


def test_command_line(smtp, monkeypatch, tmp_path, capsys):
    key = tmp_path / "neu.key"
    mail.main(["dkim-key", str(key)])
    assert key.exists() and "DNS-Eintrag (TXT)" in capsys.readouterr().out
    monkeypatch.setattr(mail, "DKIM_KEY_FILE", "")
    with pytest.raises(SystemExit, match="Pfad fehlt"):
        mail.main(["dkim-key"])
    monkeypatch.setattr(mail, "DKIM_SELECTOR", "")

    monkeypatch.setattr(mail, "txt", _dns({"example.org": ["v=spf1 a"]}))
    with pytest.raises(SystemExit) as failed:
        mail.main(["check"])
    assert failed.value.code == 1 and "FEHL" in capsys.readouterr().out
    monkeypatch.setattr(mail, "check", lambda: [(True, "alles gut"), (None, "Hinweis")])
    with pytest.raises(SystemExit) as passed:
        mail.main(["check"])
    assert passed.value.code == 0

    sent = []
    monkeypatch.setattr(mail, "check_config", lambda: None)
    monkeypatch.setattr(mail, "send", lambda *args: sent.append(args))
    mail.main(["test", "m.muster@example.org"])
    assert sent[0][0] == "m.muster@example.org" and "gesendet an" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        mail.main([])


# ---------------------------------------------------------------- auth
def test_secret_comes_from_environment_or_is_created(data_dir, monkeypatch):
    monkeypatch.setattr(auth, "SECRET_KEY", "aus-der-umgebung")
    monkeypatch.setattr(auth, "_key", None)
    assert auth._secret() == b"aus-der-umgebung"
    monkeypatch.setattr(auth, "SECRET_KEY", "")
    monkeypatch.setattr(auth, "_key", None)
    created = auth._secret()
    monkeypatch.setattr(auth, "_key", None)
    assert auth._secret() == created and (data_dir / "session.key").exists()


@pytest.mark.parametrize("token", ["", "ohne-punkt", "abc.falsche-signatur"])
def test_malformed_tokens_are_rejected(data_dir, monkeypatch, token):
    monkeypatch.setattr(auth, "_key", b"k")
    assert auth._verify("link", token) is None


def test_token_with_garbage_payload_is_rejected(data_dir, monkeypatch):
    monkeypatch.setattr(auth, "_key", b"k")
    payload = base64.urlsafe_b64encode(b"admin@example.org|keine-zahl").decode().rstrip("=")
    assert auth._verify("link", f"{payload}.{auth._mac('link', payload)}") is None
    assert auth._use_link("kaputt") is None


def test_session_touch_and_expiry(make_client, data_dir, monkeypatch):
    client = make_client(login=True)
    token = auth.create_session("admin@example.org")
    client.cookies.set(auth.COOKIE, token)
    with tenancy.central() as con:
        con.execute("UPDATE session SET last_seen = ?", (time.time() - 5 * 24 * 3600,))
    assert client.get("/api/super/overview").status_code == 200
    with tenancy.central() as con:
        assert con.execute("SELECT last_seen FROM session").fetchone()[0] > time.time() - 60
        con.execute("UPDATE session SET expires = ?", (time.time() - 1,))
    assert client.get("/api/super/overview").status_code == 401
    client.cookies.set(auth.COOKIE, "x" * 101)
    assert client.get("/api/super/overview").status_code == 401


def test_login_pages(make_client, data_dir):
    client = make_client(login=True)
    assert client.get("/login").status_code == 200
    login(client, "admin@example.org")
    assert client.get("/login", follow_redirects=False).status_code == 303
    assert "abgelaufen oder ungültig" in client.get("/auth/verify?token=falsch").text


def test_second_link_request_within_cooldown_sends_nothing(data_dir, monkeypatch, caplog):
    monkeypatch.setattr(tenancy, "ADMIN_EMAILS", {"admin@example.org"})
    monkeypatch.setattr(auth, "BASE_URL", "http://localhost")
    monkeypatch.setattr(auth, "_key", b"k")
    auth._last_mail.clear()
    auth._sent.clear()
    with caplog.at_level("WARNING", logger="openeinsatzstatistik"):
        auth.send_link("admin@example.org")
        auth.send_link("admin@example.org")
    assert sum("Anmeldelink für admin@example.org" in r.message for r in caplog.records) == 1


def test_failed_mail_delivery_allows_immediate_retry(smtp, data_dir, monkeypatch):
    monkeypatch.setattr(tenancy, "ADMIN_EMAILS", {"admin@example.org"})
    monkeypatch.setattr(auth, "_key", b"k")
    auth._last_mail.clear()
    auth._sent.clear()

    def refuse(*args, **kwargs):
        raise smtplib.SMTPException("abgelehnt")

    monkeypatch.setattr(mail, "send", refuse)
    auth.send_link("admin@example.org")
    assert "admin@example.org" not in auth._last_mail


# ---------------------------------------------------------------- main: Startprüfungen und Header
@pytest.mark.parametrize("environment, message", [
    ({"APP_PASSWORD": "alt"}, "APP_PASSWORD"),
    ({"AUTH_EMAILS": "m.muster@example.org"}, "AUTH_EMAILS"),
])
def test_start_refuses_unsupported_access_configuration(data_dir, monkeypatch, environment, message):
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(auth, "AUTH_DISABLED", True)
    monkeypatch.setattr(tenancy, "ADMIN_EMAILS", set())
    with pytest.raises(RuntimeError, match=message):
        with TestClient(main.app):
            pass


def test_start_refuses_missing_data_dir(monkeypatch):
    monkeypatch.setattr(db, "DATA_DIR", "")
    monkeypatch.setattr(auth, "AUTH_DISABLED", True)
    monkeypatch.setattr(tenancy, "ADMIN_EMAILS", set())
    with pytest.raises(RuntimeError, match="DATA_DIR"):
        with TestClient(main.app):
            pass


def test_start_warns_about_ignored_legacy_emails(data_dir, monkeypatch, caplog):
    monkeypatch.setenv("AUTH_EMAILS", "m.muster@example.org")
    monkeypatch.setattr(tenancy, "ADMIN_EMAILS", {"admin@example.org"})
    monkeypatch.setattr(auth, "BASE_URL", "http://localhost")
    with caplog.at_level("WARNING", logger="openeinsatzstatistik"):
        with TestClient(main.app):
            pass
    assert any("AUTH_EMAILS wird ignoriert" in r.message for r in caplog.records)


def test_hsts_is_set_for_https_base_url(monkeypatch):
    import importlib
    monkeypatch.setattr(auth, "BASE_URL", "https://statistik.example.org")
    reloaded = importlib.reload(main)
    try:
        assert reloaded.SECURITY_HEADERS["Strict-Transport-Security"].startswith("max-age=")
    finally:
        monkeypatch.setattr(auth, "BASE_URL", "http://localhost")
        importlib.reload(main)
