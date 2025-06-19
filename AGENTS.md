# BalaamBot Agent Guide

This document summarises the repository so that future contributors can quickly understand the layout and tooling.

## Overview

BalaamBot is a Discord bot implemented in Python.  It plays YouTube audio, schedules and triggers sound effects and exposes a few fun commands such as jokes and a small cat mini‑game.  The entry point is `src/balaambot/main.py` which starts a `discord.py` bot and loads cogs from `src/balaambot/bot_commands/`.

Key features include:

- **YouTube playback** via the modules under `src/balaambot/youtube/`.
- **Sound effect scheduling** in `src/balaambot/sfx/`.
- **Cat adoption mini‑game** in `src/balaambot/cats/`.
- **Slash command cogs** in `src/balaambot/bot_commands/`.
- **Custom audio mixer** `MultiAudioSource` in `src/balaambot/audio_handlers/`.

Tests covering these modules live under `tests/`.

## Project structure

```
src/balaambot/
├── audio_handlers/        # Audio mixer implementation
├── bot_commands/          # Discord slash commands
├── cats/                  # CatHandler and persistence
├── sfx/                   # Scheduled sound effects
├── youtube/               # YouTube download and queue handling
├── config.py              # Runtime configuration
├── discord_utils.py       # Helpers for voice and interactions
├── main.py                # Bot entry point
└── utils.py               # General helpers and cache
```

Sound effect files are stored in the `sounds/` directory (extracted from `sounds.zip`). Cached audio and metadata are written under the directory defined by `PERSISTENT_DATA_DIR` (defaults to `persistent/`).

## Tooling

- **Ruff** (`ruff.toml`) is used for linting/formatting. Run `uv run ruff check .` or `make lint`.
- **Pytest** is used for tests. `make test` runs the unit suite and `make test-integration` runs slower tests.
- The project requires Python 3.10+ and depends on `discord.py`, `yt-dlp`, `anyio` and others (`pyproject.toml`).
- A `Makefile` provides common targets for development and deployment. `make run` starts the bot locally.

### Important Makefile commands

The Makefile provides convenient shortcuts for most tasks. These targets are the
preferred way to build the project and run tests.

- `make install-dev` – install development dependencies via `uv`.
- `make lint` – run Ruff checks.
- `make build` – build a distributable package with `uv build`.
- `make test` and `make test-integration` – preferred way to run unit and integration tests.
- `make run` – launch the bot locally.
- `make docker-build` and `make docker-run` – build and run the Docker container.
- `make docker-brun` – combined Docker build and run.
- `make clean` – remove caches and build artifacts.
- `make unpack` – extract bundled sound effects.

## Contributing

- Follow the existing style: 4‑space indentation and line length 88 (see `ruff.toml`).
- New features should include tests under `tests/`.
- New features must also be documented in `README.md` at the project root.
- Keep the `persistent/` directory out of version control – it stores runtime data such as cached audio and cat data.
- After modifying code or documentation, run `make lint` and `make test` before committing.

