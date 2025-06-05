# type: ignore
import asyncio
import logging
import os

import pytest

from balaambot import main


class DummySync:
    def __init__(self):
        self.called = False

    async def __call__(self):
        self.called = True


class DummyLogger(logging.Logger):
    def __init__(self):
        super().__init__(name="dummy")
        self.last_msg = None
        self.last_args = None

    def info(self, msg, *args, **kwargs):
        self.last_msg = msg
        self.last_args = args


@pytest.fixture(autouse=True)
def isolate_env(monkeypatch):
    """Ensure environment modifications don't leak."""
    # Make a copy of os.environ
    original = os.environ.copy()
    yield
    os.environ.clear()
    os.environ.update(original)


@pytest.mark.asyncio
async def test_load_extensions(monkeypatch):
    loaded = []

    async def fake_load(ext):
        loaded.append(ext)

    # Patch the bot.load_extension method
    monkeypatch.setattr(main.bot, "load_extension", fake_load)

    # Run the coroutine
    await main.load_extensions()

    assert loaded == [
        "balaambot.bot_commands.bot_commands",
        "balaambot.bot_commands.joke_commands",
        "balaambot.bot_commands.music_commands",
        "balaambot.bot_commands.sfx_commands",
    ]


@pytest.mark.asyncio
async def test_on_ready_logs_and_sync(monkeypatch):
    # Prepare dummy sync and dummy logger
    dummy_sync = DummySync()
    monkeypatch.setattr(main.bot.tree, "sync", dummy_sync)
    dummy_logger = DummyLogger()
    monkeypatch.setattr(main, "logger", dummy_logger)

    # Call on_ready
    await main.on_ready()

    # Verify sync was awaited
    assert dummy_sync.called, "bot.tree.sync() was not called"

    # Verify logger.info was invoked with the bot user
    assert dummy_logger.last_msg == "Logged in as %s"
    assert dummy_logger.last_args == (main.bot.user,)


def test_start_raises_when_no_token(monkeypatch):
    # Ensure DISCORD_BOT_TOKEN is not set or empty
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "")
    # Reload the module-level BOT_TOKEN
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "")
    monkeypatch.setattr(main, "BOT_TOKEN", os.getenv("DISCORD_BOT_TOKEN"))
    with pytest.raises(ValueError) as exc:
        main.start()
    assert "DISCORD_BOT_TOKEN environment variable is not set." in str(exc.value)


def test_start_runs_extensions_and_bot(monkeypatch):
    # Set a fake token
    fake_token = "fake-token-123"
    monkeypatch.setenv("DISCORD_BOT_TOKEN", fake_token)
    monkeypatch.setattr(main, "BOT_TOKEN", fake_token)

    # Track calls to asyncio.run and bot.run
    ran = {"asyncio_run": False, "bot_run": False}

    def fake_asyncio_run(coro):
        # Should be called with main.load_extensions()
        assert asyncio.iscoroutine(coro)
        # We can run it synchronously since load_extensions is safe
        asyncio.get_event_loop().run_until_complete(coro)
        ran["asyncio_run"] = True

    def fake_bot_run(token):
        assert token == fake_token
        ran["bot_run"] = True

    monkeypatch.setattr(asyncio, "run", fake_asyncio_run)
    monkeypatch.setattr(main.bot, "run", fake_bot_run)

    # Finally call start
    main.start()

    assert ran["asyncio_run"], "asyncio.run was not called"
    assert ran["bot_run"], "bot.run was not called"
