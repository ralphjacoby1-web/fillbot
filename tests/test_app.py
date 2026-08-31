"""Routes and access control.

None of these reach OpenAI or Google: they cover the guards that run before any
external call, which is where a mistake silently exposes an endpoint.
"""

import config
import db
import helpers


# --- public pages -----------------------------------------------------------

def test_the_landing_page_is_public(client):
    response = client.get("/")

    assert response.status_code == 200
    assert b"Transform ideas into" in response.data


def test_an_unknown_page_returns_404(client):
    assert client.get("/does-not-exist").status_code == 404


def test_responses_are_not_cached(client):
    """Pages reflect session state, so a cached copy would show the wrong nav."""
    assert "no-store" in client.get("/").headers["Cache-Control"]


# --- access control ---------------------------------------------------------

def test_generate_requires_a_session(client):
    response = client.get("/generate")

    assert response.status_code == 302
    assert response.headers["Location"] == "/login"


def test_generate_is_reachable_once_logged_in(logged_in):
    client, _ = logged_in

    assert client.get("/generate").status_code == 200


def test_create_form_answers_401_json_without_a_session(client):
    """A fetch() must get JSON, not a redirect it would follow to Google and
    then fail to parse."""
    response = client.post("/create-form", json={"prompt": "a survey"})

    assert response.status_code == 401
    assert response.get_json()["error"]


def test_login_redirects_to_google(client):
    response = client.get("/login")

    assert response.status_code == 302
    assert "accounts.google.com" in response.headers["Location"]


def test_logout_clears_the_session(logged_in):
    client, _ = logged_in
    client.get("/logout")

    assert client.get("/generate").status_code == 302


# --- OAuth callback ---------------------------------------------------------

def test_the_callback_rejects_a_forged_state(client):
    """The state is what proves the callback belongs to this browser."""
    response = client.get("/callback?code=abc&state=forged")

    assert response.status_code == 400


def test_the_callback_rejects_a_missing_state(client):
    assert client.get("/callback?code=abc").status_code == 400


def test_the_callback_handles_a_denied_consent(client):
    response = client.get("/callback?error=access_denied")

    assert response.status_code == 403
    assert b"grant access" in response.data


def test_the_state_is_single_use(client):
    """Popping it means a replayed callback cannot reuse the same state."""
    client.get("/login")

    with client.session_transaction() as session:
        state = session["oauth_state"]

    client.get("/callback?code=abc&state=" + state)

    with client.session_transaction() as session:
        assert "oauth_state" not in session


# --- create-form input handling ---------------------------------------------

def test_a_missing_prompt_is_rejected(logged_in):
    client, _ = logged_in
    response = client.post("/create-form", json={})

    assert response.status_code == 400


def test_a_blank_prompt_is_rejected(logged_in):
    client, _ = logged_in

    assert client.post("/create-form", json={"prompt": "   "}).status_code == 400


def test_a_non_numeric_question_count_is_rejected(logged_in):
    client, _ = logged_in
    response = client.post("/create-form",
                           json={"prompt": "a survey", "question_count": "many"})

    assert response.status_code == 400


def test_a_body_that_is_not_json_is_rejected(logged_in):
    client, _ = logged_in
    response = client.post("/create-form", data="not json",
                           content_type="text/plain")

    assert response.status_code in (400, 401)


def test_the_quota_blocks_before_any_external_call(logged_in, monkeypatch):
    """429 must come back without spending a token: the check runs first."""
    client, user_id = logged_in
    monkeypatch.setattr(config, "MAX_FORMS", 1)
    db.record_form_created(user_id)

    response = client.post("/create-form", json={"prompt": "a survey"})

    assert response.status_code == 429
    assert response.get_json()["error"]


# --- usage counters ---------------------------------------------------------

def test_the_page_shows_the_remaining_quota(logged_in, monkeypatch):
    client, _ = logged_in
    monkeypatch.setattr(config, "MAX_FORMS", 5)

    assert b"Forms remaining: 5/5" in client.get("/generate").data


def test_the_counter_goes_down_after_a_form(logged_in, monkeypatch):
    client, user_id = logged_in
    monkeypatch.setattr(config, "MAX_FORMS", 5)
    db.record_form_created(user_id)

    assert b"Forms remaining: 4/5" in client.get("/generate").data


def test_the_nav_reflects_the_session(client, logged_in):
    logged_client, _ = logged_in

    assert b"Log out" in logged_client.get("/generate").data
