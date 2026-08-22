"""_execute_write must retry "unable to open database file" (SQLITE_CANTOPEN)
the same way it already retries "database is locked" / "database is busy".

Observed in production (2026-08-22): CANTOPEN surfaced intermittently under
the nono sandbox and cleared on its own within seconds, aborting Slack turns
via session_persistence_failed in the meantime. Not reproducible under
synthetic concurrent-load testing, so the underlying trigger is unconfirmed —
this applies the same defensive retry the code already uses for a sibling
process transiently holding the write lock.
"""

import sqlite3
from unittest.mock import MagicMock

import pytest

from hermes_state import SessionDB


@pytest.fixture()
def db(tmp_path):
    db_path = tmp_path / "test_state.db"
    session_db = SessionDB(db_path=db_path)
    yield session_db
    try:
        session_db.close()
    except Exception:
        pass


def test_execute_write_retries_cantopen_then_succeeds(db):
    """A transient CANTOPEN is retried like a lock and the write still lands."""
    real_conn = db._conn
    attempts = {"n": 0}

    def flaky_execute(sql, *args, **kwargs):
        if sql.strip().upper() == "BEGIN IMMEDIATE":
            attempts["n"] += 1
            if attempts["n"] <= 2:
                raise sqlite3.OperationalError("unable to open database file")
        return real_conn.execute(sql, *args, **kwargs)

    mock_conn = MagicMock()
    mock_conn.execute.side_effect = flaky_execute
    mock_conn.commit.side_effect = real_conn.commit
    mock_conn.rollback.side_effect = real_conn.rollback
    db._conn = mock_conn

    result = db._execute_write(lambda conn: conn.execute("SELECT 1").fetchone())

    assert attempts["n"] == 3
    assert tuple(result) == (1,)


def test_execute_write_exhausts_patience_on_persistent_cantopen(db):
    """A CANTOPEN that never clears still raises after the patience budget,
    with the same enriched "database is locked" message used for real lock
    contention — not a raw, confusing CANTOPEN string."""
    mock_conn = MagicMock()
    mock_conn.execute.side_effect = sqlite3.OperationalError(
        "unable to open database file"
    )
    db._conn = mock_conn

    with pytest.raises(sqlite3.OperationalError) as exc_info:
        db._execute_write(lambda conn: conn.execute("SELECT 1"), patience_s=0.05)

    assert "database is locked" in str(exc_info.value)
    assert "healthy" in str(exc_info.value)


def test_execute_write_still_propagates_unrelated_operational_errors(db):
    """A genuinely different OperationalError (e.g. malformed SQL) must not
    be swallowed into the lock-retry path."""
    mock_conn = MagicMock()
    mock_conn.execute.side_effect = sqlite3.OperationalError("no such table: bogus")
    db._conn = mock_conn

    with pytest.raises(sqlite3.OperationalError) as exc_info:
        db._execute_write(lambda conn: conn.execute("SELECT * FROM bogus"))

    assert "no such table" in str(exc_info.value)
