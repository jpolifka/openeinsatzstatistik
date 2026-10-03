"""Lebenszyklus des Wiederholungsdienstes ohne Schlafpausen und echte Daten."""
import asyncio
from app import import_queue


def test_worker_retries_after_failure_and_stops(monkeypatch):
    calls = []
    async def scenario():
        stop = asyncio.Event()
        def retry(tenant, callback):
            calls.append(tenant)
            if len(calls) == 1:
                raise RuntimeError("vorübergehender Fehler")
            asyncio_loop.call_soon_threadsafe(stop.set)
        monkeypatch.setattr(import_queue, "retry", retry)
        asyncio_loop = asyncio.get_running_loop()
        await asyncio.wait_for(import_queue.run_worker(stop, lambda: ["synthetisch"], None, interval=0.001), 2)
    asyncio.run(scenario())
    assert calls == ["synthetisch", "synthetisch"]
