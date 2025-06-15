import asyncio
import logging
import os
import pathlib

import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(
    command_prefix=commands.when_mentioned_or("!"),
    case_insensitive=True,
    intents=intents,
    description="A bot for the NaughtyBoys",
)


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


async def main() -> None:
    """Main async process that runs the bot."""
    # Check the token is valid
    if DISCORD_BOT_TOKEN is None or DISCORD_BOT_TOKEN == "":
        msg = "DISCORD_BOT_TOKEN environment variable is not set."
        raise ValueError(msg)
    if '"' in DISCORD_BOT_TOKEN:
        msg = (
            "DISCORD_BOT_TOKEN contains invalid characters. "
            'Do not wrap the token in "..." inside the .env file!'
        )
        raise ValueError(msg)
    logger.info("Starting bot...")
    async with bot:
        # Loads all files in bot_commands
        await load_extensions()
        # Start the bot
        await bot.start(DISCORD_BOT_TOKEN)


def start() -> None:
    """Entrypoint for the bot. Starts the main async process."""
    # Bot must be run this way so all tasks run in the same process
    asyncio.run(main())
