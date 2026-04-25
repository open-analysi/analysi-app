# Unified Dockerfile for all Analysi services (API, alerts-worker, integrations-worker)
# Stages: base → dev (local development) → production
#
# All services share the same codebase and dependencies. The entrypoint is
# configured at the compose / Kubernetes layer via `command:`.
#
# Local dev:  docker compose uses target: dev (volume-mounts source)
# Production: docker build --target production (copies source, non-root)

# ---- Base: shared dependencies ----
FROM python:3.13-slim AS base

WORKDIR /app

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PORT=8000

# System deps + Node.js (required for Claude Code CLI in alerts-worker).
# NODE_MAJOR pins which NodeSource setup script we fetch; the actual nodejs
# package is then installed via apt with version constraint. Curl flags
# (--proto, --tlsv1.2) enforce HTTPS-with-modern-TLS to harden the
# downstream-trust-on-first-use of the NodeSource repo.
ARG NODE_MAJOR=20
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        postgresql-client \
        curl && \
    curl --proto '=https' --tlsv1.2 -fsSL "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    rm -rf /var/lib/apt/lists/*

RUN npm install -g @anthropic-ai/claude-code

# Pin Poetry to a known version so the install is deterministic across rebuilds.
# Bump POETRY_VERSION and re-test when upgrading.
ENV POETRY_VERSION=2.2.1
ENV POETRY_HOME=/opt/poetry
ENV PATH="$POETRY_HOME/bin:$PATH"
RUN curl --proto '=https' --tlsv1.2 -sSL https://install.python-poetry.org | python3 - && \
    poetry config virtualenvs.create false

COPY pyproject.toml poetry.lock ./
COPY dist ./dist

RUN poetry install --no-interaction --no-ansi --without dev --no-root

ARG GIT_SHA=unknown
LABEL org.opencontainers.image.revision=$GIT_SHA

# ---- Dev: local development with hot reload ----
FROM base AS dev

RUN poetry install --no-interaction --no-ansi --with dev --no-root

# Non-root user required: Claude Code CLI refuses --dangerously-skip-permissions as root
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

ENV PYTHONPATH=/app/src
EXPOSE ${PORT}

# Default CMD is the API; compose/k8s overrides for workers
CMD ["poetry", "run", "uvicorn", "analysi.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ---- Production: copy source, non-root user ----
FROM base AS production

COPY src /app/src
COPY agents/dist /app/agents

ENV PYTHONPATH=/app/src
EXPOSE ${PORT}

RUN id -u appuser >/dev/null 2>&1 || useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Poetry config was set as root in base stage; re-set for appuser so
# `poetry run` doesn't create an empty venv (Bug: notifications-worker CrashLoopBackOff)
RUN poetry config virtualenvs.create false

# Copy agents to appuser's .claude directory (for Claude Code CLI discovery)
RUN mkdir -p /home/appuser/.claude/agents && \
    cp -r /app/agents/* /home/appuser/.claude/agents/

# Default CMD is the API; compose/k8s overrides for workers
CMD ["poetry", "run", "uvicorn", "analysi.main:app", "--host", "0.0.0.0", "--port", "8000"]
