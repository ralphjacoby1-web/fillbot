"""Google Forms API client.

Exposes a single high-level operation: create a complete form from the metadata
and the already-built items.
"""

import logging

from googleapiclient.discovery import build

logger = logging.getLogger(__name__)


def create_form(credentials, metadata, items, is_quiz=False):
    """Create the form in the user's Drive and add the questions to it.

    Takes the user's credentials, the metadata (title, description,
    document_title) and the items already shaped for the API.

    Returns a dict with the id and both URLs: the editing one and the public
    one for responding.
    """
    service = build("forms", "v1", credentials=credentials)

    # The API only accepts the title on creation; the description and the
    # questions must go through batchUpdate.
    form = service.forms().create(body={
        "info": {
            "title": metadata["title"],
            "documentTitle": metadata["document_title"],
        }
    }).execute()

    form_id = form["formId"]

    # From here on the form exists in the user's Drive. If Google rejects
    # anything that follows, the half-built form is deleted rather than left
    # behind: the user asked for a form, not for an empty one they have to
    # clean up themselves.
    try:
        if metadata.get("description"):
            _update_description(service, form_id, metadata["description"])

        _add_items(service, form_id, items, is_quiz)
    except Exception:
        _discard(credentials, form_id)
        raise

    return {
        "id": form_id,
        "edit_url": "https://docs.google.com/forms/d/" + form_id + "/edit",
        "share_url": _share_url(service, form_id),
    }


def _discard(credentials, form_id):
    """Delete a form that could not be finished.

    The Forms API has no delete, so it goes through Drive. The drive.file scope
    covers files this app created, which is exactly what this is.

    Best effort: a failure here is logged and swallowed, so it never replaces
    the original error that caused the rollback.
    """
    try:
        drive = build("drive", "v3", credentials=credentials)
        drive.files().delete(fileId=form_id).execute()
        logger.info("Discarded incomplete form %s", form_id)
    except Exception as e:
        logger.warning("Could not discard incomplete form %s: %s", form_id, e)


def _update_description(service, form_id, description):
    """Add the description, which cannot be set when creating the form."""
    service.forms().batchUpdate(formId=form_id, body={
        "requests": [{
            "updateFormInfo": {
                "info": {"description": description},
                "updateMask": "description",
            }
        }]
    }).execute()


def _add_items(service, form_id, items, is_quiz):
    """Turn on quiz mode and add the questions in ONE batchUpdate.

    They have to travel together: Google rejects grading data on a question
    while the form is not marked as a quiz yet.
    """
    requests = []

    if is_quiz:
        requests.append({
            "updateSettings": {
                "settings": {"quizSettings": {"isQuiz": True}},
                "updateMask": "quizSettings.isQuiz",
            }
        })

    requests.extend(items)

    service.forms().batchUpdate(formId=form_id, body={"requests": requests}).execute()


def _share_url(service, form_id):
    """Return the public URL for responding to the form.

    Google assigns the responderUri when the form is created, so it has to be
    read back. If that read fails, the URL is assembled by hand as a fallback.
    """
    try:
        form = service.forms().get(formId=form_id).execute()
        share_url = form.get("responderUri")

        if share_url:
            return share_url

    except Exception as e:
        logger.warning("Could not read the responderUri: %s", e)

    return "https://docs.google.com/forms/d/e/" + form_id + "/viewform"
