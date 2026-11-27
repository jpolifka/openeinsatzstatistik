# -*- coding: utf-8 -*-
"""Willkommensmail für Führungspersonen: beim Zuordnen, einmalig je Person, Nachversand."""
import pytest

from app import mail, tenancy, welcome
from conftest import grant, login, make_tenant


@pytest.fixture
def world(make_client, monkeypatch):
    sent = []
    monkeypatch.setattr(mail, "send", lambda to, subject, text, html, **kw: sent.append((to, subject, text, html)))
    vg_a, a1 = make_tenant("wehr-a1", "vg-a")
    grant("vglead@example.org", "vg_lead", vg_a)
    client = make_client(login=True)       # SMTP_HOST erst nach dem Start setzen (check_config verlangt sonst alle SMTP_*)
    monkeypatch.setattr(mail, "SMTP_HOST", "smtp.example.org")
    client.cookies.clear()
    login(client, "vglead@example.org")
    tenancy.record_login("vglead@example.org")      # gilt als angemeldet: kommt im Nachversand nicht vor
    client.sent = sent
    client.a1 = a1
    client.vg_a = vg_a
    return client


def _give(client, email, role):
    return client.post("/api/admin/memberships", json={"email": email, "scope": "tenant", "slug": "wehr-a1", "role": role})


def test_leadership_gets_welcome_once(world):
    assert _give(world, "neu@example.org", "lead").status_code == 200
    assert [s[0] for s in world.sent] == ["neu@example.org"]
    _, subject, text, html = world.sent[0]
    assert subject.startswith("Willkommen in der Einsatzstatistik")
    assert "Wehrführer/in" in text and "Wehrführer/in" in html
    # weitere Rolle derselben Person: keine zweite Mail
    _give(world, "neu@example.org", "deputy_lead")
    assert len(world.sent) == 1


def test_other_roles_get_no_welcome(world):
    _give(world, "erfasser@example.org", "editor")
    assert world.sent == []


def test_failed_send_can_be_repeated(world, monkeypatch):
    def fail(*a, **k):
        raise OSError("kein Netz")

    monkeypatch.setattr(mail, "send", fail)
    assert _give(world, "neu@example.org", "lead").status_code == 200       # Zuordnung bleibt
    assert welcome.send_welcome("neu@example.org") == "failed"
    monkeypatch.setattr(mail, "send", lambda to, *a, **k: world.sent.append(to))
    assert welcome.send_welcome("neu@example.org") == "sent"
    assert welcome.send_welcome("neu@example.org") == "skipped"


def test_without_mail_nothing_is_marked(world, monkeypatch):
    monkeypatch.setattr(mail, "SMTP_HOST", "")
    _give(world, "neu@example.org", "lead")
    assert welcome.send_welcome("neu@example.org") == "unavailable"
    monkeypatch.setattr(mail, "SMTP_HOST", "smtp.example.org")
    assert welcome.send_welcome("neu@example.org") == "sent"


def test_catch_up_dry_run_and_send(world, monkeypatch):
    monkeypatch.setattr(mail, "SMTP_HOST", "")           # früher angelegt, ohne Mail
    _give(world, "alt@example.org", "lead")
    _give(world, "aktiv@example.org", "deputy_lead")
    _give(world, "erfasser@example.org", "editor")
    tenancy.record_login("aktiv@example.org")
    monkeypatch.setattr(mail, "SMTP_HOST", "smtp.example.org")
    world.sent.clear()
    # Probelauf: nichts verschickt; Angemeldete und Nicht-Führung übergangen
    assert welcome.catch_up() == {"alt@example.org": "would_send"}
    assert world.sent == []
    assert welcome.catch_up(send=True) == {"alt@example.org": "sent"}
    assert [s[0] for s in world.sent] == ["alt@example.org"]
    assert welcome.catch_up(send=True) == {}             # nicht erneut
    assert welcome.catch_up(send=True, include_active=True) == {"aktiv@example.org": "sent"}


def test_cli(world, capsys, monkeypatch):
    monkeypatch.setattr(mail, "SMTP_HOST", "")
    _give(world, "alt@example.org", "lead")
    monkeypatch.setattr(mail, "SMTP_HOST", "smtp.example.org")
    assert welcome.main(["catch-up"]) == 0
    assert "Probelauf: 1 Person" in capsys.readouterr().out
    assert world.sent == []
    assert welcome.main(["catch-up", "--send"]) == 0
    assert len(world.sent) == 1
    assert welcome.main([]) == 2
    monkeypatch.setattr(mail, "SMTP_HOST", "")
    assert welcome.main(["catch-up", "--send"]) == 1


def test_build_without_tenant_is_neutral():
    subject, text, html, images = welcome.build(None, [("Wehrführer/in", "Beispiel")], "https://example.org")
    assert subject == welcome.SUBJECT and images == []
    assert "https://example.org" in text and "Beispiel" in html


def test_new_tenant_sends_welcome_to_first_lead(make_client, monkeypatch):
    sent = []
    monkeypatch.setattr(mail, "send", lambda to, subject, text, html, **kw: sent.append(to))
    make_tenant("wehr-a1", "vg-a")
    client = login(make_client(login=True), "admin@example.org")       # Superadmin
    monkeypatch.setattr(mail, "SMTP_HOST", "smtp.example.org")
    response = client.post("/api/super/tenants", json={"name": "Neue Wehr", "vg": "vg-a", "email": "erste@example.org"})
    assert response.status_code == 200
    assert sent == ["erste@example.org"]
