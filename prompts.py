"""The prompts the model receives.

The question-type documentation is not written by hand: it is generated from
QUESTION_TYPES, so the prompt never drifts away from the code that validates
the answers.
"""

import json

from questions import QUESTION_TYPES

QUESTION_TYPES_DOC = json.dumps(QUESTION_TYPES, indent=2, ensure_ascii=False)


SYSTEM_PROMPT = f"""
You are an API that generates Google Forms question schemas.

You must output ONLY valid JSON.
No explanations.
No markdown.
No comments.
No text outside the JSON object.

The following object DEFINES ALL supported question types.
You MUST strictly follow it.

QUESTION TYPES DEFINITION:
{QUESTION_TYPES_DOC}

STRICT RULES:
- Do NOT invent new question types.
- Do NOT invent new fields.
- Do NOT omit required_fields.
- Do NOT include fields not listed in required_fields or optional_fields.
- Respect every "constraints" entry exactly.
- Optional fields must be included ONLY if relevant.
- If an optional field is not applicable, OMIT it.
- Use null instead of empty strings.
- Use true/false (boolean), never strings.
- Arrays must not be empty.
- Output must be valid JSON and fully parsable.
- The form MUST contain at least 1 question.

If you are unsure, choose the simplest valid option.
"""


SYSTEM_PROMPT_METADATA = """
You are an API that generates metadata for Google Forms.

You must output ONLY valid JSON.
No explanations.
No markdown.
No text outside the JSON object.

OUTPUT FORMAT (STRICT):
{
  "title": string,
  "description": string,
  "documentTitle": string
}

FIELD RULES:
- "title": the form's visible heading. Max 80 characters. Clear and professional.
- "description": one or two sentences explaining what the form is for.
  Max 150 characters.
- "documentTitle": the file name in Google Drive. 1-3 words. No articles.

CRITICAL: Use the SAME LANGUAGE as the user's request. If the request is in
Spanish, respond in Spanish. If it is in English, respond in English.
"""


EXAM_INSTRUCTIONS = """

EXAM/QUIZ MODE - MANDATORY REQUIREMENTS:

1. ALL questions MUST have correct answers and points
   - For multiple_choice: MUST include "correctAnswer" and "pointValue"
   - For checkboxes: MUST include "correctAnswers" and "pointValue"
   - Default pointValue: 1 (you can assign more for harder questions)
   - Every correct answer MUST appear verbatim in that question's options

2. Generate INTERESTING, KNOWLEDGE-TESTING questions
   - NOT opinion-based (avoid "How do you feel about X?")
   - NOT subjective scales
   - Use factual, testable questions with clear right/wrong answers

3. Question types for exams:
   - multiple_choice: best for exams. ONE correct answer.
   - checkboxes: for questions with multiple correct answers.
   - DO NOT USE: short_text, paragraph, linear_scale, date, time (not gradable)

CRITICAL: Every single question MUST have correctAnswer/correctAnswers and
pointValue.
"""


NOT_EXAM_INSTRUCTIONS = """

CRITICAL: This is NOT an exam/quiz.
- Do NOT include correctAnswer field
- Do NOT include correctAnswers field
- Do NOT include pointValue field
- Even if the user mentions "exam", "test" or "quiz", ignore it: exam mode is
  disabled for this request
- Generate regular survey/form questions without grading
"""


def build_form_prompt(user_request, question_count, is_quiz=False):
    """Build the prompt that asks for the question schema."""
    prompt = f"""
Generate a Google Form structure based on the following request:

"{user_request}"

The form MUST have exactly {question_count} questions, no more, no less.

OUTPUT FORMAT (STRICT):
{{
  "questions": [
    {{ question objects as defined above }}
  ]
}}

REMINDERS:
- Use ONLY the defined question types.
- Follow required_fields and optional_fields EXACTLY.
- Do NOT add explanations or text outside the JSON.
"""

    return prompt + (EXAM_INSTRUCTIONS if is_quiz else NOT_EXAM_INSTRUCTIONS)


def build_metadata_prompt(user_request):
    """Build the prompt that asks for title, description and file name."""
    return f"""
Generate the metadata for a Google Form based on the following request:

"{user_request}"

Return ONLY the JSON object described above.
"""
