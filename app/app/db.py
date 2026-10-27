"""SQLite connection management and schema initialisation."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from flask import current_app, g

SCHEMA_PATH = Path(__file__).with_name("schema.sql")

# Drop order matters because of foreign keys (children first).
_DROP_STATEMENTS = [
    "DROP TABLE IF EXISTS request_status_history",
    "DROP TABLE IF EXISTS help_requests",
    "DROP TABLE IF EXISTS resources",
    "DROP TABLE IF EXISTS shelters",
    "DROP TABLE IF EXISTS users",
]


def get_db():
    """Return this request's SQLite connection, creating it if needed."""
    if "db" not in g:
        conn = sqlite3.connect(current_app.config["DATABASE"])
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        g.db = conn
    return g.db


def close_db(exception=None):
    """Close the connection at the end of the request/app context."""
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


@contextmanager
def transaction():
    """Commit if the block succeeds, roll back and re-raise if it fails."""
    conn = get_db()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def init_db(reset=False):
    """Create all tables. With reset=True, drop them first (destroys data)."""
    conn = get_db()
    if reset:
        for statement in _DROP_STATEMENTS:
            conn.execute(statement)
        conn.commit()
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()


def init_app(app):
    app.teardown_appcontext(close_db)
