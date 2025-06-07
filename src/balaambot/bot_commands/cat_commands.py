import logging
import random

import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger(__name__)


class CatCommands(commands.Cog):
    """Slash commands for cat interactions."""

    def __init__(self, bot: commands.Bot) -> None:
        """Initialize the CatCommands cog."""
        self.bot = bot
        self.cats = {}

    @app_commands.command(name="adopt", description="Adopt a new cat!")
    @app_commands.describe(cat="The cat you want to pet")
    async def adopt_cat(self, interaction: discord.Interaction, cat: str) -> None:
        """Try to pet a cat with a chance to fail."""
        logger.info("Received adopt_cat command from: %s", interaction.user)
        cat_id = cat.strip().lower()
        if cat_id in self.cats:
            await interaction.response.send_message(
                f"You already have a cat named {cat}!",
            )
            return
        self.cats[cat_id] = cat
        await interaction.response.send_message(
            f"You adopted a new cat called {cat}! :cat: "
        )

    @app_commands.command(name="pet", description="Try to pet one of your cats!")
    @app_commands.describe(cat="The cat you want to pet")
    async def pet_cat(self, interaction: discord.Interaction, cat: str) -> None:
        """Try to pet a cat with a chance to fail."""
        logger.info("Received pet_cat command from: %s", interaction.user)
        cat_id = cat.strip().lower()
        if cat_id not in self.cats:
            await interaction.response.send_message(
                f"You don't have any cats named {cat}."
                f"Please choose from: {', '.join(self.cats)}",
            )
            return
        success = random.choices([True, False], [3, 1])  # noqa: S311
        if success[0]:
            msg = f"You successfully petted {cat}! They love it! :heart_eyes_cat:"
        else:
            msg = f"{cat} ran away before you could pet it!"
        await interaction.response.send_message(msg)


async def setup(bot: commands.Bot) -> None:
    """Load the CatCommands cog."""
    logger.info("Loading CatCommands cog")
    await bot.add_cog(CatCommands(bot))
