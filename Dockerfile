FROM jrottenberg/ffmpeg:7.1-nvidia2404 AS base

RUN apt-get update && apt-get install -yqq --no-install-recommends python3

FROM base AS compiler

RUN apt-get install -yqq --no-install-recommends python3-venv git

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app
COPY . .
RUN pip install .

FROM base

COPY --from=compiler /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

LABEL org.opencontainers.image.source="https://github.com/wthueb/wi1-bot"
LABEL org.opencontainers.image.maintainer="wilhueb@gmail.com"

ENV WB_CONFIG_PATH=/config/config.yaml
ENV WB_LOG_DIR=/logs

RUN mkdir -p /config
RUN mkdir -p /logs

EXPOSE 9000

ENTRYPOINT ["python", "-m", "wi1_bot.scripts.start"]
