"""Shared utilities for the routes: decorators, session and usage limits."""

import time
from functools import wraps

from flask import jsonify, redirect, render_template, request, session

import config
import db


def login_required(f):
    """Require an active session to reach a route.

    Without one, the user is sent to /login, which starts the Google OAuth
    flow.

    Routes that answer JSON get a 401 instead of the redirect: a fetch() would
    follow the redirect all the way to Google and then fail to parse HTML,
    hiding the real reason (the session expired).
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            if request.is_json:
                return jsonify({"error": "Your session expired. Please log in again."}), 401
            return redirect("/login")
        return f(*args, **kwargs)

    return decorated_function


def current_user():
    """Return the logged-in user's row, or None if there is no session.

    If the session points at a user that no longer exists (because the .db was
    deleted, say), it clears the session rather than leaving the user in an
    inconsistent state.
    """
    user_id = session.get("user_id")

    if user_id is None:
        return None

    user = db.get_user(user_id)

    if user is None:
        session.clear()

    return user


def error_page(message, code=400):
    """Render a simple error page.

    Returns the (html, status) tuple Flask expects to answer with a status
    other than 200.
    """
    return render_template("error.html", message=message, code=code), code


# ---------------------------------------------------------------------------
# Usage limits
# ---------------------------------------------------------------------------
# These cap API spending when the app is publicly reachable, not to sell
# anything. Running it with your own key, raise MAX_FORMS.

def has_unlimited_access(user):
    """True when the limits do not apply to this user."""
    if not user or not config.DEV_EMAIL:
        return False

    return user["email"] == config.DEV_EMAIL


def remaining_forms(user):
    """How many forms the user can still create.

    Returns None for unlimited users, which the template renders as
    "Unlimited".
    """
    if has_unlimited_access(user):
        return None

    return max(0, config.MAX_FORMS - user["forms_created"])


def seconds_until_next_form(user):
    """Seconds left before the user may create another form."""
    if has_unlimited_access(user):
        return 0

    elapsed = time.time() - user["last_form_at"]
    return max(0, int(config.RATE_LIMIT_SECONDS - elapsed))


def check_can_create_form(user):
    """Check whether the user may create a form right now.

    Returns None when they may, or a message explaining why not. Returning the
    reason as text means it can be shown to the user directly.
    """
    if has_unlimited_access(user):
        return None

    if remaining_forms(user) <= 0:
        return (
            "You have used all " + str(config.MAX_FORMS) + " of your forms. "
            "Run FillBot with your own API key to lift the limit."
        )

    wait = seconds_until_next_form(user)
    if wait > 0:
        return "Please wait " + str(wait) + " seconds before creating another form."

    return None


def usage_summary(user):
    """Build the usage summary consumed by the templates and the frontend."""
    remaining = remaining_forms(user)

    return {
        "unlimited": remaining is None,
        "remaining": remaining,
        "max": config.MAX_FORMS,
    }
