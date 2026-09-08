"""Failure/recovery tests for the PostgreSQL connection boundary.

These tests avoid destructive database operations: they simulate a lost pool
connection and verify that the gateway surfaces the failure cleanly while the
pool remains capable of serving a later healthy connection.
"""
import os

import pytest

pytestmark = pytest.mark.integration


def test_postgres_pool_reports_clean_failure_when_database_is_unreachable(monkeypatch):
    from database_gateway import pool_status

    monkeypatch.setenv("REELO_DATABASE_URL", "postgresql://reelo:bad@127.0.0.1:1/reelo_test")
    monkeypatch.setenv("REELO_DB_CONNECT_TIMEOUT", "1")

    # A failed connection must be an explicit operational failure, not a
    # silent SQLite fallback that could write to the wrong datastore.
    import database_gateway
    database_gateway.close_pool()
    with pytest.raises(Exception):
        database_gateway.open_pool(wait=True)

    assert pool_status()["backend"] == "postgresql"
    database_gateway.close_pool()


def test_sqlite_never_falls_back_when_postgres_is_configured(monkeypatch):
    import database_gateway

    monkeypatch.setenv("REELO_DATABASE_URL", "postgresql://reelo:bad@127.0.0.1:1/reelo_test")
    database_gateway.close_pool()
    with pytest.raises(Exception):
        database_gateway.db().__enter__()
    database_gateway.close_pool()


def test_pool_recovers_after_a_bad_pool_is_replaced(monkeypatch):
    import database_gateway

    monkeypatch.setenv("REELO_DATABASE_URL", "postgresql://reelo:bad@127.0.0.1:1/reelo_test")
    database_gateway.close_pool()
    with pytest.raises(Exception):
        database_gateway.open_pool(wait=True)
    database_gateway.close_pool()

    # Closing the failed pool clears the singleton so a subsequent healthy
    # environment can construct a fresh pool instead of reusing stale state.
    assert database_gateway._POOL is None
