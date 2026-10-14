import sqlite3
from pathlib import Path
from config import Settings

settings = Settings()


def get_connection():
    """Get a connection to the SQLite database."""
    DB_PATH = Path(settings.DB_SQLITE_PATH)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=10000;")
    return conn

