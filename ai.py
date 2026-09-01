"""Everything that talks to the language model.

Two operations: generate the question schema and generate the form's metadata.
Both ask for JSON and parse it; if the model returns something invalid, the
question generation retries with the error fed back to it.
"""

import json
import logging
import re

from openai import OpenAI

import config
import form_builder
import prompts
import questions

logger = logging.getLogger(__name__)

client = OpenAI(api_key=config.OPENAI_API_KEY)

MAX_ATTEMPTS = 2


class GenerationError(Exception):
    """The model could not produce a valid form."""


def _ask_json(system_prompt, user_prompt, temperature=0.2, max_tokens=None):
    """Ask the model for JSON and return it parsed.

    Extracts the first JSON object from the answer, in case the model wraps it
    in prose or a markdown fence despite the instructions.
    """
    extra = {"max_tokens": max_tokens} if max_tokens else {}

    response = client.chat.completions.create(
        model=config.OPENAI_MODEL,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        **extra,
    )

    text = response.choices[0].message.content.strip()

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise GenerationError("The model did not return a JSON object")

    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as e:
        raise GenerationError("The model returned invalid JSON: " + str(e))


def generate_questions(user_request, question_count, is_quiz=False):
    """Generate the list of questions, ready for the Forms API.

    When a question fails validation, it retries by handing the error back to
    the model so it can correct itself. Raises GenerationError once the
    attempts run out.
    """
    prompt = prompts.build_form_prompt(user_request, question_count, is_quiz)
    last_error = None

    for attempt in range(MAX_ATTEMPTS):
        try:
            raw = _ask_json(prompts.SYSTEM_PROMPT, prompt)

            items = [
                form_builder.process(question, index, is_quiz)
                for index, question in enumerate(raw.get("questions", []))
            ]

            if not items:
                raise GenerationError("The model returned a form with no questions")

            return items

        except Exception as e:
            last_error = e
            logger.warning(
                "Attempt %s/%s failed: %s", attempt + 1, MAX_ATTEMPTS, e
            )
            prompt += (
                "\n\nIMPORTANT: your previous output was invalid.\nError:\n"
                + str(e) + "\n\nFix it and return ONLY valid JSON.\n"
            )

    raise GenerationError("Could not generate a valid form") from last_error


def generate_metadata(user_request):
    """Generate title, description and file name in ONE call.

    The metadata is cosmetic: a form with a plain title beats losing all the
    work, so any error falls back to the text the user typed.
    """
    fallback = user_request.strip().splitlines()[0][:80] or "Form"

    try:
        raw = _ask_json(
            prompts.SYSTEM_PROMPT_METADATA,
            prompts.build_metadata_prompt(user_request),
            temperature=0.4,
            max_tokens=200,
        )
    except Exception as e:
        logger.warning("Metadata failed, falling back to the user's text: %s", e)
        return {"title": fallback, "description": "", "document_title": fallback}

    title = _clean(raw.get("title")) or fallback

    return {
        "title": title[:80],
        "description": _clean(raw.get("description"))[:150],
        "document_title": (_clean(raw.get("documentTitle")) or title)[:80],
    }


def _clean(value):
    """Normalise a metadata field: flatten whitespace and drop stray quotes.

    The title, description and file name are displayed text too, and the API
    rejects newlines in any of them.
    """
    if not isinstance(value, str):
        return ""

    return questions.collapse_whitespace(value.strip().strip('"'))
