import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands

from src import discord_utils
from src.audio_handlers import youtube_audio
from src.schedulers import youtube_jobs

logger = logging.getLogger(__name__)


class MusicCommands(commands.Cog):
    """Slash commands for YouTube queue and playback."""

    def __init__(self, bot: commands.Bot) -> None:
        """Initialize the MusicCommands cog."""
        self.bot = bot

    @app_commands.command(
        name="play", description="Enqueue and play a YouTube video audio"
    )
    @app_commands.describe(url="YouTube video URL")
    async def play(self, interaction: discord.Interaction, url: str) -> None:
        """Enqueue a YouTube URL; starts playback if idle."""
        await interaction.response.defer(thinking=True, ephemeral=False)

        url = url.strip()
        if not youtube_audio.is_valid_youtube_url(url):
            return await interaction.followup.send(
                "Invalid YouTube URL. Please provide a valid link.", ephemeral=True
            )

        logger.info("Received play command for URL: %s", url)
        self.bot.loop.create_task(self._do_play(interaction, url))

        return None

    async def _do_play(self, interaction: discord.Interaction, url: str) -> None:
        if interaction.guild is None:
            return await interaction.followup.send(
                "This command can only be used in a server.", ephemeral=True
            )

        member = interaction.guild.get_member(interaction.user.id)
        if (
            not member
            or not member.voice
            or not isinstance(member.voice.channel, discord.VoiceChannel)
        ):
            return await interaction.followup.send(
                "Join a voice channel first.", ephemeral=True
            )

        # TODO: If this is not a valid YouTube URL, we should handle it gracefully

        vc = await discord_utils.ensure_connected(
            interaction.guild,
            member.voice.channel,
        )
        mixer = await discord_utils.get_mixer_from_voice_client(vc)

        # download and cache in background
        fetch_task = asyncio.create_task(
            youtube_audio.fetch_audio_pcm(
                url,
                sample_rate=mixer.SAMPLE_RATE,
                channels=mixer.CHANNELS,
            )
        )

        # Add to queue. Playback (in mixer) will await cache when it's time
        await youtube_jobs.add_to_queue(vc, url)

        track_name = youtube_audio.get_youtube_track_name(url) or url
        queue = await youtube_jobs.list_queue(vc)
        pos = len(queue)
        msg = (
            f"🎵    Queued **{track_name}** at position {pos}."
            if pos > 1
            else f"▶️    Now playing **{track_name}**"
        )
        await interaction.followup.send(msg)

        # wait for the background fetch to complete (so file is ready later)
        try:
            await fetch_task
        except Exception:
            logger.exception("Failed to fetch audio for %s", url)

    @app_commands.command(name="list_queue", description="List upcoming YouTube tracks")
    async def list_queue(self, interaction: discord.Interaction) -> None:
        """Show the current YouTube queue for this server."""
        if interaction.guild is None:
            await interaction.response.send_message(
                "This command only works in a server.", ephemeral=True
            )
            return
        member = interaction.guild.get_member(interaction.user.id)
        if (
            not member
            or not member.voice
            or not isinstance(member.voice.channel, discord.VoiceChannel)
        ):
            await interaction.response.send_message(
                "You need to be in a standard voice channel to view the queue.",
                ephemeral=True,
            )
            return
        vc = await discord_utils.ensure_connected(
            interaction.guild,
            member.voice.channel,
        )
        upcoming = await youtube_jobs.list_queue(vc)
        if not upcoming:
            msg = "The queue is empty."
        else:
            lines = [
                f"{i + 1}. {youtube_audio.get_youtube_track_name(url)}"
                for i, url in enumerate(upcoming)
            ]
            lines[0] = (
                f"**Now playing:** {youtube_audio.get_youtube_track_name(upcoming[0])}"
            )
            msg = "**Upcoming tracks:**\n" + "\n".join(lines)
        await interaction.response.send_message(msg, ephemeral=True)

    @app_commands.command(name="skip", description="Skip the current YouTube track")
    async def skip(self, interaction: discord.Interaction) -> None:
        """Stop current track and play next in queue."""
        if interaction.guild is None:
            await interaction.response.send_message(
                "This command only works in a server.", ephemeral=True
            )
            return
        member = interaction.guild.get_member(interaction.user.id)
        if (
            not member
            or not member.voice
            or not isinstance(member.voice.channel, discord.VoiceChannel)
        ):
            await interaction.response.send_message(
                "You need to be in a standard voice channel to skip audio.",
                ephemeral=True,
            )
            return
        vc = await discord_utils.ensure_connected(
            interaction.guild,
            member.voice.channel,
        )
        await youtube_jobs.skip(vc)
        logger.info("Skipped track for guild_id=%s", interaction.guild.id)

        track_url = youtube_jobs.get_current_track(vc)
        if not track_url:
            await interaction.response.send_message(
                "No track is currently playing.", ephemeral=True
            )
            return

        track_name = youtube_audio.get_youtube_track_name(track_url)
        await interaction.response.send_message(
            f"⏭️    Skipped to next track: {track_name}",
            ephemeral=False,
        )

    @app_commands.command(
        name="stop_music",
        description="Stop playback and clear YouTube queue",
    )
    async def stop_music(self, interaction: discord.Interaction) -> None:
        """Stop the current YouTube track and clear all queued tracks."""
        if interaction.guild is None:
            await interaction.response.send_message(
                "This command only works in a server.", ephemeral=True
            )
            return
        member = interaction.guild.get_member(interaction.user.id)
        if (
            not member
            or not member.voice
            or not isinstance(member.voice.channel, discord.VoiceChannel)
        ):
            await interaction.response.send_message(
                "You need to be in a standard voice channel to stop music.",
                ephemeral=True,
            )
            return
        vc = await discord_utils.ensure_connected(
            interaction.guild,
            member.voice.channel,
        )
        await youtube_jobs.stop(vc)
        await interaction.response.send_message(
            "⏹️    Stopped and cleared YouTube queue.", ephemeral=False
        )

    @app_commands.command(name="clear_queue", description="Clear the YouTube queue")
    async def clear_queue(self, interaction: discord.Interaction) -> None:
        """Remove all queued YouTube tracks."""
        if interaction.guild is None:
            await interaction.response.send_message(
                "This command only works in a server.", ephemeral=True
            )
            return
        member = interaction.guild.get_member(interaction.user.id)
        if (
            not member
            or not member.voice
            or not isinstance(member.voice.channel, discord.VoiceChannel)
        ):
            await interaction.response.send_message(
                "You need to be in a standard voice channel to clear the queue.",
                ephemeral=True,
            )
            return
        vc = await discord_utils.ensure_connected(
            interaction.guild, member.voice.channel
        )
        logger.info("Clearing YouTube queue for guild_id=%s", interaction.guild.id)

        # Clear the queue
        await youtube_jobs.clear_queue(vc)
        current_queue = await youtube_jobs.list_queue(vc)
        logger.info("queue after clearing: %s", current_queue)

        await interaction.response.send_message(
            "🗑️    Cleared the YouTube queue.", ephemeral=False
        )


async def setup(bot: commands.Bot) -> None:
    """Load the MusicCommands cog."""
    logger.info("Loading MusicCommands cog")
    await bot.add_cog(MusicCommands(bot))
