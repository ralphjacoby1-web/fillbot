"""Form creation against a stubbed Google API.

No network: the Google client is replaced by a stub that records the calls it
receives, which is enough to check the request shapes and the rollback.
"""

import pytest

import google_forms


class FakeRequest:
    def __init__(self, result=None, fails=False):
        self._result = result or {}
        self._fails = fails

    def execute(self):
        if self._fails:
            raise RuntimeError("Google said no")
        return self._result


class FakeForms:
    """Stands in for service.forms()."""

    def __init__(self, recorder, fail_on_batch=False):
        self.recorder = recorder
        self.fail_on_batch = fail_on_batch

    def create(self, body):
        self.recorder["created"] = body
        return FakeRequest({"formId": "form-123"})

    def batchUpdate(self, formId, body):
        self.recorder.setdefault("batches", []).append(body)
        return FakeRequest(fails=self.fail_on_batch)

    def get(self, formId):
        return FakeRequest({"responderUri": "https://forms.gle/abc"})


class FakeDriveFiles:
    def __init__(self, recorder):
        self.recorder = recorder

    def delete(self, fileId):
        self.recorder["deleted"] = fileId
        return FakeRequest()


@pytest.fixture
def google(monkeypatch):
    """Replaces googleapiclient's build() and returns the call recorder."""
    recorder = {"fail_on_batch": False}

    def fake_build(service_name, version, credentials=None):
        if service_name == "drive":
            drive = type("Drive", (), {"files": lambda self: FakeDriveFiles(recorder)})()
            return drive

        forms = FakeForms(recorder, fail_on_batch=recorder["fail_on_batch"])
        return type("Service", (), {"forms": lambda self: forms})()

    monkeypatch.setattr(google_forms, "build", fake_build)
    return recorder


METADATA = {"title": "Feedback", "description": "How did we do?",
            "document_title": "Feedback"}
ITEMS = [{"createItem": {"item": {"title": "Your name"}, "location": {"index": 0}}}]


# --- the happy path ---------------------------------------------------------

def test_the_form_is_created_with_its_titles(google):
    google_forms.create_form("creds", METADATA, ITEMS)

    assert google["created"]["info"]["title"] == "Feedback"
    assert google["created"]["info"]["documentTitle"] == "Feedback"


def test_the_description_goes_in_a_separate_update(google):
    """The API refuses a description on create, so it needs its own call."""
    google_forms.create_form("creds", METADATA, ITEMS)

    described = [b for b in google["batches"]
                 if "updateFormInfo" in b["requests"][0]]

    assert described[0]["requests"][0]["updateFormInfo"]["updateMask"] == "description"


def test_an_empty_description_is_skipped(google):
    google_forms.create_form("creds", dict(METADATA, description=""), ITEMS)

    assert not any("updateFormInfo" in b["requests"][0] for b in google["batches"])


def test_quiz_settings_travel_with_the_questions(google):
    """Grading is rejected while the form is not marked as a quiz, so both have
    to arrive in the same batch."""
    google_forms.create_form("creds", METADATA, ITEMS, is_quiz=True)

    batch = [b for b in google["batches"]
             if "updateSettings" in b["requests"][0]][0]

    assert batch["requests"][0]["updateSettings"]["settings"]["quizSettings"]["isQuiz"]
    assert batch["requests"][1] == ITEMS[0]


def test_questions_go_out_without_quiz_settings_for_a_plain_form(google):
    google_forms.create_form("creds", METADATA, ITEMS, is_quiz=False)

    items_batch = google["batches"][-1]

    assert items_batch["requests"] == ITEMS


def test_both_urls_come_back(google):
    result = google_forms.create_form("creds", METADATA, ITEMS)

    assert result["edit_url"] == "https://docs.google.com/forms/d/form-123/edit"
    assert result["share_url"] == "https://forms.gle/abc"


# --- rollback ---------------------------------------------------------------

def test_a_rejected_batch_discards_the_half_built_form(google):
    """Regression: Google answered 400 "Displayed text cannot contain newlines"
    after the form existed, leaving an empty form in the user's Drive."""
    google["fail_on_batch"] = True

    with pytest.raises(RuntimeError):
        google_forms.create_form("creds", METADATA, ITEMS)

    assert google["deleted"] == "form-123"


def test_the_original_error_survives_the_rollback(google):
    """The caller must see why it failed, not whatever the cleanup did."""
    google["fail_on_batch"] = True

    with pytest.raises(RuntimeError, match="Google said no"):
        google_forms.create_form("creds", METADATA, ITEMS)


def test_nothing_is_deleted_when_everything_works(google):
    google_forms.create_form("creds", METADATA, ITEMS)

    assert "deleted" not in google
