# -*- coding: utf-8 -*-
import pytest

from app import db
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
