# -*- coding: utf-8 -*-
"""Schutzheader auf allen Antworten, eigene Richtlinien einzelner Antworten bleiben erhalten."""
from fastapi.testclient import TestClient

from app import main


def test_headers_on_public_and_redirect_and_error_responses():
    client = TestClient(main.app)
    for path in ("/health", "/login", "/static/app.js", "/nicht-vorhanden"):
        r = client.get(path, follow_redirects=False)
        for name in ("Content-Security-Policy", "X-Content-Type-Options", "X-Frame-Options", "Referrer-Policy"):
            assert name in r.headers, (path, name)
        assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
        assert "'unsafe-inline'" not in r.headers["Content-Security-Policy"].split("script-src")[1].split(";")[0]


def test_own_policy_is_kept():
    @main.app.get("/_own_csp")
    def own():
        from fastapi import Response
        return Response("x", headers={"Content-Security-Policy": "default-src 'none'; sandbox"})
    r = TestClient(main.app).get("/_own_csp", follow_redirects=False)
    assert r.headers["Content-Security-Policy"] == "default-src 'none'; sandbox"


def test_api_docs_are_off():
    client = TestClient(main.app)
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path, follow_redirects=False).status_code in (303, 404), path
