"""Translation of a validated question into a Google Forms API item.

These assert the exact shape Google expects; a wrong key here produces a 400
from the API rather than a visible bug locally.
"""

import pytest

import form_builder
import questions


def build(raw, index=0):
    """Normalise, validate and build in one step, as the generator does."""
    return form_builder.process(raw, index, is_quiz=False)


def question_body(item):
    """Dig out the question payload from the createItem wrapper."""
    return item["createItem"]["item"]["questionItem"]["question"]


# --- structure --------------------------------------------------------------

def test_item_is_wrapped_with_its_position():
    item = build({"type": "short_text", "label": "Name"}, index=3)

    assert item["createItem"]["location"] == {"index": 3}
    assert item["createItem"]["item"]["title"] == "Name"


def test_required_flag_is_carried_through():
    item = build({"type": "short_text", "label": "Name", "required": True})

    assert question_body(item)["required"] is True


def test_description_is_included_when_present():
    item = build({"type": "short_text", "label": "Name",
                  "description": "As it appears on your ID"})

    assert item["createItem"]["item"]["description"] == "As it appears on your ID"


def test_description_is_omitted_when_absent():
    item = build({"type": "short_text", "label": "Name"})

    assert "description" not in item["createItem"]["item"]


# --- one test per type ------------------------------------------------------

def test_short_text_is_not_a_paragraph():
    item = build({"type": "short_text", "label": "Name"})

    assert question_body(item)["textQuestion"] == {"paragraph": False}


def test_paragraph_is_a_paragraph():
    item = build({"type": "paragraph", "label": "Tell us more"})

    assert question_body(item)["textQuestion"] == {"paragraph": True}


@pytest.mark.parametrize("question_type,api_type", [
    ("multiple_choice", "RADIO"),
    ("checkboxes", "CHECKBOX"),
    ("dropdown", "DROP_DOWN"),
])
def test_choice_types_map_to_their_api_names(question_type, api_type):
    item = build({"type": question_type, "label": "Pick", "options": ["A", "B"]})
    choice = question_body(item)["choiceQuestion"]

    assert choice["type"] == api_type
    assert choice["options"] == [{"value": "A"}, {"value": "B"}]


def test_shuffle_is_applied_when_set():
    item = build({"type": "multiple_choice", "label": "Pick",
                  "options": ["A", "B"], "shuffle": True})

    assert question_body(item)["choiceQuestion"]["shuffle"] is True


def test_shuffle_is_omitted_when_absent():
    item = build({"type": "multiple_choice", "label": "Pick", "options": ["A", "B"]})

    assert "shuffle" not in question_body(item)["choiceQuestion"]


def test_linear_scale_carries_its_bounds_and_labels():
    item = build({"type": "linear_scale", "label": "Rate it", "minValue": 1,
                  "maxValue": 5, "startLabel": "Bad", "endLabel": "Great"})
    scale = question_body(item)["scaleQuestion"]

    assert scale == {"low": 1, "high": 5, "lowLabel": "Bad", "highLabel": "Great"}


def test_linear_scale_omits_labels_when_absent():
    item = build({"type": "linear_scale", "label": "Rate it",
                  "minValue": 1, "maxValue": 5})

    assert question_body(item)["scaleQuestion"] == {"low": 1, "high": 5}


def test_date_and_time_take_empty_bodies():
    assert question_body(build({"type": "date", "label": "When"}))["dateQuestion"] == {}
    assert question_body(build({"type": "time", "label": "What time"}))["timeQuestion"] == {}


def test_unknown_type_raises():
    with pytest.raises(ValueError):
        form_builder.build({"type": "hologram", "label": "?"}, 0)


# --- grading (exam mode) ----------------------------------------------------

def build_quiz(raw, index=0):
    return form_builder.process(raw, index, is_quiz=True)


def test_multiple_choice_grading_lists_the_correct_answer():
    item = build_quiz({
        "type": "multiple_choice", "label": "Capital?",
        "options": ["Paris", "London"], "correctAnswer": "Paris", "pointValue": 3,
    })
    grading = question_body(item)["grading"]

    assert grading["pointValue"] == 3
    assert grading["correctAnswers"] == {"answers": [{"value": "Paris"}]}


def test_checkbox_grading_lists_every_correct_answer():
    item = build_quiz({
        "type": "checkboxes", "label": "Primes?",
        "options": ["2", "3", "4"], "correctAnswers": ["2", "3"], "pointValue": 2,
    })
    grading = question_body(item)["grading"]

    assert grading["correctAnswers"]["answers"] == [{"value": "2"}, {"value": "3"}]


def test_missing_point_value_defaults_to_one():
    """Regression: the model may mark a correct answer and omit the score.

    q.get("pointValue", 1) does not help, because normalize() always creates
    the key. The default never applied and Google rejects a grading block whose
    pointValue is null, failing the whole form.
    """
    item = build_quiz({
        "type": "multiple_choice", "label": "Capital?",
        "options": ["Paris", "London"], "correctAnswer": "Paris",
    })
    grading = question_body(item)["grading"]

    assert grading["pointValue"] == form_builder.DEFAULT_POINT_VALUE
    assert grading["pointValue"] is not None


def test_missing_point_value_defaults_for_checkboxes_too():
    item = build_quiz({
        "type": "checkboxes", "label": "Primes?",
        "options": ["2", "3", "4"], "correctAnswers": ["2"],
    })

    assert question_body(item)["grading"]["pointValue"] == 1


# --- grading is stripped outside exam mode ----------------------------------

def test_grading_is_dropped_when_not_a_quiz():
    """The model returns answers even when it was not asked for them."""
    item = build({
        "type": "multiple_choice", "label": "Favourite colour?",
        "options": ["Red", "Blue"], "correctAnswer": "Red", "pointValue": 5,
    })

    assert "grading" not in question_body(item)


def test_answers_outside_the_options_are_tolerated_outside_exam_mode():
    """Stripping happens before validation, so a stray answer is not an error
    on a form that was never going to be graded."""
    item = build({
        "type": "multiple_choice", "label": "Favourite colour?",
        "options": ["Red", "Blue"], "correctAnswer": "Green",
    })

    assert "grading" not in question_body(item)


def test_invalid_question_raises_through_process():
    with pytest.raises(questions.ValidationError):
        build({"type": "multiple_choice", "label": "Pick", "options": ["Only one"]})
