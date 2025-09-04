FROM linuxserver/ffmpeg:latest AS base

RUN apt-get update && apt-get install -yqq --no-install-recommends python3

FROM base AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
ENV UV_PYTHON_DOWNLOADS=0 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml uv.lock .

RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-install-project --no-dev

COPY . .

RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev

FROM base

COPY --from=builder --chown=app:app /app /app
ENV PATH="/app/.venv/bin:$PATH"

LABEL org.opencontainers.image.source="https://github.com/wthueb/wi1-bot"
LABEL org.opencontainers.image.maintainer="wilhueb@gmail.com"

ENV WB_CONFIG_PATH=/config/config.yaml
ENV WB_LOG_DIR=/logs

RUN mkdir -p /config
RUN mkdir -p /logs

EXPOSE 9000

ENTRYPOINT ["python", "-m", "wi1_bot.scripts.start"]
