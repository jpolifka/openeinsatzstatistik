"""Skalierung: Wehr-Daten werden nicht für jeden Stammdatensatz erneut geladen."""
import time
from app import db, records, store, tenancy
from conftest import make_tenant


def test_protocol_loads_each_tenant_once_for_many_records(data_dir, monkeypatch):
    vg, _ = make_tenant("wehr-a")
    make_tenant("wehr-b")
    for slug in ("wehr-a", "wehr-b"):
        with db.connection(tenancy.tenant_path(slug)) as con:
            for number in range(1, 501):
                store.create_incident(con, {"number": number, "started_at": "2025-03-12T10:00:00",
                                           "bks_record_id": str(number)}, "pdf")
    original, calls = store.load_incidents, []
    def counted(con, *args, **kwargs):
        calls.append(1)
        return original(con, *args, **kwargs)
    monkeypatch.setattr(store, "load_incidents", counted)
    started = time.perf_counter()
    with tenancy.central() as con:
        result = records.protocol(con, vg, 2025, tenancy.vg_tenants(vg))
    print(f"Prüfprotokoll: 500 Stammdatensätze, 1000 Beteiligungen in {time.perf_counter() - started:.3f} s")
    assert len(result) == 500
    assert len(calls) == 2
