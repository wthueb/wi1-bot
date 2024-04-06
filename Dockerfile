FROM python:3.10

RUN apt-get update && apt-get install -y ffmpeg

WORKDIR /app

COPY . .

RUN pip install .

ENV WB_CONFIG_PATH=/app/config/config.yaml
ENV WB_LOG_DIR=/app/logs

RUN mkdir -p config
RUN mkdir -p logs

EXPOSE 9000

ENTRYPOINT ["python", "-m", "wi1_bot.scripts.start"]

