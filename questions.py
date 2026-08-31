"""Definition and validation of the supported question types.

QUESTION_TYPES is the project's single source of truth: both the prompt the
model receives (see prompts.py) and the validation rules are derived from it.
Adding a new type happens in one place.
"""


QUESTION_TYPES = {
    "short_text": {
        "description": "Single-line short text answer",
        "required_fields": ["type", "label", "required"],
        "optional_fields": ["description"],
        "example": {
            "type": "short_text",
            "label": "Full name",
            "required": True,
        },
    },
    "paragraph": {
        "description": "Multi-line long text answer",
        "required_fields": ["type", "label", "required"],
        "optional_fields": ["description"],
        "example": {
            "type": "paragraph",
            "label": "Tell us about your experience",
            "required": False,
        },
    },
    "multiple_choice": {
        "description": "Pick exactly one option",
        "required_fields": ["type", "label", "required", "options"],
        "optional_fields": ["description", "shuffle", "correctAnswer", "pointValue"],
        "example": {
            "type": "multiple_choice",
            "label": "What is your favourite colour?",
            "required": True,
            "options": ["Red", "Green", "Blue"],
            "shuffle": False,
        },
        "exam_example": {
            "type": "multiple_choice",
            "label": "What is the capital of France?",
            "required": True,
            "options": ["London", "Paris", "Berlin", "Madrid"],
            "correctAnswer": "Paris",
            "pointValue": 1,
        },
    },
    "checkboxes": {
        "description": "Pick any number of options",
        "required_fields": ["type", "label", "required", "options"],
        "optional_fields": ["description", "shuffle", "correctAnswers", "pointValue"],
        "example": {
            "type": "checkboxes",
            "label": "Which languages do you know?",
            "required": False,
            "options": ["Python", "JavaScript", "Java"],
        },
        "exam_example": {
            "type": "checkboxes",
            "label": "Which of these are prime numbers?",
            "required": True,
            "options": ["2", "3", "4", "6", "7"],
            "correctAnswers": ["2", "3", "7"],
            "pointValue": 2,
        },
    },
    "dropdown": {
        "description": "Pick one option from a dropdown menu",
        "required_fields": ["type", "label", "required", "options"],
        "optional_fields": ["description"],
        "example": {
            "type": "dropdown",
            "label": "Country of residence",
            "required": True,
            "options": ["Argentina", "Chile", "Uruguay"],
        },
    },
    "linear_scale": {
        "description": "Numeric scale with a minimum and a maximum",
        "required_fields": ["type", "label", "required", "minValue", "maxValue"],
        "optional_fields": ["startLabel", "endLabel"],
        # Limits imposed by the Google Forms API, not by FillBot. They live
        # inside the dict so the prompt picks them up automatically.
        "constraints": {
            "minValue": "MUST be exactly 0 or 1",
            "maxValue": "MUST be an integer between 2 and 10 (inclusive)",
        },
        "example": {
            "type": "linear_scale",
            "label": "Satisfaction level",
            "required": True,
            "minValue": 1,
            "maxValue": 5,
            "startLabel": "Very low",
            "endLabel": "Very high",
        },
    },
    "date": {
        "description": "Date picker",
        "required_fields": ["type", "label", "required"],
        "optional_fields": [],
        "example": {
            "type": "date",
            "label": "Date of birth",
            "required": True,
        },
    },
    "time": {
        "description": "Time picker",
        "required_fields": ["type", "label", "required"],
        "optional_fields": [],
        "example": {
            "type": "time",
            "label": "Preferred time",
            "required": False,
        },
    },
}


# Types built with a choiceQuestion, which therefore require options.
CHOICE_TYPES = frozenset({"multiple_choice", "checkboxes", "dropdown"})

# linear_scale bounds accepted by the Google Forms API.
SCALE_LOW_VALUES = frozenset({0, 1})
SCALE_HIGH_MIN = 2
SCALE_HIGH_MAX = 10


class ValidationError(Exception):
    """A question produced by the model breaks one of the rules."""

    def __init__(self, message, field=None):
        self.message = message
        self.field = field
        super().__init__(message)


def normalize(raw):
    """Bring the model's raw JSON into a predictable shape.

    Always leaves the same keys present, set to None when they were absent, so
    the rest of the code never has to ask whether they exist.
    """
    return {
        "type": raw.get("type"),
        "label": raw.get("label"),
        "required": raw.get("required", False),
        "description": raw.get("description"),
        "options": raw.get("options"),
        "shuffle": raw.get("shuffle"),
        "minValue": raw.get("minValue"),
        "maxValue": raw.get("maxValue"),
        "startLabel": raw.get("startLabel"),
        "endLabel": raw.get("endLabel"),
        "correctAnswer": raw.get("correctAnswer"),
        "correctAnswers": raw.get("correctAnswers"),
        "pointValue": raw.get("pointValue"),
    }


def strip_grading(question):
    """Drop the grading data from a question that is not an exam question.

    The model sometimes returns correct answers even when it was not asked
    for them; without this they would end up in a regular form.
    """
    question["correctAnswer"] = None
    question["correctAnswers"] = None
    question["pointValue"] = None
    return question


def validate(q):
    """Validate an already-normalised question.

    Every rule here mirrors a constraint the Google Forms API enforces server
    side. Checking them locally is what makes it possible to retry with a
    useful message instead of failing the whole form against Google.

    Returns nothing: raises ValidationError when something does not add up.
    """
    _validate_type(q)
    _validate_label(q)

    if q["type"] in CHOICE_TYPES:
        _validate_options(q)

    if q["type"] == "linear_scale":
        _validate_scale(q)

    _validate_grading(q)


def _validate_type(q):
    if not q.get("type"):
        raise ValidationError("Missing required field 'type'", field="type")

    if q["type"] not in QUESTION_TYPES:
        raise ValidationError(
            "Unsupported question type: " + str(q["type"]) + ". Supported types: "
            + ", ".join(sorted(QUESTION_TYPES)) + ".",
            field="type",
        )


def _validate_label(q):
    if not q.get("label") or not str(q["label"]).strip():
        raise ValidationError("Missing required field 'label'", field="label")


def _validate_options(q):
    options = q.get("options")

    if not options or len(options) < 2:
        raise ValidationError(
            "Questions of type " + q["type"] + " require at least two options.",
            field="options",
        )

    if any(not str(option).strip() for option in options):
        raise ValidationError(
            "Questions of type " + q["type"] + " cannot have blank options.",
            field="options",
        )

    if len(set(options)) != len(options):
        raise ValidationError(
            "Questions of type " + q["type"] + " cannot have duplicate options.",
            field="options",
        )


def _validate_scale(q):
    """The API only accepts minValue of 0 or 1, and maxValue between 2 and 10.

    Without this check a request like "rate it from 1 to 100" passes local
    validation and then fails with an unexplained 400 from Google.
    """
    low, high = q.get("minValue"), q.get("maxValue")

    if low is None or high is None:
        raise ValidationError(
            "Linear scale requires minValue and maxValue",
            field="minValue/maxValue",
        )

    if not isinstance(low, int) or not isinstance(high, int):
        raise ValidationError(
            "Linear scale bounds must be integers", field="minValue/maxValue"
        )

    if low not in SCALE_LOW_VALUES:
        raise ValidationError(
            "Linear scale minValue must be 0 or 1, got " + str(low) + ".",
            field="minValue",
        )

    if not SCALE_HIGH_MIN <= high <= SCALE_HIGH_MAX:
        raise ValidationError(
            "Linear scale maxValue must be between " + str(SCALE_HIGH_MIN)
            + " and " + str(SCALE_HIGH_MAX) + ", got " + str(high) + ".",
            field="maxValue",
        )

    if low >= high:
        raise ValidationError("minValue must be less than maxValue", field="minValue")


def _validate_grading(q):
    """Correct answers have to be among the question's options.

    Google rejects the whole batchUpdate when a correct answer does not match
    an option exactly, so one stray space from the model would take the entire
    form down with it.
    """
    options = q.get("options") or []

    answers = []
    if q.get("correctAnswer") is not None:
        answers.append(q["correctAnswer"])
    if q.get("correctAnswers") is not None:
        answers.extend(q["correctAnswers"])

    for answer in answers:
        if answer not in options:
            raise ValidationError(
                "Correct answer " + str(answer) + " is not one of the options.",
                field="correctAnswer",
            )

    points = q.get("pointValue")
    if points is not None and (not isinstance(points, int) or points <= 0):
        raise ValidationError(
            "pointValue must be a positive integer, got " + str(points) + ".",
            field="pointValue",
        )
