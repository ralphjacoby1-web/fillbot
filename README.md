# FillBot

[![tests](https://github.com/ralphjacoby1-web/FIllbot_def/actions/workflows/tests.yml/badge.svg)](https://github.com/ralphjacoby1-web/FIllbot_def/actions/workflows/tests.yml)
[![license](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Turns a plain-language description into a real Google Form, created directly in
the user's own Drive.

You type *"customer satisfaction survey for a restaurant"*, pick how many
questions you want, and FillBot builds the form. It also has an exam mode that
generates questions with correct answers and point values, using Google Forms'
own auto-grading.

A Flask app with Jinja templates, a local SQLite database and Google login.

---

## What you need before running it

FillBot is self-hosted: you run it yourself, with your own credentials. There is
no hosted version to sign into.

- **An OpenAI API key.** This is the one part that costs money. OpenAI bills per
  token, and FillBot spends roughly 2,200 tokens per form (~1,550 in, ~700 out),
  which lands somewhere under a cent with `gpt-4o` at current rates. Check the
  [pricing page](https://openai.com/api/pricing/) for the actual numbers, and
  set a spending limit on your OpenAI account if you want a hard ceiling. You
  can point `OPENAI_MODEL` at a cheaper model in `.env` without touching code.
- **A Google Cloud project** with the Forms API enabled and an OAuth client.
  Free: Google does not bill for the Forms API, it only applies rate quotas.
- **Docker**, or Python 3.11+ if you would rather run it directly.

Both credentials go in a `.env` file that is never committed. Setup is walked
through below.

> If you deploy this somewhere public, remember the API key is yours: every form
> a visitor generates is billed to you. That is what `MAX_FORMS` is for.

---

## How it works

```
user prompt
      |
      v
   ai.py            asks the model for the question schema
      |
      v
 questions.py       normalises and validates against Google's rules
      |                    |
      |                    +--> anything that fails is retried, handing the
      |                         error back to the model to correct itself
      v
form_builder.py     translates each question into the API's format
      |
      v
google_forms.py     creates the form in the user's Drive
```

The order is the point: **the questions are generated and validated before
anything touches Google**. If the model fails, nothing was created yet. And if
Google rejects a request anyway, the half-built form is deleted rather than
left behind, so a failure never costs the user an empty form in their Drive.

`QUESTION_TYPES`, in `questions.py`, is the single source of truth: both the
prompt the model receives and the validation rules come out of that dictionary.
Adding a question type happens in one place.

---

## Layout

```
app.py            Flask routes
config.py         configuration read from the environment
helpers.py        login_required, session and usage limits
db.py             SQLite access
schema.sql        database schema
ai.py             model calls and generation
prompts.py        the prompts (built from QUESTION_TYPES)
questions.py      question types, normalisation and validation
form_builder.py   question -> Google Forms API item
google_auth.py    OAuth flow and credentials
google_forms.py   Google Forms API client

templates/        layout.html plus one template per page
static/           css, js and images

Dockerfile          how the image is built
docker-compose.yml  how the container is run
```

---

## Running it with Docker

Docker builds a container with its own Python and its own dependencies, so
nothing depends on what is installed on your machine. It is the shortest path
from a fresh clone to a running app.

Fill in `.env` first (see the section below), then:

```bash
docker compose up --build
```

Open `http://localhost:5000`. To stop it:

```bash
docker compose down
```

### What each file does

- **`Dockerfile`** describes how to *build* the image: which Python, which
  dependencies, which code. Every instruction adds a cached layer, which is why
  `requirements.txt` is copied and installed before the rest of the code:
  editing a `.py` file does not reinstall your dependencies.
- **`.dockerignore`** lists what is left out of the build. It keeps `venv/`
  (Windows binaries, useless on the container's Linux) and `.env` (secrets)
  out of the image.
- **`docker-compose.yml`** describes how to *run* it: the port mapping, the
  environment variables, the volumes.

### Two details worth understanding

**The database lives in a volume.** A container's filesystem dies with it, so
the SQLite file is written to `./data`, a directory on your machine mounted at
`/app/data` inside the container. Your users and counters survive
`docker compose down`.

**Your code is mounted live.** The project directory is mounted over `/app`, so
editing a file restarts Flask's reloader instead of forcing a rebuild. Remove
that line from `docker-compose.yml` to run the code exactly as it was baked
into the image.

### Useful commands

```bash
docker compose logs -f
```

```bash
docker compose exec web sh
```

The first follows the logs; the second opens a shell inside the running
container, which is the fastest way to see what the app actually sees.

---

## Running it without Docker

### 1. Dependencies

```bash
python -m venv venv && venv/Scripts/activate && pip install -r requirements.txt
```

The dependencies are installed *into the virtualenv*, not system-wide, so
`venv/Scripts/activate` has to run in every new terminal before `python app.py`.
Skipping it gets you `ModuleNotFoundError: No module named 'flask'`, because the
system Python does not have the packages. Docker exists to make this problem go
away.

### 2. Credentials

```bash
cp .env.example .env
```

Fill in `.env`:

| Variable | Where to get it |
|---|---|
| `OPENAI_API_KEY` | https://platform.openai.com/api-keys |
| `OAUTH_CLIENT_ID` | Google Cloud Console, see below |
| `OAUTH_CLIENT_SECRET` | same |
| `SECRET_KEY` | `python -c "import secrets; print(secrets.token_urlsafe(32))"` |

For the Google credentials:

1. In the [Google Cloud Console](https://console.cloud.google.com/), enable the
   **Google Forms API**.
2. Under *APIs & Services > Credentials*, create an **OAuth client ID** of type
   **Web application**.
3. Add `http://localhost:5000/callback` as an *Authorized redirect URI*.
4. On the consent screen, add your account as a test user.

If a required variable is missing, the app refuses to start and tells you which
one.

### 3. Start it

```bash
python app.py
```

Open `http://localhost:5000`. The `fillbot.db` file is created on first start.

---

## Database

A SQLite file at `data/fillbot.db`, created from `schema.sql`. There is no
server to run.

It sits in its own directory because that is what the Docker container mounts,
so running with Docker and running with the virtualenv share the same database
rather than each keeping its own.

One table, `users`, holding the email, the Google credentials and the usage
counters. **Tokens live in the database, not in the browser**: the session
cookie only carries the user's id.

To start from scratch, delete the file:

```bash
rm data/fillbot.db
```

---

## If you deploy it

Everything below is off by default so that running it locally is friction-free,
and so that deploying it by accident cannot hand out anything dangerous. Turn
these on wherever it is reachable by someone else:

- **`FLASK_DEBUG` must stay off.** Werkzeug's debugger executes arbitrary code
  from the browser. `docker-compose.yml` enables it for local development only;
  the image itself defaults to off.
- **`SESSION_COOKIE_SECURE=1`**, so the session cookie is only ever sent over
  HTTPS.
- **Use a real WSGI server.** `python app.py` runs Flask's development server,
  which is single-threaded and not built for exposure. `gunicorn` is already in
  `requirements.txt`:

```bash
gunicorn --bind :5000 --workers 1 --threads 8 --timeout 0 app:app
```

`--timeout 0` matters: generating a form chains several model and API calls, and
gunicorn's 30-second default would kill the worker mid-request.

---

## Usage limits

They exist to cap API spending when the app is publicly reachable, not to sell
anything. Running it with your own key, raise `MAX_FORMS` in `.env` and you're
done.

- `MAX_FORMS` forms per user (5 by default)
- `RATE_LIMIT_SECONDS` of cooldown between forms (60 by default)
- The account set as `DEV_EMAIL` has no limit

---

## Tests

```bash
pip install -r requirements-dev.txt
```

```bash
python -m pytest
```

Or inside the container, without installing anything locally:

```bash
docker compose exec web sh -c "pip install -q pytest && python -m pytest"
```

113 tests, no network access and no API keys needed. They cover the parts where a
mistake is expensive:

- **`test_questions.py`** — every validation rule, each mirroring a constraint
  the Google Forms API enforces. A failure here means FillBot would have shipped
  a form Google rejects.
- **`test_form_builder.py`** — the exact API payload for each question type,
  including the grading block for exam mode.
- **`test_helpers.py`** — the usage limits that keep a public deployment from
  running up an API bill.
- **`test_app.py`** — routes and access control: `login_required`, the OAuth
  state check, and that the quota returns 429 *before* any token is spent.
- **`test_google_forms.py`** — the request shapes sent to Google, against a
  stubbed client, including the rollback when a request is rejected.

Several are regression tests for bugs that actually shipped, and they are marked
as such in the code. The suite was verified by reintroducing three of those bugs
and confirming it caught each one.

They also run on every push via GitHub Actions, across Python 3.10, 3.11 and
3.12 — see [`.github/workflows/tests.yml`](.github/workflows/tests.yml).
Installing from `requirements-dev.txt` on a clean machine is part of the job, so
an incomplete dependency list fails there rather than on somebody else's clone.

---

## License

MIT. See [LICENSE](LICENSE).

---

## Adding a question type

1. Describe it in `QUESTION_TYPES` (`questions.py`). The prompt picks it up
   automatically.
2. If the Forms API imposes constraints, add them to `validate()` in the same
   file.
3. Write the builder in `form_builder.py` and register it in `build()`.
