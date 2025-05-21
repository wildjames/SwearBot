FROM python:3.12-slim AS builder

WORKDIR /opt

COPY ./pyproject.toml ./poetry.lock* /opt/

# hadolint ignore=DL3013
RUN pip install --no-cache-dir poetry && \
    poetry config virtualenvs.create false && \
    poetry install --no-dev && \
    rm -rf ~/.cache


FROM python:3.12-slim

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
ENV PYTHONUNBUFFERED=True
