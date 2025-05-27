import logging

import discord
import pyjokes  # type: ignore # noqa: PGH003
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger(__name__)


class JokeCommands(commands.Cog):
    """Slash commands for YouTube queue and playback."""

    def __init__(self, bot: commands.Bot) -> None:
        """Initialize the JokeCommands cog."""
        self.bot = bot

    @app_commands.command(name="joke", description="Get a random joke")
    async def get_joke(self, interaction: discord.Interaction) -> None:
        """Gets a random joke."""
        logger.info("Received get_joke command from: %s", interaction.user)
        joke = pyjokes.get_joke()
        await interaction.response.send_message(joke, ephemeral=False)


async def setup(bot: commands.Bot) -> None:
    """Load the JokeCommands cog."""
    logger.info("Loading JokeCommands cog")
    await bot.add_cog(JokeCommands(bot))
