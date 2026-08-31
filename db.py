"""Access to the local SQLite database.

A single .db file next to the code. No server to run and no cloud credentials
needed: it is created from schema.sql the first time the app starts.
"""

import os
import sqlite3
import time

import config


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

def connect():
    """Open a connection to the database.

    Rows come back as sqlite3.Row, which are accessed by column name
    (row["email"]) rather than by index.
    """
    conn = sqlite3.connect(config.DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def execute(sql, params=()):
    """Run a write (INSERT/UPDATE/DELETE) and commit the transaction.

    Returns the id of the inserted row, which is useful after an INSERT.
    """
    with connect() as conn:
        cursor = conn.execute(sql, params)
        return cursor.lastrowid


def query_one(sql, params=()):
    """Return the first row of the result, or None if there is none."""
    with connect() as conn:
        return conn.execute(sql, params).fetchone()


def query_all(sql, params=()):
    """Return every row of the result as a list."""
    with connect() as conn:
        return conn.execute(sql, params).fetchall()


def init_db():
    """Create the tables if they do not exist.

    Idempotent: safe to call on every startup.
    """
    # The directory may not exist yet on a fresh clone; SQLite will not
    # create it on its own.
    os.makedirs(os.path.dirname(config.DATABASE), exist_ok=True)

    with open("schema.sql", encoding="utf-8") as f:
        with connect() as conn:
            conn.executescript(f.read())


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def get_user(user_id):
    """Return the user with this id, or None if there is none."""
    return query_one("SELECT * FROM users WHERE id = ?", (user_id,))


def get_user_by_email(email):
    """Return the user with this email, or None if there is none."""
    return query_one("SELECT * FROM users WHERE email = ?", (email,))


def create_or_update_user(email, access_token, refresh_token):
    """Register the user if new and store their Google credentials.

    Returns the user's id, which is what gets stored in the session.

    Google only sends a refresh token the first time the user grants consent,
    so an empty one keeps whatever was already saved.
    """
    user = get_user_by_email(email)

    if user is None:
        return execute(
            "INSERT INTO users (email, access_token, refresh_token)"
            " VALUES (?, ?, ?)",
            (email, access_token, refresh_token),
        )

    execute(
        "UPDATE users SET access_token = ?, refresh_token = COALESCE(?, refresh_token)"
        " WHERE id = ?",
        (access_token, refresh_token, user["id"]),
    )
    return user["id"]


def save_access_token(user_id, access_token):
    """Store the access token that was just refreshed."""
    execute(
        "UPDATE users SET access_token = ? WHERE id = ?",
        (access_token, user_id),
    )


def record_form_created(user_id):
    """Bump the counter and stamp the time of the latest form."""
    execute(
        "UPDATE users SET forms_created = forms_created + 1, last_form_at = ?"
        " WHERE id = ?",
        (time.time(), user_id),
    )
