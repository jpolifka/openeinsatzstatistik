# -*- coding: utf-8 -*-
import dataclasses

import pytest
from fastapi.testclient import TestClient

from app import auth, db, main, tenancy
from app.api import common as api_common
from app.preview_sessions import PreviewSessions
from app.legacy import rheinbrohl_config

# Fachkonfiguration für die Tests: die Werte der ersten Wehr (keine personenbezogenen Daten)
CFG = rheinbrohl_config()


@pytest.fixture
def con():
    """Leere, migrierte In-Memory-Datenbank."""
    connection = db.connect(":memory:")
    db.migrate(connection)
    yield connection
    connection.close()


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """Leerer Datenordner mit migrierter Zentral-DB; Anmeldung aus (jeder ist Superadmin)."""
    monkeypatch.setattr(db, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(api_common, "previews", PreviewSessions())
    from app import parser_worker
    # API-Tests ersetzen die Dateileser gezielt; echte Prozessgrenzen separat prüfen.
    monkeypatch.setattr(parser_worker, "read", parser_worker.read_local)
    monkeypatch.setattr(tenancy, "ADMIN_EMAILS", set())
    monkeypatch.delenv("AUTH_EMAILS", raising=False)
    tenancy.setup()
    return tmp_path


def make_tenant(slug, vg="vg-a", cfg=CFG, name=None, dpa="signed"):
    """Wehr (und bei Bedarf ihre VG) anlegen -> (vg_id, tenant_id). Eine neue VG bekommt den AVV-Status
    dpa (Standard: liegt vor, damit die Wehr nutzbar ist; None = ausstehend wie in Betrieb)."""
    with tenancy.central() as con:
        row = con.execute("SELECT id FROM vg WHERE slug = ?", (vg,)).fetchone()
        vg_id = row["id"] if row else tenancy.create_vg(con, vg, f"VG {vg}")
        if not row and dpa:
            con.execute("INSERT INTO dpa (vg_id, status) VALUES (?, ?)", (vg_id, dpa))
        name = name or f"Wehr {slug}"
        tenant_id = tenancy.create_tenant(con, slug, name, vg_id, dataclasses.replace(cfg, name=name))
    return vg_id, tenant_id


def grant(email, role, scope_id):
    with tenancy.central() as con:
        tenancy.grant(con, email, role, scope_id)


@pytest.fixture
def make_client(data_dir, monkeypatch):
    """TestClient-Fabrik; mit login=True ist die Anmeldung an (Superadmin admin@example.org)."""
    clients = []

    def factory(login=False):
        if login:
            monkeypatch.setattr(tenancy, "ADMIN_EMAILS", {"admin@example.org"})
            monkeypatch.setattr(auth, "BASE_URL", "http://testserver")
            monkeypatch.setattr(auth, "_key", None)
        client = TestClient(main.app)
        client.__enter__()
        clients.append(client)
        return client

    yield factory
    for client in clients:
        client.__exit__(None, None, None)


def login(client, email):
    """Sitzungs-Cookie setzen, ohne Mail."""
    client.cookies.set(auth.COOKIE, auth._sign("session", email, 600))
    return client


def make_incident(**overrides):
    """Einsatz in der Form von store.load_incidents – mit erfundenen Werten."""
    incident = {
        "id": 1, "year": 2025, "number": 1, "started_at": "2025-03-12T10:00:00", "ended_at": "2025-03-12T11:00:00",
        "keyword": "B2", "subcode": "08", "description": "Zimmerbrand / Musterweg 1", "place": "Rheinbrohl",
        "unit_leader": "M. Muster", "station_staff": 0, "weekend_or_holiday": 0, "source": "pdf",
        "filename": "01-25_B2_Test.pdf", "warnings": [], "vehicles": {}, "people": [],
    }
    incident.update(overrides)
    return incident


def vehicle(call_sign, crew, departed=None, arrived=None, name=None):
    return {"call_sign": call_sign, "name": name, "crew": crew, "departed": departed, "arrived": arrived}
