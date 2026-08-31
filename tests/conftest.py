"""Shared test setup.

The environment has to be arranged BEFORE importing the app: config.py reads
os.environ at import time and app.py calls config.validate() at import time.
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

# The modules under test live in the project root, one level up.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Fake credentials so config.validate() passes. No test reaches the network:
# the OpenAI client is built at import but never called.
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")
os.environ.setdefault("OAUTH_CLIENT_ID", "test-client-id")
os.environ.setdefault("OAUTH_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

# A throwaway database, so running the tests never touches data/fillbot.db.
os.environ["DATABASE"] = str(Path(tempfile.mkdtemp(prefix="fillbot-test-")) / "test.db")

# Nobody is the dev account unless a test says so.
os.environ["DEV_EMAIL"] = ""


@pytest.fixture
def client():
    """A Flask test client with an empty database."""
    import app as flask_app
    import db

    db.execute("DELETE FROM users")

    flask_app.app.config["TESTING"] = True
    with flask_app.app.test_client() as test_client:
        yield test_client


@pytest.fixture
def logged_in(client):
    """A test client with an active session, plus the user's id."""
    import db

    user_id = db.create_or_update_user("tester@example.com", "token", "refresh")

    with client.session_transaction() as session:
        session["user_id"] = user_id

    return client, user_id
