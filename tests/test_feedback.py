# -*- coding: utf-8 -*-
import smtplib

import pytest

from app import feedback, mail, tenancy
from conftest import grant, login, make_tenant


@pytest.fixture
def sent(monkeypatch):
    """Versendete Mails landen in der Liste statt beim SMTP-Server."""
    mails = []
    monkeypatch.setattr(mail, "send", lambda to, subject, text, html, reply_to=None: mails.append(
        {"to": to, "subject": subject, "text": text, "html": html, "reply_to": reply_to}))
    monkeypatch.setattr(feedback, "_last_sent", {})
    return mails


@pytest.fixture
def client(make_client, sent, monkeypatch):
    c = make_client(login=True)
    # Mailversand erst nach dem Start einrichten (sonst prüft der Start die übrigen SMTP-Variablen)
    monkeypatch.setattr(mail, "SMTP_HOST", "smtp.example.org")
    _, tenant_id = make_tenant("musterstadt")
    grant("m.muster@example.org", "viewer", tenant_id)
    return login(c, "m.muster@example.org")


def test_feedback_goes_to_superadmins_with_reply_to_sender(client, sent):
    assert client.get("/api/config").json()["feedback"] is True
    r = client.post("/api/feedback", json={"message": "Diagramm <b>fehlt</b>", "view": "Auswertung"})
    assert r.status_code == 200
    assert [m["to"] for m in sent] == ["admin@example.org"]
    m = sent[0]
    assert m["reply_to"] == "m.muster@example.org"
    assert "Wehr musterstadt" in m["subject"]
    assert "Ansicht: Auswertung" in m["text"] and "Diagramm <b>fehlt</b>" in m["text"]
    assert "&lt;b&gt;fehlt" in m["html"]


def test_feedback_is_rate_limited(client, sent):
    assert client.post("/api/feedback", json={"message": "Eins"}).status_code == 200
    assert client.post("/api/feedback", json={"message": "Zwei"}).status_code == 429
    assert len(sent) == 1


def test_empty_feedback_is_rejected(client, sent):
    assert client.post("/api/feedback", json={"message": "   "}).status_code == 422
    assert client.post("/api/feedback", json={"message": "x" * 5001}).status_code == 422
    assert not sent


def test_failed_mail_allows_retry(client, monkeypatch):
    def fail(*args, **kwargs):
        raise smtplib.SMTPException("kaputt")
    monkeypatch.setattr(mail, "send", fail)
    assert client.post("/api/feedback", json={"message": "Eins"}).status_code == 502
    assert "m.muster@example.org" not in feedback._last_sent


def test_without_mail_or_login_feedback_is_off(make_client, monkeypatch):
    # Ohne Anmeldung (lokaler Betrieb) gibt es keinen Absender und keine Superadmins
    client = make_client()
    make_tenant("musterstadt")
    assert client.get("/api/config").json()["feedback"] is False
    assert client.post("/api/feedback", json={"message": "Hallo"}).status_code == 503
    # Mit Anmeldung, aber ohne SMTP
    monkeypatch.setattr(tenancy, "ADMIN_EMAILS", {"admin@example.org"})
    monkeypatch.setattr(mail, "SMTP_HOST", "")
    assert not feedback.enabled()


def test_reply_to_header_is_set():
    msg = mail.build("admin@example.org", "Betreff", "Text", "<p>Text</p>", reply_to="m.muster@example.org")
    assert msg["Reply-To"] == "m.muster@example.org"
    assert "Reply-To" not in mail.build("admin@example.org", "Betreff", "Text", "<p>Text</p>")
