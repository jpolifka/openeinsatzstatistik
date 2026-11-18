# -*- coding: utf-8 -*-
"""Anmeldemail im Design der Wehr und Anmeldecode als Alternative zum Link."""
import dataclasses
import email as emaillib
import email.policy
import re

import pytest

from app import auth, db, login_mail, mail, tenancy
from conftest import CFG, grant, make_tenant

PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360f8ffff3f0005fe02fea7e6f1d70000000049454e44ae426082")
EMAIL = "m.muster@example.org"


@pytest.fixture
def client(make_client, monkeypatch):
    monkeypatch.setattr(auth, "_last_mail", {})
    monkeypatch.setattr(auth, "_sent", [])         # sonst erschöpfen mehrere Tests die Tagesgrenze je Adresse
    return make_client(login=True)


def _code_from(caplog):
    found = re.findall(r"Code (\d{8})", caplog.text)
    return found[-1] if found else None


# ---------------------------------------------------------------- First Hit
def _created(scope, scope_id, day):
    with tenancy.central() as con:
        con.execute("UPDATE membership SET created = ? WHERE email = ? AND scope = ? AND scope_id = ?",
                    (day, EMAIL, scope, scope_id))


def test_first_hit_prefers_oldest_direct_membership(client):
    _, a = make_tenant("wehr-a")
    _, b = make_tenant("wehr-b2", vg="vg-a")
    grant(EMAIL, "lead", b)
    grant(EMAIL, "lead", a)
    _created("tenant", b, "2024-02-01")
    _created("tenant", a, "2024-01-01")
    assert tenancy.mail_tenant(EMAIL).slug == "wehr-a"


def test_first_hit_skips_inactive_and_falls_back_to_vg(client):
    vg_id, a = make_tenant("wehr-a")
    make_tenant("wehr-b", vg="vg-a")
    grant(EMAIL, "lead", a)
    grant(EMAIL, "vg_stats", vg_id)
    with tenancy.central() as con:
        con.execute("UPDATE tenant SET active = 0 WHERE id = ?", (a,))
    assert tenancy.mail_tenant(EMAIL).slug == "wehr-b"


def test_first_hit_none_for_superadmin_without_membership(client):
    make_tenant("wehr-a")
    assert tenancy.mail_tenant("admin@example.org") is None


# ---------------------------------------------------------------- Mail
def test_mail_uses_tenant_name_color_and_inline_logo(client):
    _, tid = make_tenant("wehr-a", name="FF <Beispiel>")
    tenant = tenancy.vg_tenants(1)[0]
    tenant.config  # Konfiguration laden
    with tenant.connection() as con:
        con.execute("INSERT OR REPLACE INTO asset (name, content_type, data) VALUES ('logo-light', 'image/png', ?)", (PNG,))
    subject, text, body, images = login_mail.build(tenant, "http://x/auth/verify?token=t", "12345678", 15)
    assert "FF <Beispiel>" in subject
    assert "FF &lt;Beispiel&gt;" in body and "<Beispiel>" not in body
    assert "cid:" + login_mail.LOGO_CID in body and images[0][2] == "image/png"
    assert login_mail.DEFAULT_BRAND["brand"] in body.upper()
    assert text.startswith("Dein Anmeldecode: 12345678\n")
    assert body.count("12345678") == 1


def test_mail_uses_own_brand_color(client):
    make_tenant("wehr-a")
    tenant = tenancy.vg_tenants(1)[0]
    with tenant.connection() as con:
        tenancy.save_config(con, dataclasses.replace(tenant.config, colors={"brand": "#1F5FAA"}), tenant.layer)
    tenancy.forget_config("wehr-a")
    body = login_mail.build(tenant, "http://x/l", "12345678", 15)[2]
    assert "#1F5FAA" in body.upper() and "#7C2734" not in body.upper()


def test_mail_without_logo_or_tenant_is_neutral(client):
    subject, text, body, images = login_mail.build(None, "http://x/l", "00000001", 15)
    assert subject == login_mail.SUBJECT and images == [] and "cid:" not in body


def test_oversized_or_non_image_logo_is_skipped(client):
    make_tenant("wehr-a")
    tenant = tenancy.vg_tenants(1)[0]
    with tenant.connection() as con:
        con.execute("INSERT OR REPLACE INTO asset (name, content_type, data) VALUES ('logo-light', 'image/png', ?)",
                    (PNG + b"0" * login_mail.MAX_LOGO_BYTES,))
    assert login_mail._logo(tenant) is None
    with tenant.connection() as con:
        con.execute("UPDATE asset SET data = ? WHERE name = 'logo-light'", (b"<svg/>",))
    assert login_mail._logo(tenant) is None


def test_built_message_has_related_image(client):
    msg = mail.build("a@example.org", "S", "t", "<img src='cid:x'>", images=[("x", PNG, "image/png")])
    raw = emaillib.message_from_bytes(msg.as_bytes(), policy=emaillib.policy.default)
    types = [p.get_content_type() for p in raw.walk()]
    assert "multipart/related" in types and "image/png" in types
    assert raw.get_body(("html",)) is not None and raw.get_body(("plain",)) is not None


def test_sent_mail_contains_code_and_branding(client, monkeypatch):
    _, tid = make_tenant("wehr-a")
    grant(EMAIL, "lead", tid)
    sent = []
    monkeypatch.setattr(mail, "enabled", lambda: True)
    monkeypatch.setattr(mail, "send", lambda *a, **k: sent.append((a, k)))
    client.post("/login", data={"email": EMAIL})
    (to, subject, text, body), kwargs = sent[0]
    assert to == EMAIL and "Wehr wehr-a" in subject
    code = re.search(r"Dein Anmeldecode: (\d{8})", text).group(1)
    assert code in body and "/auth/verify?token=" in text


def test_branding_failure_falls_back_to_neutral_mail(client, monkeypatch):
    _, tid = make_tenant("wehr-a")
    grant(EMAIL, "lead", tid)
    sent = []
    monkeypatch.setattr(mail, "enabled", lambda: True)
    monkeypatch.setattr(mail, "send", lambda *a, **k: sent.append(a))
    real = login_mail.build

    def broken(tenant, *args):
        if tenant:
            raise RuntimeError("kaputt")
        return real(None, *args)
    monkeypatch.setattr(login_mail, "build", broken)
    client.post("/login", data={"email": EMAIL})
    assert sent and sent[0][1] == login_mail.SUBJECT


# ---------------------------------------------------------------- Code
@pytest.fixture
def member(client):
    _, tid = make_tenant("wehr-a")
    grant(EMAIL, "lead", tid)
    return client


def _request(client, caplog, address=EMAIL):
    client.post("/login", data={"email": address})
    return _code_from(caplog)


def test_login_page_offers_code_field_for_any_address(member):
    known = member.post("/login", data={"email": EMAIL}).text
    unknown = member.post("/login", data={"email": "fremd@example.org"}).text
    for page in (known, unknown):
        assert 'autocomplete="one-time-code"' in page and 'inputmode="numeric"' in page
    assert known.replace(EMAIL, "X") == unknown.replace("fremd@example.org", "X")


def test_code_logs_in_once_and_kills_link(member, caplog):
    code = _request(member, caplog)
    token = re.findall(r"token=(\S+)", caplog.text)[-1].split(" ")[0]
    wrong = member.post("/auth/code", data={"email": EMAIL, "code": "00000000" if code != "00000000" else "11111111"})
    assert auth.COOKIE not in wrong.cookies
    ok = member.post("/auth/code", data={"email": EMAIL.upper(), "code": f"{code[:4]} {code[4:]}"}, follow_redirects=False)
    assert ok.status_code == 303 and auth.COOKIE in ok.cookies
    member.cookies.clear()
    assert auth._use_link(token) is None                       # Link ist mit entwertet
    again = member.post("/auth/code", data={"email": EMAIL, "code": code}, follow_redirects=False)
    assert auth.COOKIE not in again.cookies


def test_link_kills_code(member, caplog):
    code = _request(member, caplog)
    token = re.findall(r"token=(\S+)", caplog.text)[-1].split(" ")[0]
    assert auth._use_link(token) == EMAIL
    assert auth._use_code(EMAIL, code) is None


def test_code_locks_after_failed_attempts(member, caplog):
    code = _request(member, caplog)
    bad = "00000000" if code != "00000000" else "11111111"
    for _ in range(auth.CODE_ATTEMPTS):
        assert auth._use_code(EMAIL, bad) is None
    assert auth._use_code(EMAIL, code) is None                  # richtiger Code nach zu vielen Fehlversuchen


def test_hourly_failure_limit(member, caplog):
    for _ in range(auth.CODE_FAILURES_PER_HOUR):
        auth._use_code(EMAIL, "00000000")
    auth._last_mail.clear()
    code = _request(member, caplog)
    assert auth._use_code(EMAIL, code) is None


def test_expired_code_and_unknown_address(member, caplog):
    code = _request(member, caplog)
    with tenancy.central() as con:
        con.execute("UPDATE login_code SET expires = 1")
    assert auth._use_code(EMAIL, code) is None
    assert auth._use_code("fremd@example.org", "12345678") is None


def test_new_request_replaces_old_code(member, caplog):
    first = _request(member, caplog)
    auth._last_mail.clear()
    second = _request(member, caplog)
    if first != second:
        assert auth._use_code(EMAIL, first) is None
    auth._last_mail.clear()
    third = _request(member, caplog)
    assert auth._use_code(EMAIL, third) == EMAIL


def test_code_stored_only_hashed(member, caplog):
    code = _request(member, caplog)
    with tenancy.central() as con:
        row = con.execute("SELECT * FROM login_code").fetchone()
    assert code not in tuple(row)
