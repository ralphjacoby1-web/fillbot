-- Schema for FillBot's local database.
-- Applied on every startup; creating tables is idempotent (see db.init_db).

CREATE TABLE IF NOT EXISTS users (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    email          TEXT    NOT NULL UNIQUE,

    -- Google credentials. They live here and not in the browser: the session
    -- cookie only carries the user's id.
    access_token   TEXT,
    refresh_token  TEXT,

    -- Usage counters.
    forms_created  INTEGER NOT NULL DEFAULT 0,
    last_form_at   REAL    NOT NULL DEFAULT 0,

    created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
