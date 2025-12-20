FROM linuxserver/ffmpeg:latest AS base

RUN apt-get update && apt-get install -yqq --no-install-recommends python3 && rm -rf /var/lib/apt/lists/*

FROM base AS builder

RUN apt-get update && apt-get install -yqq --no-install-recommends git && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
ENV UV_PYTHON_DOWNLOADS=0 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml uv.lock .

RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-install-project --no-dev

COPY . .

RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --no-editable

RUN sed -i 's/fallback-version = "0\.0\.0"/fallback-version = "'"$(uvx uv-dynamic-versioning)"'"/' pyproject.toml

FROM builder AS test

RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-editable

ENV WB_CONFIG_PATH=/app/tests/config.yaml

ENTRYPOINT ["uv", "run", "pytest"]

FROM base

COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --from=builder --chown=app:app /app/wi1_bot /app/wi1_bot
COPY --from=builder --chown=app:app /app/pyproject.toml /app/uv.lock /app/
ENV PATH="/app/.venv/bin:$PATH"

LABEL org.opencontainers.image.source="https://github.com/wthueb/wi1-bot"
LABEL org.opencontainers.image.maintainer="wilhueb@gmail.com"

ENV WB_CONFIG_PATH=/config/config.yaml
ENV WB_LOG_DIR=/logs
ENV WB_DB_PATH=/config/wi1_bot.db

RUN mkdir -p /config /logs

EXPOSE 9000

ENTRYPOINT ["python", "-m", "wi1_bot.scripts.start"]
