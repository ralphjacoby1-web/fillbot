"""Validation rules for questions coming out of the model.

Every rule mirrors a constraint the Google Forms API enforces, so a test
failing here means FillBot would have shipped a form Google rejects.
"""

import pytest

import questions
from questions import ValidationError


def valid(**overrides):
    """A minimal valid question, with fields overridden per test."""
    base = {"type": "short_text", "label": "Your name", "required": True}
    base.update(overrides)
    return questions.normalize(base)


# --- normalize --------------------------------------------------------------

def test_normalize_fills_every_key():
    q = questions.normalize({"type": "short_text", "label": "Name"})

    assert q["required"] is False
    assert q["options"] is None
    assert q["correctAnswer"] is None
    assert q["pointValue"] is None


def test_normalize_keeps_provided_values():
    q = questions.normalize({
        "type": "multiple_choice",
        "label": "Colour?",
        "required": True,
        "options": ["Red", "Blue"],
        "shuffle": True,
    })

    assert q["options"] == ["Red", "Blue"]
    assert q["shuffle"] is True


def test_strip_grading_clears_exam_fields():
    q = questions.normalize({
        "type": "multiple_choice",
        "label": "Capital?",
        "options": ["Paris", "London"],
        "correctAnswer": "Paris",
        "pointValue": 5,
    })

    questions.strip_grading(q)

    assert q["correctAnswer"] is None
    assert q["correctAnswers"] is None
    assert q["pointValue"] is None


# --- type and label ---------------------------------------------------------

def test_every_documented_type_validates():
    """Anything listed in QUESTION_TYPES must survive its own example."""
    for name, spec in questions.QUESTION_TYPES.items():
        questions.validate(questions.normalize(spec["example"]))


def test_missing_type_is_rejected():
    with pytest.raises(ValidationError) as e:
        questions.validate(valid(type=None))

    assert e.value.field == "type"


def test_unknown_type_is_rejected():
    with pytest.raises(ValidationError) as e:
        questions.validate(valid(type="file_upload"))

    assert "file_upload" in e.value.message


def test_missing_label_is_rejected():
    with pytest.raises(ValidationError) as e:
        questions.validate(valid(label=None))

    assert e.value.field == "label"


def test_blank_label_is_rejected():
    with pytest.raises(ValidationError):
        questions.validate(valid(label="   "))


# --- options ----------------------------------------------------------------

@pytest.mark.parametrize("question_type", sorted(questions.CHOICE_TYPES))
def test_choice_types_need_two_options(question_type):
    with pytest.raises(ValidationError) as e:
        questions.validate(valid(type=question_type, options=["Only one"]))

    assert e.value.field == "options"


@pytest.mark.parametrize("question_type", sorted(questions.CHOICE_TYPES))
def test_choice_types_accept_two_options(question_type):
    questions.validate(valid(type=question_type, options=["A", "B"]))


def test_blank_options_are_rejected():
    with pytest.raises(ValidationError):
        questions.validate(valid(type="dropdown", options=["A", "   "]))


def test_duplicate_options_are_rejected():
    with pytest.raises(ValidationError) as e:
        questions.validate(valid(type="checkboxes", options=["A", "A", "B"]))

    assert "duplicate" in e.value.message.lower()


# --- linear_scale -----------------------------------------------------------
# The API only accepts low in {0, 1} and high in 2..10.

def scale(minimum, maximum):
    return valid(type="linear_scale", label="Rate it",
                 minValue=minimum, maxValue=maximum)


@pytest.mark.parametrize("bounds", [(0, 2), (1, 5), (0, 10), (1, 10)])
def test_scales_within_the_api_limits_pass(bounds):
    questions.validate(scale(*bounds))


@pytest.mark.parametrize("bounds", [
    (1, 100),   # "rate from 1 to 100": the case that used to reach Google
    (1, 11),    # high above the maximum
    (1, 1),     # high not above low
    (2, 8),     # low outside {0, 1}
    (3, 5),
    (0, 1),     # high below the minimum of 2
])
def test_scales_outside_the_api_limits_are_rejected(bounds):
    with pytest.raises(ValidationError):
        questions.validate(scale(*bounds))


def test_scale_requires_both_bounds():
    with pytest.raises(ValidationError):
        questions.validate(valid(type="linear_scale", minValue=1, maxValue=None))


def test_scale_bounds_must_be_integers():
    with pytest.raises(ValidationError):
        questions.validate(scale(1.0, 5))


# --- grading ----------------------------------------------------------------

def test_correct_answer_must_be_one_of_the_options():
    """Google rejects the whole batch when an answer is not a verbatim option."""
    with pytest.raises(ValidationError) as e:
        questions.validate(valid(
            type="multiple_choice",
            options=["London", "Berlin"],
            correctAnswer="Paris",
        ))

    assert e.value.field == "correctAnswer"


def test_trailing_whitespace_no_longer_breaks_the_answer_match():
    """Normalisation trims both sides, so a stray space is no longer fatal.

    This used to be rejected, wasting a retry on a difference the user would
    never have seen. An answer that genuinely is not an option is still caught
    by the test above.
    """
    q = valid(type="multiple_choice", options=["Paris", "London"],
              correctAnswer="Paris ")
    questions.validate(q)

    assert q["correctAnswer"] == "Paris"


def test_every_checkbox_answer_must_be_an_option():
    with pytest.raises(ValidationError):
        questions.validate(valid(
            type="checkboxes",
            options=["2", "3", "4"],
            correctAnswers=["2", "7"],
        ))


def test_valid_grading_passes():
    questions.validate(valid(
        type="multiple_choice",
        options=["Paris", "London"],
        correctAnswer="Paris",
        pointValue=2,
    ))


@pytest.mark.parametrize("points", [0, -1, 1.5, "1"])
def test_point_value_must_be_a_positive_integer(points):
    with pytest.raises(ValidationError) as e:
        questions.validate(valid(
            type="multiple_choice",
            options=["A", "B"],
            correctAnswer="A",
            pointValue=points,
        ))

    assert e.value.field == "pointValue"


# --- newlines in displayed text ---------------------------------------------
# Regression: the API answers 400 "Displayed text cannot contain newlines", and
# it does so only after the form has already been created, leaving an empty
# form behind. The model wraps long labels and options across lines, so this is
# flattened during normalisation rather than rejected.

NL = chr(10)
CR = chr(13)


def test_newlines_in_a_label_are_flattened():
    q = questions.normalize({"type": "short_text", "label": "Full" + NL + "name"})

    assert q["label"] == "Full name"


def test_carriage_returns_are_flattened_too():
    q = questions.normalize({"type": "short_text", "label": "Full" + CR + NL + "name"})

    assert q["label"] == "Full name"


def test_newlines_in_a_description_are_flattened():
    q = questions.normalize({
        "type": "short_text", "label": "Name",
        "description": "First line" + NL + "second line",
    })

    assert q["description"] == "First line second line"


def test_newlines_in_options_are_flattened():
    q = questions.normalize({
        "type": "multiple_choice", "label": "Pick",
        "options": ["Deep" + NL + "red", "Blue"],
    })

    assert q["options"] == ["Deep red", "Blue"]


def test_scale_labels_are_flattened():
    q = questions.normalize({
        "type": "linear_scale", "label": "Rate",
        "startLabel": "Very" + NL + "low", "endLabel": "Very" + NL + "high",
    })

    assert q["startLabel"] == "Very low"
    assert q["endLabel"] == "Very high"


def test_answers_are_flattened_with_their_options():
    """Both sides get the same treatment, so the answer still matches."""
    q = questions.normalize({
        "type": "multiple_choice", "label": "Capital?",
        "options": ["Buenos" + NL + "Aires", "Lima"],
        "correctAnswer": "Buenos" + NL + "Aires",
    })
    questions.validate(q)

    assert q["correctAnswer"] == "Buenos Aires"
    assert q["correctAnswer"] in q["options"]


def test_surrounding_whitespace_is_trimmed():
    q = questions.normalize({"type": "short_text", "label": "  Name  "})

    assert q["label"] == "Name"


def test_runs_of_spaces_collapse():
    q = questions.normalize({"type": "short_text", "label": "Full     name"})

    assert q["label"] == "Full name"


def test_non_strings_pass_through_untouched():
    """So validate() can still report a useful type error."""
    assert questions.collapse_whitespace(5) == 5
    assert questions.collapse_whitespace(None) is None


def test_validation_still_catches_newlines_that_bypass_normalisation():
    """The backstop, for anything built without going through normalize()."""
    q = questions.normalize({"type": "short_text", "label": "Name"})
    q["label"] = "Full" + NL + "name"

    with pytest.raises(ValidationError) as e:
        questions.validate(q)

    assert "newline" in e.value.message.lower()
