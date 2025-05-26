import logging

import discord
from discord import app_commands
from discord.ext import commands

from src import discord_utils
from src.schedulers import audio_sfx_jobs, youtube_jobs

logger = logging.getLogger(__name__)


class BotControlCommands(commands.Cog):
    """Basic control commands like stop and ping."""

    def __init__(self, bot: commands.Bot) -> None:
        """Initialize the BotControlCommands cog."""
        self.bot = bot

    @app_commands.command(
        name="stop", description="Stop the bot, and leave the voice channel"
    )
    async def stop(self, interaction: discord.Interaction) -> None:
        """Stop the bot and leave the voice channel."""
        if interaction.guild is None:
            await interaction.response.send_message(
                "This command only works in a server.", ephemeral=True
            )
            return

        member = interaction.guild.get_member(interaction.user.id)
        if (
            not member
            or not member.voice
            or not member.voice.channel
            or not isinstance(member.voice.channel, discord.VoiceChannel)
        ):
            await interaction.response.send_message(
                "You need to be in a standard voice channel to add a job.",
                ephemeral=True,
            )
            return
        vc = await discord_utils.ensure_connected(
            interaction.guild, member.voice.channel
        )

        await audio_sfx_jobs.stop_all_jobs(vc)
        await youtube_jobs.stop(vc)

        await vc.disconnect(force=True)

        logger.info(
            "Bot stopped and left the voice channel for guild_id=%s",
            interaction.guild.id,
        )
        await interaction.response.send_message(
            "🔴    Stopped and left the voice channel.",
            ephemeral=False,
        )

    @app_commands.command(name="ping", description="Check if the bot is alive")
    async def ping(self, interaction: discord.Interaction) -> None:
        """Check if the bot is alive."""
        await interaction.response.send_message("Pong!", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    """Load the BotControlCommands cog."""
    logger.info("Loading BotControlCommands cog")
    await bot.add_cog(BotControlCommands(bot))
