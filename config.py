"""Configuration read from the environment.

This module holds no business logic: it only reads variables, applies sensible
defaults, and fails early when something required is missing.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

# Absolute path so the configuration does not depend on the directory the
# process was started from.
load_dotenv(BASE_DIR / ".env")


def flag(name):
    """Read a boolean switch from the environment.

    Anything other than an explicit yes is false, so a typo turns a security
    switch off rather than on.
    """
    return os.environ.get(name, "").lower() in ("1", "true", "yes")


class ConfigError(RuntimeError):
    """Raised at startup when a required variable is missing."""


# --- Secrets ----------------------------------------------------------------

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OAUTH_CLIENT_ID = os.environ.get("OAUTH_CLIENT_ID")
OAUTH_CLIENT_SECRET = os.environ.get("OAUTH_CLIENT_SECRET")

# Signs the Flask session cookie. If it changes, every session is dropped.
SECRET_KEY = os.environ.get("SECRET_KEY")


# --- Database ---------------------------------------------------------------

# Local SQLite. A single file under data/: no server, no cloud, no credentials.
# Created automatically the first time the app starts. It lives in its own
# directory because that is what the Docker container mounts, so both ways of
# running the app share one database.
DATABASE = os.environ.get("DATABASE", str(BASE_DIR / "data" / "fillbot.db"))


# --- Security -----------------------------------------------------------

# Werkzeug's debugger lets anyone who can reach the port run arbitrary code
# through the browser. It stays off unless explicitly asked for, so deploying
# this by accident cannot hand out a shell.
DEBUG = flag("FLASK_DEBUG")

# Send the session cookie only over HTTPS. Off by default because local
# development runs on http://localhost; turn it on wherever you deploy.
SESSION_COOKIE_SECURE = flag("SESSION_COOKIE_SECURE")


# --- Model ------------------------------------------------------------------

OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")


# --- Usage limits -----------------------------------------------------------

# These exist to cap API spending when the app is publicly reachable. They have
# nothing to do with monetisation: running it with your own key, just raise
# MAX_FORMS.

# Account with unlimited access. Empty by default so no personal data ends up
# in the source.
DEV_EMAIL = os.environ.get("DEV_EMAIL", "").strip().lower()

MAX_FORMS = int(os.environ.get("MAX_FORMS", "5"))
RATE_LIMIT_SECONDS = int(os.environ.get("RATE_LIMIT_SECONDS", "60"))

MAX_PROMPT_LENGTH = 300


# --- OAuth ------------------------------------------------------------------

# drive.file rather than drive: enough to create and edit the forms FillBot
# generates, without granting access to the rest of the user's Drive.
SCOPES = [
    "https://www.googleapis.com/auth/forms.body",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]

REQUIRED = (
    ("OPENAI_API_KEY", OPENAI_API_KEY),
    ("OAUTH_CLIENT_ID", OAUTH_CLIENT_ID),
    ("OAUTH_CLIENT_SECRET", OAUTH_CLIENT_SECRET),
    ("SECRET_KEY", SECRET_KEY),
)


def validate():
    """Check that every required environment variable is present.

    Fails at startup instead of returning opaque errors on the first request.
    """
    missing = [name for name, value in REQUIRED if not value]

    if missing:
        raise ConfigError(
            "Missing environment variables: " + ", ".join(missing) + ". "
            "Copy .env.example to .env and fill it in."
        )
