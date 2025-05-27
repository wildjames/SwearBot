import asyncio
import logging
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

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
    for ext in [
        "src.bot_commands.sfx_commands",
        "src.bot_commands.music_commands",
        "src.bot_commands.bot_commands",
    ]:
        await bot.load_extension(ext)


def start() -> None:
    """Entrypoint for the bot; schedules extension loading and runs the bot."""
    if BOT_TOKEN is None or BOT_TOKEN == "":
        msg = "DISCORD_BOT_TOKEN environment variable is not set."
        raise ValueError(msg)

    asyncio.run(load_extensions())
    logger.info("Starting bot...")
    bot.run(BOT_TOKEN)


if __name__ == "__main__":
    start()
