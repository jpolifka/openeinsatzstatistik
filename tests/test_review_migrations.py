import sqlite3

import pytest

from app import db


def test_newer_database_schema_is_rejected():
    with sqlite3.connect(":memory:") as con:
        con.execute(f"PRAGMA user_version = {len(db.TENANT_MIGRATIONS) + 1}")
        with pytest.raises(RuntimeError, match="neuer"):
            db.migrate(con)


@pytest.mark.parametrize("steps", [db.TENANT_MIGRATIONS, db.CENTRAL_MIGRATIONS])
def test_every_historical_schema_migrates_and_restart_is_idempotent(steps):
    for version in range(len(steps) + 1):
        con = db.connect(":memory:")
        try:
            db.migrate(con, steps[:version])
            db.migrate(con, steps)
            db.migrate(con, steps)
            assert con.execute("PRAGMA user_version").fetchone()[0] == len(steps)
        finally:
            con.close()
