import json
import logging
import pathlib
import random

import discord
import pydantic
from discord import app_commands
from discord.ext import commands

import balaambot.config

logger = logging.getLogger(__name__)

SAVE_FILE = pathlib.Path(balaambot.config.PERSISTENT_DATA_DIR) / "cats.json"
MSG_NO_CAT = (
    "You don't have any cats yet! :crying_cat_face: Try adopting one with `/adopt`!"
)


class Cat(pydantic.BaseModel):
    """Data representing a cat."""

    name: str


class CatCommands(commands.Cog):
    """Slash commands for cat interactions."""

    def __init__(self, bot: commands.Bot) -> None:
        """Initialize the CatCommands cog."""
        self.bot = bot
        self.cats = self.load_cats()

    @app_commands.command(name="adopt", description="Adopt a new cat for the server!")
    @app_commands.describe(cat="The name of the cat to adopt")
    async def adopt_cat(self, interaction: discord.Interaction, cat: str) -> None:
        """Creates and saves a new pet cat."""
        logger.info("Received adopt_cat command: %s (cat: %s)", interaction.user, cat)
        cat_id = cat.strip().lower()
        if cat_id in self.cats:
            await interaction.response.send_message(
                f"We already have a cat named {cat}!",
            )
            return
        # Make a new cat and save it
        self.cats[cat_id] = Cat(name=cat)
        self.save_cats(self.cats)

        await interaction.response.send_message(
            f"You adopted a new cat called {cat}! :cat:"
        )

    @app_commands.command(name="pet", description="Try to pet one of our cats!")
    @app_commands.describe(cat="The name of the cat you want to pet")
    async def pet_cat(self, interaction: discord.Interaction, cat: str) -> None:
        """Try to pet a cat with a chance to fail."""
        logger.info(
            "Received pet_cat command from: %s (cat: %s)", interaction.user, cat
        )
        cat_id = cat.strip().lower()
        if cat_id not in self.cats:
            if self.cats:
                await interaction.response.send_message(
                    f"We don't have any cats named {cat}. "
                    f"We have these:\n{self.get_cat_names()}.",
                )
            else:
                await interaction.response.send_message(MSG_NO_CAT)
            return
        cat_name = self.cats[cat_id].name
        success = random.choices([True, False], [3, 1])  # noqa: S311
        if success[0]:
            msg = f"You successfully petted {cat_name}! They love it! :heart_eyes_cat:"
        else:
            msg = f"{cat_name} ran away before you could pet them!"
        await interaction.response.send_message(msg)

    @app_commands.command(name="list_cats", description="See all of our cats!")
    async def list_cats(self, interaction: discord.Interaction) -> None:
        """List all of the server's cats."""
        logger.info("Received list_cats command from: %s", interaction.user)
        if not self.cats:
            await interaction.response.send_message(
                MSG_NO_CAT,
            )
            return
        await interaction.response.send_message(
            f"We currently have these cats:\n{self.get_cat_names()}",
        )

    def load_cats(self) -> dict[str, Cat]:
        """Load cats from the save file."""
        cats = {}
        if SAVE_FILE.exists():
            with SAVE_FILE.open("r") as f:
                try:
                    cat_data = json.load(f)
                    cats = {k: Cat(**v) for k, v in cat_data.items()}
                    logger.info("Loaded %d cat(s) from %s", len(cats), SAVE_FILE)
                except json.JSONDecodeError:
                    logger.exception("Failed to decode JSON from %s", SAVE_FILE)
        else:
            logger.info("No save file found at %s", SAVE_FILE)
        return cats

    def save_cats(self, cats: dict[str, Cat]) -> None:
        """Save cats to the save file."""
        if not SAVE_FILE.exists():
            logger.info("No save file found, creating a new one.")
            SAVE_FILE.touch()
        # Convert each Cat model to a dict
        cats_dict = {k: v.model_dump() for k, v in cats.items()}
        with SAVE_FILE.open("w") as f:
            json.dump(cats_dict, f, indent=4)
        logger.info("Saved %d cat(s) to %s", len(cats_dict), SAVE_FILE)

    def get_cat_names(self) -> str:
        """Get a formatted list of cat names."""
        if not self.cats:
            return MSG_NO_CAT
        return "\n".join(f"- {cat.name}" for cat in self.cats.values())


async def setup(bot: commands.Bot) -> None:
    """Load the CatCommands cog."""
    logger.info("Loading CatCommands cog")
    await bot.add_cog(CatCommands(bot))
