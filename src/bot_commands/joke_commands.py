import logging
from http import HTTPStatus

import aiohttp
import discord
import pyjokes  # type: ignore # noqa: PGH003
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger(__name__)


class JokeCommands(commands.Cog):
    """Slash commands for telling bad jokes."""

    def __init__(self, bot: commands.Bot) -> None:
        """Initialize the JokeCommands cog."""
        self.bot = bot

    @app_commands.command(name="joke", description="Get a random joke")
    async def get_joke(self, interaction: discord.Interaction) -> None:
        """Gets a random joke."""
        logger.info("Received get_joke command from: %s", interaction.user)
        joke = pyjokes.get_joke()
        await interaction.response.send_message(joke, ephemeral=False)

    @app_commands.command(name="meme", description="Get a random meme image")
    async def get_meme(self, interaction: discord.Interaction) -> None:
        """Sends a random meme image."""
        meme_api = "https://meme-api.com/gimme"
        logger.info("Received get_meme command from: %s", interaction.user)
        async with aiohttp.ClientSession() as session, session.get(meme_api) as resp:
            if resp.status == HTTPStatus.OK:
                data = await resp.json()
                meme_url = data.get("url")
                if meme_url:
                    await interaction.response.send_message(meme_url)
                else:
                    await interaction.response.send_message(
                        "Couldn't fetch a meme right now.", ephemeral=True
                    )
            else:
                await interaction.response.send_message(
                    "Failed to fetch meme from API.", ephemeral=True
                )


async def setup(bot: commands.Bot) -> None:
    """Load the JokeCommands cog."""
    logger.info("Loading JokeCommands cog")
    await bot.add_cog(JokeCommands(bot))
