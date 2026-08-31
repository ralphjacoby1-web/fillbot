# A Docker image is built in layers, and each instruction below creates one.
# Docker caches them: if a layer's inputs did not change, it is reused instead
# of re-run. That is why dependencies are installed before the code is copied.

# The base image. "slim" is a trimmed Debian with Python already on it.
# Pinning the minor version means everyone runs the same Python, which is the
# whole point of doing this.
FROM python:3.11-slim

# PYTHONUNBUFFERED: send logs straight to the terminal instead of buffering
#   them, so `docker compose logs` shows output as it happens.
# PYTHONDONTWRITEBYTECODE: skip .pyc files, useless in a container.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Every command from here runs inside /app, and it is where the code will live.
WORKDIR /app

# Only requirements.txt is copied first, on purpose. This layer is only rebuilt
# when that file changes, so editing your Python code does not reinstall every
# dependency from scratch.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Now the rest of the code. What actually gets copied is filtered by
# .dockerignore (no venv, no .env, no database).
COPY . .

# Documents which port the app listens on. It does not publish anything by
# itself; the mapping lives in docker-compose.yml.
EXPOSE 5000

# Listen on every interface. Without this the app would only answer from inside
# the container and the published port would reach nothing.
ENV HOST=0.0.0.0

CMD ["python", "app.py"]
