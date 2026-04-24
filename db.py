import sqlite3


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user    TEXT PRIMARY KEY,
    uuid    TEXT NOT NULL,
    admin   INTEGER NOT NULL DEFAULT 0,
    quota   INTEGER NOT NULL DEFAULT 0,
    blocked INTEGER NOT NULL DEFAULT 0
);
"""


def connect(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def sync(conn, users):
    conn.executemany(
        "INSERT INTO users(user, uuid, admin) VALUES (?, ?, ?) "
        "ON CONFLICT(user) DO UPDATE SET uuid=excluded.uuid, admin=excluded.admin",
        [(u["user"], u["uuid"], int(u["admin"])) for u in users],
    )
    names = [u["user"] for u in users]
    if names:
        qmarks = ",".join("?" * len(names))
        conn.execute(f"DELETE FROM users WHERE user NOT IN ({qmarks})", names)
    else:
        conn.execute("DELETE FROM users")
    conn.commit()


def all(conn):
    return [dict(r) for r in conn.execute("SELECT * FROM users ORDER BY user")]


def set_quota(conn, user, value):
    conn.execute("UPDATE users SET quota = ? WHERE user = ?", (value, user))
    conn.commit()


def set_blocked(conn, user, value):
    conn.execute("UPDATE users SET blocked = ? WHERE user = ?", (value, user))
    conn.commit()
