FROM python:3.12-slim

ENV POETRY_VERSION=1.8.2 \
    POETRY_VIRTUALENVS_CREATE=false \
    PYTHONUNBUFFERED=1

WORKDIR /app

# system deps for building wheels
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential=12.9 \
        ca-certificates=20230311 \
        curl=7.88.1-10+deb12u12 \
        ffmpeg=7:5.1.6-0+deb12u1 \
        make=4.3-4.1 \
        unzip=6.0-28 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "poetry==$POETRY_VERSION"

# copy poetry files and install only prod deps
COPY pyproject.toml poetry.lock* /app/
RUN poetry install --no-root --no-dev

WORKDIR /app

# entrypoint script
COPY start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

# bring in the zip so we can unpack at runtime
COPY sounds.zip /app/sounds.zip
COPY Makefile /app/Makefile
RUN make unpack

COPY . /app

# default command
ENTRYPOINT ["start.sh"]
