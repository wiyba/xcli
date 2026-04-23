import os
import sqlite3

from config import DB_PATH

HOSTS = ("relay", "london", "stockholm")

SCHEMA = """
CREATE TABLE IF NOT EXISTS usage (
    user TEXT PRIMARY KEY,
    "limit" INTEGER NOT NULL DEFAULT 0,
    relay INTEGER NOT NULL DEFAULT 0,
    london INTEGER NOT NULL DEFAULT 0,
    stockholm INTEGER NOT NULL DEFAULT 0,
    relay_enabled INTEGER NOT NULL DEFAULT 1
);
"""


def connect():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.executescript(SCHEMA)
    cols = {r["name"] for r in c.execute("PRAGMA table_info(usage)")}
    if "relay_enabled" not in cols:
        c.execute(
            "ALTER TABLE usage ADD COLUMN relay_enabled INTEGER NOT NULL DEFAULT 1"
        )
        c.commit()
    return c


def ensure(conn, names):
    conn.executemany(
        "INSERT OR IGNORE INTO usage(user) VALUES (?)",
        [(n,) for n in names],
    )
    conn.commit()


def row(conn, name):
    r = conn.execute("SELECT * FROM usage WHERE user = ?", (name,)).fetchone()
    return dict(r) if r else None


def all_rows(conn):
    return [dict(r) for r in conn.execute("SELECT * FROM usage ORDER BY user")]


def topup(conn, name, add_bytes):
    conn.execute(
        'UPDATE usage SET "limit" = "limit" + ? WHERE user = ?',
        (add_bytes, name),
    )
    conn.commit()


def set_host_bytes(conn, name, host, bytes_val):
    if host not in HOSTS:
        raise ValueError(host)
    conn.execute(
        f'UPDATE usage SET "{host}" = ? WHERE user = ?',
        (bytes_val, name),
    )
    conn.commit()


def set_relay_enabled(conn, name, enabled):
    conn.execute(
        "UPDATE usage SET relay_enabled = ? WHERE user = ?",
        (1 if enabled else 0, name),
    )
    conn.commit()
