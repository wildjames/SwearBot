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
        "balaambot.bot_commands.cat_commands",
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
    monkeypatch.setattr(main, "DISCORD_BOT_TOKEN", os.getenv("DISCORD_BOT_TOKEN"))
    with pytest.raises(ValueError) as exc:
        main.start()
    assert "DISCORD_BOT_TOKEN environment variable is not set." in str(exc.value)


def test_load_extensions_fatal(monkeypatch):
    # Patch glob to return empty list
    monkeypatch.setattr(main.pathlib.Path, "glob", lambda self, pat: [])
    called = {}

    def fake_fatal(msg):
        called["fatal"] = msg

    monkeypatch.setattr(main.logger, "fatal", fake_fatal)
    # Should not raise, just log fatal
    asyncio.run(main.load_extensions())
    assert "No extensions found to load" in called["fatal"]


def test_main_invalid_token(monkeypatch):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", '"badtoken"')
    monkeypatch.setattr(main, "DISCORD_BOT_TOKEN", '"badtoken"')
    with pytest.raises(ValueError) as exc:
        asyncio.run(main.main())
    assert "contains invalid characters" in str(exc.value)


def test_main_success(monkeypatch):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "goodtoken")
    monkeypatch.setattr(main, "DISCORD_BOT_TOKEN", "goodtoken")

    class DummyBot:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def start(self, token):
            assert token == "goodtoken"

    monkeypatch.setattr(main, "bot", DummyBot())

    async def fake_load_extensions():
        pass

    monkeypatch.setattr(main, "load_extensions", fake_load_extensions)
    # Should not raise
    asyncio.run(main.main())

