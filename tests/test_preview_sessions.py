"""Vorschauen: Besitz, Abbruch, Ablauf und Speichergrenzen ohne echte Daten."""
import pytest
from fastapi import HTTPException
from app.preview_sessions import PreviewSessions


def test_cancel_only_own_and_idempotent():
    sessions = PreviewSessions()
    token = sessions.add([({"filename": "test.pdf"}, "wehr-a")], "owner")
    sessions.cancel(token, "other")
    assert sessions.get(token, "test.pdf", "owner")[1] == "wehr-a"
    sessions.cancel(token, "owner")
    sessions.cancel(token, "owner")
    assert sessions.get(token, "test.pdf", "owner") == (None, None)


def test_claim_failure_restores_but_success_consumes():
    sessions = PreviewSessions()
    token = sessions.add([({"filename": "test.pdf"}, "wehr-a")], None)
    with pytest.raises(ValueError):
        with sessions.claim(token, "test.pdf", None):
            raise ValueError("Fehler")
    with sessions.claim(token, "test.pdf", None) as (report, slug):
        assert report["filename"] == "test.pdf" and slug == "wehr-a"
        assert sessions.get(token, "test.pdf", None) == (None, None)
    assert not sessions._sessions


def test_preview_limits_and_expiry(monkeypatch):
    sessions = PreviewSessions()
    monkeypatch.setattr(sessions, "MAX_PER_OWNER", 1)
    token = sessions.add([({"filename": "test.pdf"}, "wehr-a")], None)
    with pytest.raises(HTTPException) as error:
        sessions.add([({"filename": "other.pdf"}, "wehr-a")], None)
    assert error.value.status_code == 429
    sessions._sessions[token]["time"] = 0
    assert sessions.get(token, "test.pdf", None) == (None, None)
    monkeypatch.setattr(sessions, "MAX_BYTES", 1)
    with pytest.raises(HTTPException) as error:
        sessions.add([({"filename": "test.pdf"}, "wehr-a")], None)
    assert error.value.status_code == 413


def test_cancel_during_failed_claim_does_not_restore():
    sessions = PreviewSessions()
    token = sessions.add([({"filename": "test.pdf"}, "wehr-a")], None)
    with pytest.raises(ValueError):
        with sessions.claim(token, "test.pdf", None):
            sessions.cancel(token, None)
            raise ValueError("Fehler nach Abbruch")
    assert not sessions._sessions
