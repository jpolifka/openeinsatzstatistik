# -*- coding: utf-8 -*-
import pytest


@pytest.mark.parametrize("path, text", [("/impressum", "Polifka IT-Beratung"), ("/datenschutz", "Auftragsverarbeitung"),
                                        ("/barrierefreiheit", "Barriere melden")])
def test_legal_pages_public(make_client, monkeypatch, path, text):
    monkeypatch.setenv("LEGAL_EMAIL", "kontakt@example.org")
    client = make_client(login=True)
    response = client.get(path)
    assert response.status_code == 200
    assert text in response.text


def test_imprint_has_address_and_placeholder(make_client, monkeypatch):
    monkeypatch.delenv("LEGAL_EMAIL", raising=False)
    client = make_client(login=True)
    text = client.get("/impressum").text
    assert "In der Maar 31" in text and "56598 Rheinbrohl" in text
    assert "[bitte ergänzen]" in text


def test_legal_input_is_escaped(make_client, monkeypatch):
    monkeypatch.setenv("LEGAL_NAME", "<script>x</script>")
    assert "<script>x" not in make_client(login=True).get("/impressum").text


def test_login_page_links_legal(make_client):
    text = make_client(login=True).get("/login").text
    assert 'href="/impressum"' in text and 'href="/datenschutz"' in text
