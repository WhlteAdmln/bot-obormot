FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATABASE_PATH=/app/data/bot.db

WORKDIR /app

# ffmpeg используется для обработки видео и аудио.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 bot \
    && useradd --system --uid 10001 --gid bot \
       --create-home --home-dir /home/bot bot

# Runtime-зависимости устанавливаются строго из lock-файла.
COPY requirements-lock.txt .
RUN python -m pip install \
        --no-cache-dir \
        --disable-pip-version-check \
        -r requirements-lock.txt \
    && python -m pip check

COPY --chown=bot:bot bot ./bot
COPY --chown=bot:bot prompts ./prompts

RUN install -d -o bot -g bot /app/data

USER bot

VOLUME ["/app/data"]

CMD ["python", "-m", "bot.main"]
