ARG DEBIAN_VERSION=bookworm
ARG UV_VERSION=latest
ARG VARIANT=3.13


FROM ghcr.io/astral-sh/uv:$UV_VERSION AS uv


FROM python:$VARIANT-slim-$DEBIAN_VERSION

WORKDIR /app

COPY --from=uv /uv /uvx /bin/
COPY pyproject.toml uv.lock ./

ENV PYTHONDONTWRITEBYTECODE=True
ENV PYTHONUNBUFFERED=True
ENV UV_LINK_MODE=copy

# hadolint ignore=DL3008
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    build-essential=12.9 \
    ca-certificates=20230311 \
    curl=7.88.1-10+deb12u12 \
    ffmpeg=7:5.1.6-0+deb12u1 \
    libopus0=1.3.1-3 \
    make=4.3-4.1 \
    unzip=6.0-28 \
    # To remove the image size, it is recommended refresh the package cache as follows
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# bring in the zip so we can unpack at runtime
COPY sounds.zip /app/sounds.zip
COPY Makefile /app/Makefile
RUN make unpack

COPY . /app

# Cache directories
ENV AUDIO_CACHE_DIR="/app/audio_cache"

VOLUME ["/app/audio_cache"]

# entrypoint script
RUN chmod +x ./start.sh

# default command
ENTRYPOINT ["./start.sh"]
