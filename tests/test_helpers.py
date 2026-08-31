"""Usage limits.

These are what stop a public deployment from running up an API bill, so the
edges matter: a wrong comparison here either blocks paying users or lets the
limit be bypassed.
"""

import time

import pytest

import config
import helpers


def user(email="someone@example.com", forms_created=0, last_form_at=0):
    """A stand-in for a database row. Rows are read by key, like a dict."""
    return {"email": email, "forms_created": forms_created,
            "last_form_at": last_form_at}


@pytest.fixture
def limits(monkeypatch):
    """Small, predictable limits so the assertions read clearly."""
    monkeypatch.setattr(config, "MAX_FORMS", 3)
    monkeypatch.setattr(config, "RATE_LIMIT_SECONDS", 60)
    monkeypatch.setattr(config, "DEV_EMAIL", "dev@example.com")


# --- unlimited access -------------------------------------------------------

def test_the_dev_account_is_unlimited(limits):
    assert helpers.has_unlimited_access(user(email="dev@example.com")) is True


def test_everyone_else_is_limited(limits):
    """Regression: is_dev used to return True for every address, which made
    the whole limit system inert."""
    assert helpers.has_unlimited_access(user(email="someone@example.com")) is False


def test_no_user_is_not_unlimited(limits):
    assert helpers.has_unlimited_access(None) is False


def test_an_empty_dev_email_grants_nobody_access(monkeypatch):
    """The default is empty, so a fresh clone must not hand out free access."""
    monkeypatch.setattr(config, "DEV_EMAIL", "")

    assert helpers.has_unlimited_access(user(email="")) is False


# --- remaining forms --------------------------------------------------------

def test_a_fresh_user_has_the_full_quota(limits):
    assert helpers.remaining_forms(user()) == 3


def test_the_quota_goes_down_with_use(limits):
    assert helpers.remaining_forms(user(forms_created=2)) == 1


def test_the_quota_never_goes_negative(limits):
    assert helpers.remaining_forms(user(forms_created=99)) == 0


def test_unlimited_users_report_none(limits):
    """None is what the template renders as "Unlimited"."""
    assert helpers.remaining_forms(user(email="dev@example.com")) is None


# --- cooldown and the combined check ----------------------------------------

def test_a_fresh_user_may_create_a_form(limits):
    assert helpers.check_can_create_form(user()) is None


def test_a_user_out_of_quota_is_blocked(limits):
    reason = helpers.check_can_create_form(user(forms_created=3))

    assert reason is not None
    assert "3" in reason


def test_a_user_inside_the_cooldown_is_blocked(limits):
    reason = helpers.check_can_create_form(user(last_form_at=time.time() - 10))

    assert reason is not None
    assert "wait" in reason.lower()


def test_the_cooldown_expires(limits):
    assert helpers.check_can_create_form(user(last_form_at=time.time() - 120)) is None


def test_the_dev_account_skips_quota_and_cooldown(limits):
    exhausted_and_recent = user(email="dev@example.com", forms_created=99,
                                last_form_at=time.time())

    assert helpers.check_can_create_form(exhausted_and_recent) is None


def test_the_block_reason_is_shown_to_the_user(limits):
    """The reason is returned as text precisely so it can be displayed."""
    reason = helpers.check_can_create_form(user(forms_created=3))

    assert isinstance(reason, str) and reason.strip()


# --- summary handed to the templates ----------------------------------------

def test_the_summary_marks_unlimited_users(limits):
    summary = helpers.usage_summary(user(email="dev@example.com"))

    assert summary["unlimited"] is True


def test_the_summary_carries_the_numbers(limits):
    summary = helpers.usage_summary(user(forms_created=1))

    assert summary == {"unlimited": False, "remaining": 2, "max": 3}
