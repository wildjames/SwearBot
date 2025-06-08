import asyncio
import logging
import os
import pathlib

import discord
from discord.ext import commands
from dotenv import load_dotenv

import balaambot.config

load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(
    command_prefix="!",
    case_insensitive=True,
    intents=intents,
    description="A bot for the NaughtyBoys",
)

BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")


@bot.event
async def on_ready() -> None:
    """Call when the bot is ready; synchronizes slash commands with Discord."""
    await bot.tree.sync()
    logger.info("Logged in as %s", bot.user)


async def load_extensions() -> None:
    """Load all the available bot extensions."""
    commands_path = pathlib.Path(__file__).parent / "bot_commands"
    extension_files = sorted(commands_path.glob("*.py"), key=lambda f: f.name)
    if len(extension_files) == 0:
        logger.fatal(
            "No extensions found to load. Please double check the paths are correct."
        )

    for ext_file in extension_files:
        if ext_file.name != "__init__.py":
            ext_path = f"balaambot.bot_commands.{ext_file.stem}"
            logger.info("Loading extension: %s", ext_path)
            await bot.load_extension(ext_path)


def start() -> None:
    """Entrypoint for the bot; schedules extension loading and runs the bot."""
    if BOT_TOKEN is None or BOT_TOKEN == "":
        msg = "DISCORD_BOT_TOKEN environment variable is not set."
        raise ValueError(msg)
    # Docker volume to hold all persistent data
    if not balaambot.config.PERSISTENT_DATA_DIRECTORY.exists():
        balaambot.config.PERSISTENT_DATA_DIRECTORY.mkdir()
    asyncio.run(load_extensions())
    logger.info("Starting bot...")
    bot.run(BOT_TOKEN)


if __name__ == "__main__":
    start()
