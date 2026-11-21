# -*- coding: utf-8 -*-
"""Der Leseprozess bekommt keine Geheimnisse aus der Umgebung."""
import json

from app import parser_worker


class Conn:
    sent = b""

    def send_bytes(self, data):
        Conn.sent = data

    def close(self):
        pass


def test_child_has_no_secrets_in_environment(monkeypatch):
    seen = {}
    for name in ("SECRET_KEY", "SMTP_PASSWORD", "DKIM_KEY_FILE", "ADMIN_EMAILS", "DATA_DIR"):
        monkeypatch.setenv(name, "geheim")
    monkeypatch.setattr(parser_worker, "read_local", lambda kind, path: seen.update(env=dict(parser_worker.os.environ)) or {})
    # Der Test ändert die Umgebung des Testprozesses: monkeypatch stellt sie danach wieder her
    saved = dict(parser_worker.os.environ)
    try:
        parser_worker._child(Conn(), "pdf", "x")
    finally:
        parser_worker.os.environ.update(saved)
    assert json.loads(Conn.sent)["ok"]
    assert not {"SECRET_KEY", "SMTP_PASSWORD", "DKIM_KEY_FILE", "ADMIN_EMAILS", "DATA_DIR"} & set(seen["env"])
