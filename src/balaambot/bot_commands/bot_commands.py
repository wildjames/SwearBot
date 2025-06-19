import logging

import discord
from discord import app_commands
from discord.ext import commands

from balaambot.discord_utils import (
    alert_voice_state_update,
    ensure_connected,
    require_voice_channel,
)
from balaambot.sfx.audio_sfx_jobs import stop_all_jobs as sfx_stop
from balaambot.youtube.jobs import stop as yt_stop

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
        channel_member = await require_voice_channel(interaction)
        if channel_member is None:
            return
        channel, _member = channel_member
        guild = channel.guild
        vc = await ensure_connected(guild, channel)

        await sfx_stop(vc)
        await yt_stop(vc)

        await vc.disconnect(force=True)

        logger.info(
            "Bot stopped and left the voice channel for guild_id=%s",
            guild.id,
        )
        await interaction.response.send_message(
            "🔴    Stopped and left the voice channel.",
            ephemeral=False,
        )

    @app_commands.command(name="ping", description="Check if the bot is alive")
    async def ping(self, interaction: discord.Interaction) -> None:
        """Check if the bot is alive."""
        logger.info("Got a ping from: %s", interaction.user)
        await interaction.response.send_message("Pong!", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    """Load the BotControlCommands cog."""
    logger.info("Loading BotControlCommands cog")
    await bot.add_cog(BotControlCommands(bot))
    bot.add_listener(alert_voice_state_update, "on_voice_state_update")
