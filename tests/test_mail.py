# -*- coding: utf-8 -*-
"""Versand per SMTP mit eigener DKIM-Signatur und Prüfung von SPF, DKIM und DMARC (DNS gestellt)."""
import email
import smtplib

import dkim
import pytest

from app import mail


@pytest.fixture
def smtp(tmp_path, monkeypatch):
    """SMTP-Konfiguration wie bei Strato mit DKIM-Schlüssel; liefert die eingelieferten Mails."""
    key = tmp_path / "dkim.key"
    record = mail.generate_key(str(key))
    for name, value in {"SMTP_HOST": "smtp.example.org", "SMTP_PORT": 465, "SMTP_SECURITY": "ssl",
                        "SMTP_USER": "statistik@example.org", "SMTP_PASSWORD": "geheim",
                        "MAIL_FROM": "Einsatzstatistik <statistik@example.org>", "DKIM_SELECTOR": "app2026",
                        "DKIM_KEY_FILE": str(key)}.items():
        monkeypatch.setattr(mail, name, value)
    sent = []

    class FakeSMTP:
        def __init__(self, host, port, timeout, context=None):
            self.host, self.port, self.tls = host, port, context is not None
            self.calls = []

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self, context):
            self.tls = True

        def login(self, user, password):
            assert self.tls, "Anmeldung nur verschlüsselt"
            self.calls.append(("login", user, password))

        def sendmail(self, from_addr, to_addrs, data):
            sent.append({"host": self.host, "port": self.port, "from": from_addr, "to": to_addrs, "data": data,
                         "calls": self.calls})

    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTP)
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    return {"sent": sent, "record": record}


def test_mail_is_dkim_signed_and_aligned(smtp):
    mail.send("m.muster@example.org", "Anmeldung Einsatzstatistik", "Hallo", "<p>Hallo</p>")
    [message] = smtp["sent"]
    assert message["from"] == "statistik@example.org"              # Envelope-From = Absenderdomain (SPF)
    assert message["calls"] == [("login", "statistik@example.org", "geheim")]
    parsed = email.message_from_bytes(message["data"])
    assert parsed["From"] == "Einsatzstatistik <statistik@example.org>" and parsed["Message-ID"].endswith("@example.org>")
    tags = dict(t.strip().split("=", 1) for t in parsed["DKIM-Signature"].replace("\r\n", "").split(";") if "=" in t)
    assert tags["d"] == "example.org" and tags["s"] == "app2026" and tags["a"] == "rsa-sha256"   # d = From-Domain (DMARC)
    published = smtp["record"].encode()
    assert dkim.verify(message["data"], dnsfunc=lambda name, timeout=5: published)
    tampered = message["data"].replace(b"Hallo", b"Hallo, bitte hier klicken", 1)
    assert not dkim.verify(tampered, dnsfunc=lambda name, timeout=5: published)


def test_starttls_and_without_dkim(smtp, monkeypatch):
    monkeypatch.setattr(mail, "SMTP_SECURITY", "starttls")
    monkeypatch.setattr(mail, "SMTP_PORT", 587)
    monkeypatch.setattr(mail, "DKIM_SELECTOR", "")
    mail.send("m.muster@example.org", "Test", "x", "<p>x</p>")
    assert smtp["sent"][0]["port"] == 587 and b"DKIM-Signature" not in smtp["sent"][0]["data"]


@pytest.mark.parametrize("change, message", [
    ({"MAIL_FROM": ""}, "MAIL_FROM"),
    ({"SMTP_SECURITY": "plain"}, "SMTP_SECURITY"),
    ({"SMTP_PASSWORD": ""}, "SMTP_PASSWORD"),
    ({"DKIM_KEY_FILE": ""}, "nur zusammen"),
    ({"DKIM_KEY_FILE": "/fehlt/dkim.key"}, "fehlt"),
])
def test_incomplete_config_stops_start(smtp, monkeypatch, change, message):
    for name, value in change.items():
        monkeypatch.setattr(mail, name, value)
    with pytest.raises(RuntimeError, match=message):
        mail.check_config()


def test_key_is_never_overwritten(smtp):
    with pytest.raises(FileExistsError):
        mail.generate_key(mail.DKIM_KEY_FILE)


def _dns(records):
    return lambda name: records.get(name, [])


def test_dns_check(smtp, monkeypatch):
    good = {"example.org": ["v=spf1 redirect=_spf.strato.com"],
            "app2026._domainkey.example.org": [smtp["record"]],
            "_dmarc.example.org": ["v=DMARC1;p=reject; rua=mailto:dmarc@example.org"]}
    monkeypatch.setattr(mail, "txt", _dns(good))
    assert [ok for ok, _ in mail.check()] == [True, True, True]

    bad = {"example.org": ["v=spf1 +all"], "app2026._domainkey.example.org": ["v=DKIM1; k=rsa; p=ANDERER"]}
    monkeypatch.setattr(mail, "txt", _dns(bad))
    results = mail.check()
    assert [ok for ok, _ in results] == [False, False, False]
    assert "jedem Server" in results[0][1] and "passt nicht" in results[1][1] and "kein Eintrag" in results[2][1]
