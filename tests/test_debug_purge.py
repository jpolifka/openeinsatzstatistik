# -*- coding: utf-8 -*-
"""Abgelegte Debug-Berichte verschwinden auch ohne weiteren Upload und ohne gesetztes KEEP_UPLOADS."""
import asyncio
import os

from app import db, importing


def test_purge_without_upload_or_flag(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DATA_DIR", str(tmp_path))
    monkeypatch.delenv("KEEP_UPLOADS", raising=False)
    folder = tmp_path / "debug-reports"
    folder.mkdir()
    old, new = folder / "alt.pdf", folder / "neu.pdf"
    old.write_bytes(b"x")
    new.write_bytes(b"x")
    os.utime(old, (1, 1))
    importing.purge_debug_reports()
    assert not old.exists() and new.exists()


def test_purge_runs_at_start_and_stops(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DATA_DIR", str(tmp_path))
    folder = tmp_path / "debug-reports"
    folder.mkdir()
    old = folder / "alt.pdf"
    old.write_bytes(b"x")
    os.utime(old, (1, 1))

    async def run():
        stop = asyncio.Event()
        task = asyncio.create_task(importing.purge_debug_reports_regularly(stop, interval=3600))
        await asyncio.sleep(0.2)
        stop.set()
        await asyncio.wait_for(task, 2)

    asyncio.run(run())
    assert not old.exists()
