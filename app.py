import logging
import os
import secrets

from flask import (Flask, jsonify, redirect, render_template, request,
                   session, url_for)

import ai
import config
import db
import google_auth
import google_forms
from helpers import (check_can_create_form, current_user, error_page,
                     login_required, usage_summary)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Fail at startup when configuration is missing, rather than returning opaque
# errors on the first request.
config.validate()

app = Flask(__name__)
app.secret_key = config.SECRET_KEY

app.config.update(
    # The cookie carries only the user's id, but it is still what identifies
    # the session, so it is kept away from JavaScript and from other sites.
    SESSION_COOKIE_HTTPONLY=True,
    # Lax still allows the OAuth callback, which arrives as a top-level GET.
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=config.SESSION_COOKIE_SECURE,
)

# Creates the database the first time. Idempotent.
db.init_db()

# Animated use-case strips on the landing page. They live here and not in the
# template to avoid repeating the same tag 32 times.
USE_CASE_ROWS = [
    ["Customer Feedback", "Event Registration", "Product Surveys",
     "Team Onboarding", "Client Support", "Bug Reporting",
     "Feature Requests", "User Testing"],
    ["Data Collection", "Market Research", "Employee Surveys",
     "User Feedback", "Customer Insights", "Trend Analysis",
     "Competitor Review", "Audience Segmentation"],
    ["Lead Generation", "Customer Onboarding", "Internal Feedback",
     "Training Registration", "Process Optimization", "Workflow Automation",
     "Team Collaboration", "Project Planning"],
    ["Survey Analysis", "Market Trends", "Event Feedback", "Product Testing",
     "Customer Retention", "A/B Testing", "Content Evaluation",
     "Brand Monitoring"],
]


@app.after_request
def after_request(response):
    """Ensure responses aren't cached."""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.context_processor
def inject_user():
    """Make the current user available to every template.

    Saves passing it by hand on each render_template just to draw the
    Login/Logout button in the nav.
    """
    return {"user": current_user()}


@app.route("/")
def index():
    """Public landing page."""
    return render_template("index.html", use_case_rows=USE_CASE_ROWS)


@app.route("/generate")
@login_required
def generate():
    """Main screen: describe the form and generate it."""
    return render_template(
        "generate.html",
        usage=usage_summary(current_user()),
        max_prompt_length=config.MAX_PROMPT_LENGTH,
    )


@app.route("/login")
def login():
    """Start the Google OAuth flow."""
    flow = google_auth.build_flow(url_for("callback", _external=True))

    # The state protects against CSRF: it is kept in the session and compared
    # on the way back, confirming this callback belongs to this browser.
    state = secrets.token_urlsafe(32)
    session["oauth_state"] = state

    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
        state=state,
    )

    return redirect(auth_url)


@app.route("/logout")
def logout():
    """Log the user out."""
    session.clear()
    return redirect("/")


@app.route("/callback")
def callback():
    """Back from Google: exchange the code and open the session."""
    if request.args.get("error"):
        return error_page("You need to grant access to create forms.", 403)

    expected_state = session.pop("oauth_state", None)
    if not expected_state or request.args.get("state") != expected_state:
        return error_page("That login link expired. Please try again.", 400)

    code = request.args.get("code")
    if not code:
        return error_page("Google did not return an authorization code.", 400)

    try:
        flow = google_auth.build_flow(url_for("callback", _external=True))
        flow.fetch_token(code=code)
        credentials = flow.credentials
    except Exception as e:
        logger.error("Code exchange failed: %s", e, exc_info=True)
        return error_page("Could not complete the Google login.", 502)

    email = google_auth.fetch_email(credentials)
    if not email:
        return error_page("Could not read your Google account email.", 502)

    session["user_id"] = db.create_or_update_user(
        email, credentials.token, credentials.refresh_token
    )
    logger.info("Logged in: %s", email)

    return redirect("/generate")


@app.route("/create-form", methods=["POST"])
@login_required
def create_form():
    """Generate the form and return its URLs.

    Answers JSON instead of rendering: generating a form takes tens of seconds
    and the page needs to show a spinner meanwhile.
    """
    user = current_user()
    data = request.get_json(silent=True) or {}

    prompt = (data.get("prompt") or "").strip()
    if not prompt:
        return jsonify({"error": "Describe the form you want."}), 400

    prompt = prompt[:config.MAX_PROMPT_LENGTH]
    is_quiz = bool(data.get("is_quiz"))

    try:
        question_count = int(data.get("question_count", 5))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid number of questions."}), 400

    question_count = max(2, min(question_count, 10))

    blocked = check_can_create_form(user)
    if blocked:
        return jsonify({"error": blocked}), 429

    credentials = google_auth.credentials_for(user)
    if not credentials:
        session.clear()
        return jsonify({"error": "Your session expired. Please log in again."}), 401

    try:
        # All the model's work happens BEFORE touching Google: if generation
        # fails, the user is not left with an empty form sitting in their
        # Drive.
        metadata = ai.generate_metadata(prompt)
        items = ai.generate_questions(prompt, question_count, is_quiz)

        form = google_forms.create_form(credentials, metadata, items, is_quiz)

    except ai.GenerationError as e:
        logger.warning("Generation failed for %s: %s", user["email"], e)
        return jsonify({
            "error": "Could not build a valid form from that description. "
                     "Try rephrasing it."
        }), 422

    except Exception as e:
        logger.error("Error creating the form: %s", e, exc_info=True)
        return jsonify({"error": "Unexpected error creating the form."}), 500

    db.record_form_created(user["id"])
    logger.info("Form %s created for %s", form["id"], user["email"])

    return jsonify({
        "edit_url": form["edit_url"],
        "share_url": form["share_url"],
        "usage": usage_summary(current_user()),
    })


@app.errorhandler(404)
def not_found(e):
    return error_page("We could not find that page.", 404)


if __name__ == "__main__":
    # Inside a container the app must listen on 0.0.0.0, otherwise it only
    # accepts connections from within the container itself and the published
    # port reaches nothing. Running directly on your machine it stays on
    # localhost, which is the safer default.
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", 5000)),
        # Off unless FLASK_DEBUG says otherwise: the debugger is a remote shell
        # for anyone who can reach the port.
        debug=config.DEBUG,
    )
