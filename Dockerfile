ARG PYTHON_IMAGE=python:3.12-slim

# Stage 1: build wheels. The compiler is needed only for the optional `tgs` extra.
FROM ${PYTHON_IMAGE} AS builder

RUN apt-get update \
    && apt-get install --yes --no-install-recommends build-essential cmake \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY pyproject.toml requirements-lock.txt README.md LICENSE ./
COPY bot_obormot ./bot_obormot

RUN python -m pip wheel \
    --no-cache-dir \
    --wheel-dir=/wheels \
    --requirement requirements-lock.txt \
    && python -m pip wheel \
        --no-cache-dir \
        --no-deps \
        --wheel-dir=/wheels \
        .

# Stage 2: runtime image without a compiler.
FROM ${PYTHON_IMAGE} AS runtime

RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /wheels /wheels
COPY --from=builder /build/requirements-lock.txt /tmp/requirements-lock.txt

RUN python -m pip install \
    --no-cache-dir \
    --no-index \
    --find-links=/wheels \
    --requirement /tmp/requirements-lock.txt \
    bot-obormot \
    && rm -rf /wheels /tmp/requirements-lock.txt

RUN groupadd --system --gid 10001 bot-obormot \
    && useradd --system --uid 10001 --gid bot-obormot \
        --create-home --home-dir /home/bot-obormot \
        --shell /usr/sbin/nologin bot-obormot \
    && install -d -o bot-obormot -g bot-obormot /data

ENV BOT_OBORMOT_HOME=/data \
    DATABASE_PATH=/data/bot.db \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

LABEL org.opencontainers.image.source="https://github.com/WhlteAdmln/bot-obormot"

WORKDIR /app
VOLUME ["/data"]

USER bot-obormot:bot-obormot

HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD ["bot-obormot", "doctor", "--offline", "--quiet"]

CMD ["bot-obormot", "run"]
