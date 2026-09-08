"""Unit coverage for PostgreSQL pool lifecycle without requiring a live server."""
import importlib


def test_sqlite_gateway_unchanged(monkeypatch):
    monkeypatch.delenv("REELO_DATABASE_URL", raising=False)
    import database_gateway
    importlib.reload(database_gateway)

    with database_gateway.db() as conn:
        row = conn.execute("SELECT 1 AS value").fetchone()
        assert row["value"] == 1
    assert database_gateway.pool_status() == {"enabled": False, "backend": "sqlite"}


def test_pool_status_uses_safe_metrics(monkeypatch):
    monkeypatch.setenv("REELO_DATABASE_URL", "postgresql://reelo:test@localhost/reelo")
    import database_gateway
    importlib.reload(database_gateway)

    class FakePool:
        min_size = 1
        max_size = 10
        closed = False

        def get_stats(self):
            return {"pool_size": 4, "pool_available": 3, "requests_waiting": 1}

    monkeypatch.setattr(database_gateway, "_POOL", FakePool())
    status = database_gateway.pool_status()
    assert status["backend"] == "postgresql"
    assert status["pool_size"] == 4
    assert status["pool_available"] == 3
    assert status["requests_waiting"] == 1
    assert "password" not in status


def test_pooled_connection_returns_connection_to_pool():
    import database_gateway

    class FakeContext:
        def __init__(self):
            self.entered = False
            self.exited = False

        def __enter__(self):
            self.entered = True
            return self

        def __exit__(self, exc_type, exc, tb):
            self.exited = True

        def cursor(self):
            return self

        def execute(self, sql, params=()):
            self.description = [("value",)]
            self.rowcount = 1
            self._row = (1,)

        def fetchone(self):
            return self._row

    class FakePool:
        def __init__(self):
            self.context = FakeContext()

        def connection(self, timeout=None):
            assert timeout == 5.0
            return self.context

    pool = FakePool()
    conn = database_gateway._PGConnection(pool)
    with conn as wrapped:
        row = wrapped.execute("SELECT 1").fetchone()
        assert row["value"] == 1
    assert pool.context.entered
    assert pool.context.exited
    assert conn.conn is None
