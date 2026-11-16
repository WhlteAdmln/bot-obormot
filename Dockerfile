FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATABASE_PATH=/app/data/bot.db

WORKDIR /app

# Install ffmpeg for audio and video processing.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 bot \
    && useradd --system --uid 10001 --gid bot \
       --create-home --home-dir /home/bot bot

# Install runtime dependencies from package metadata using lock constraints.
COPY requirements-lock.txt pyproject.toml README.md LICENSE ./
COPY --chown=bot:bot bot ./bot
RUN python -m pip install \
        --no-cache-dir \
        --disable-pip-version-check \
        --constraint requirements-lock.txt \
        . \
    && python -m pip check

RUN install -d -o bot -g bot /app/data

USER bot

VOLUME ["/app/data"]

CMD ["bot-obormot"]
