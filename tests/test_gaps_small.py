# -*- coding: utf-8 -*-
"""Kleine Lücken: Migrationsabbruch, Übernahme mit Restdateien, Outbox-Codierung, Blattnamen, Größenlimit, Kennzahlen."""
import asyncio
import datetime as dt

import pytest

from app import db, domain, excel_export, import_queue, legacy, metrics, request_limits
from conftest import CFG, make_incident, vehicle
from test_legacy import old_install  # noqa: F401  (Fixture old_install)


def test_failed_migration_step_rolls_back_and_keeps_earlier_steps():
    con = db.connect(":memory:")

    def first(c):
        c.execute("CREATE TABLE kept (x)")

    def second(c):
        c.execute("CREATE TABLE lost (x)")
        raise RuntimeError("Schritt kaputt")

    with pytest.raises(RuntimeError, match="Schritt kaputt"):
        db.migrate(con, [first, second])
    assert con.execute("PRAGMA user_version").fetchone()[0] == 1
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert "kept" in tables and "lost" not in tables
    with pytest.raises(RuntimeError, match="neuer"):
        db.migrate(con, [])
    con.close()


def test_migration_removes_leftover_wal_files(old_install):  # noqa: F811
    for name in ("einsaetze.db-wal", "einsaetze.db-shm"):
        (old_install / name).write_bytes(b"")
    legacy.migrate_single_install(str(old_install))
    assert not (old_install / "einsaetze.db-wal").exists() and not (old_install / "einsaetze.db-shm").exists()


def test_fee_schedule_is_seeded_only_once(data_dir):
    from app import tenancy
    with tenancy.central() as con:
        vg_id = tenancy.create_vg(con, "vg-s", "VG S")
        legacy.seed_fee_schedule(con, vg_id)
        legacy.seed_fee_schedule(con, vg_id)
        assert con.execute("SELECT COUNT(*) FROM fee_schedule WHERE vg_id = ?", (vg_id,)).fetchone()[0] == 1


def test_outbox_encodes_times_and_rejects_other_types():
    assert import_queue._encode(dt.time(10, 5))["__report_time__"] == "time"
    assert import_queue._decode({"a": 1}) == {"a": 1}
    with pytest.raises(TypeError, match="Nicht serialisierbar"):
        import_queue._encode(object())


def test_sheet_titles_are_clean_and_unique():
    taken = set()
    first = excel_export._sheet_title("Einsätze", "FF [Muster]: Nord/Süd?", taken)
    second = excel_export._sheet_title("Einsätze", "FF [Muster]: Nord/Süd?", taken)
    assert first == "Einsätze FF Muster NordSüd" and second == f"{first[:28]} 2"
    assert len(excel_export._sheet_title("X", "y" * 80, taken)) <= 31


def test_size_limit_ignores_non_request_messages_and_rejects_oversized_bodies():
    sent, calls = [], []

    async def app(scope, receive, send):
        calls.append(await receive())
        calls.append(await receive())

    middleware = request_limits.RequestSizeLimit(app, max_bytes=5)
    messages = iter([{"type": "http.disconnect"}, {"type": "http.request", "body": b"x"}])

    async def receive():
        return next(messages)

    async def send(message):
        sent.append(message)

    asyncio.run(middleware({"type": "http", "path": "/x", "headers": []}, receive, send))
    assert [m["type"] for m in calls] == ["http.disconnect", "http.request"]

    async def too_much():
        return {"type": "http.request", "body": b"x" * 10}

    async def reading(scope, receive, send):
        await receive()

    from starlette.exceptions import HTTPException
    with pytest.raises(HTTPException) as refused:
        asyncio.run(request_limits.RequestSizeLimit(reading, max_bytes=5)(
            {"type": "http", "path": "/x", "headers": []}, too_much, send))
    assert refused.value.status_code == 413


def test_call_sign_text_without_number_or_unknown():
    assert domain.call_sign_text("kein Funkrufname") == ""
    text = domain.call_sign_text("FL NR#.BHÖ 02/45")
    assert text and "Nr." not in text


def test_respiratory_ignores_people_without_minutes():
    incident = make_incident(vehicles={"02/45": vehicle("02/45", 3, "10:03:00", "10:08:00")},
                             people=[{"id": 1, "name": "Muster, Max", "agt": 1, "agt_min": None},
                                     {"id": 2, "name": "Beispiel, Erika", "agt": 1, "agt_min": 0}])
    result = metrics.respiratory(metrics.evaluate([incident], CFG))
    assert result["persons"] == 2 and result["minutes"] == 0
    assert result["average_minutes"] == 0.0 and result["longest_minutes"] is None


def test_fire_watch_before_fire_out_adds_no_hours():
    watch_before = make_incident(keyword="B", subcode="2", ended_at="2025-03-12T11:00:00",
                                 fire_out_at="2025-03-12T10:50:00", fire_watch_until="2025-03-12T10:40:00",
                                 vehicles={"02/45": vehicle("02/45", 3, "10:03:00", "10:08:00")})
    no_base = make_incident(id=2, number=2, keyword="B", subcode="2", ended_at=None, fire_out_at=None,
                            fire_watch_until="2025-03-12T12:00:00",
                            vehicles={"02/45": vehicle("02/45", 3, "10:03:00", "10:08:00")})
    result = metrics.fire_course(metrics.evaluate([watch_before, no_base], CFG))
    assert result["fire_watches"] == 2 and result["fire_watch_hours"] is None and result["fire_watch_valid"] == 0
