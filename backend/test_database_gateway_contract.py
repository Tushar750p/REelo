"""Focused SQL compatibility checks for the PostgreSQL gateway."""
from database_gateway import _PGConnection


def test_parameter_markers_are_converted():
    assert _PGConnection._sql("SELECT * FROM users WHERE id=?") == "SELECT * FROM users WHERE id=%s"


def test_sqlite_max_expression_maps_to_greatest():
    sql = _PGConnection._sql("UPDATE videos SET likes=MAX(likes, ?) WHERE id=?")
    assert "GREATEST(likes, %s)" in sql


def test_pragma_table_info_maps_to_information_schema():
    sql = _PGConnection._sql("PRAGMA table_info(users)")
    assert "information_schema.columns" in sql
    assert "table_name='users'" in sql


def test_add_column_is_idempotent_on_postgres():
    sql = _PGConnection._sql("ALTER TABLE users ADD COLUMN bio TEXT")
    assert sql == "ALTER TABLE users ADD COLUMN IF NOT EXISTS bio TEXT"
