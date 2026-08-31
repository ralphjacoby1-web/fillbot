"""Translates a validated question into the shape the Google Forms API expects.

Each create_* returns a "createItem" request, ready to be sent inside a
batchUpdate. The nested structure is Google's, not ours.
"""

import questions

# Score used when the model marks a correct answer but forgets the pointValue.
# q.get("pointValue", 1) will not do: normalize() always creates the key, so the
# default would never apply and Google rejects a grading block whose pointValue
# is null.
DEFAULT_POINT_VALUE = 1


def build(q, index):
    """Build the Forms API item for one question.

    Takes the question already normalised and validated, plus its position in
    the form. Raises ValueError when the type has no builder, something
    validate() should have caught earlier.
    """
    builders = {
        "short_text": _short_text,
        "paragraph": _paragraph,
        "multiple_choice": _multiple_choice,
        "checkboxes": _checkboxes,
        "dropdown": _dropdown,
        "linear_scale": _linear_scale,
        "date": _date,
        "time": _time,
    }

    builder = builders.get(q["type"])

    if builder is None:
        raise ValueError("Unknown question type: " + str(q["type"]))

    return _wrap(builder(q), index)


def _wrap(item, index):
    """Wrap the item in the createItem request, with its position."""
    return {"createItem": {"item": item, "location": {"index": index}}}


def _base_item(q, question_body):
    """Build the part every question shares: title and description."""
    item = {
        "title": q["label"],
        "questionItem": {
            "question": dict({"required": q["required"]}, **question_body)
        },
    }

    if q["description"] is not None:
        item["description"] = q["description"]

    return item


def _grading(q, answers):
    """Build the grading block for exam questions."""
    return {
        "pointValue": q.get("pointValue") or DEFAULT_POINT_VALUE,
        "correctAnswers": {"answers": [{"value": answer} for answer in answers]},
    }


def _choice(q, choice_type):
    """Build a choiceQuestion (radio, checkbox or dropdown)."""
    body = {
        "choiceQuestion": {
            "type": choice_type,
            "options": [{"value": option} for option in q["options"]],
        }
    }

    if q["shuffle"] is not None:
        body["choiceQuestion"]["shuffle"] = q["shuffle"]

    return body


def _short_text(q):
    return _base_item(q, {"textQuestion": {"paragraph": False}})


def _paragraph(q):
    return _base_item(q, {"textQuestion": {"paragraph": True}})


def _dropdown(q):
    return _base_item(q, _choice(q, "DROP_DOWN"))


def _multiple_choice(q):
    item = _base_item(q, _choice(q, "RADIO"))

    if q.get("correctAnswer"):
        item["questionItem"]["question"]["grading"] = _grading(q, [q["correctAnswer"]])

    return item


def _checkboxes(q):
    item = _base_item(q, _choice(q, "CHECKBOX"))

    if q.get("correctAnswers"):
        item["questionItem"]["question"]["grading"] = _grading(q, q["correctAnswers"])

    return item


def _linear_scale(q):
    scale = {"low": q["minValue"], "high": q["maxValue"]}

    if q["startLabel"] is not None:
        scale["lowLabel"] = q["startLabel"]

    if q["endLabel"] is not None:
        scale["highLabel"] = q["endLabel"]

    return _base_item(q, {"scaleQuestion": scale})


def _date(q):
    return _base_item(q, {"dateQuestion": {}})


def _time(q):
    return _base_item(q, {"timeQuestion": {}})


def process(raw, index, is_quiz=False):
    """Normalise, validate and build one raw question from the model.

    This is the only entry point the generator needs: it chains the three steps
    and lets ValidationError bubble up when the question is unusable.
    """
    q = questions.normalize(raw)

    # Cleared BEFORE validating, so the grading rules do not reject a question
    # that is not an exam question in the first place.
    if not is_quiz:
        questions.strip_grading(q)

    questions.validate(q)

    return build(q, index)
