import logging
import random
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from src import discord_utils
from src.schedulers import audio_sfx_jobs

logger = logging.getLogger(__name__)


class SFXCommands(commands.Cog):
    """Slash commands for scheduling and triggering SFX jobs."""

    def __init__(self, bot: commands.Bot) -> None:
        """Initialize the SFXCommands cog."""
        self.bot = bot

    @app_commands.command(name="add_sfx", description="Add a scheduled SFX job")
    @app_commands.describe(
        sound="Filename of the sound effect (including extension)",
        min_interval="Minimum seconds between plays",
        max_interval="Maximum seconds between plays",
    )
    async def add_sfx(
        self,
        interaction: discord.Interaction,
        sound: str,
        min_interval: float,
        max_interval: float,
    ) -> None:
        """Add a scheduled sound effect (SFX) job to the server."""
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
        try:
            job_id = await audio_sfx_jobs.add_job(vc, sound, min_interval, max_interval)
            message = (
                f"✅    Added job `{job_id}`: `{sound}` "
                f"every {min_interval:.1f}-{max_interval:.1f}s."
            )
            await interaction.response.send_message(message, ephemeral=True)
        except ValueError as e:
            await interaction.response.send_message(
                f"Failed to add job: {e}", ephemeral=True
            )

    @app_commands.command(name="remove_sfx", description="Remove a scheduled SFX job")
    @app_commands.describe(job_id="The ID of the job to remove")
    async def remove_sfx(self, interaction: discord.Interaction, job_id: str) -> None:
        """Remove a scheduled SFX job using its job identifier."""
        if interaction.guild is None:
            await interaction.response.send_message(
                "This command only works in a server.", ephemeral=True
            )
            return

        try:
            await audio_sfx_jobs.remove_job(job_id)
            await interaction.response.send_message(
                f"🗑️    Removed job `{job_id}`.", ephemeral=True
            )
        except KeyError:
            await interaction.response.send_message(
                f"No job found with ID `{job_id}`.", ephemeral=True
            )

    @app_commands.command(name="list_sfx_jobs", description="List active SFX jobs")
    async def list_sfx_jobs(self, interaction: discord.Interaction) -> None:
        """Send a list of active jobs in the server."""
        if interaction.guild is None:
            await interaction.response.send_message(
                "This command only works in a server.", ephemeral=True
            )
            return

        jobs: list[str] = []
        for jid, (vc, _task, sound, mi, ma) in audio_sfx_jobs.loop_jobs.items():
            if vc.guild.id == interaction.guild.id:
                jobs.append(f"`{jid}`: `{sound}` every {mi:.1f}-{ma:.1f}s")

        if not jobs:
            await interaction.response.send_message(
                "No active jobs in this server.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "**Active jobs:**\n" + "\n".join(jobs), ephemeral=True
            )

    @app_commands.command(name="list_sfx", description="List available sound effects")
    async def list_sfx(self, interaction: discord.Interaction) -> None:
        """List all available sound effects."""
        if interaction.guild is None:
            await interaction.response.send_message(
                "This command only works in a server.", ephemeral=True
            )
            return

        sound_files = audio_sfx_jobs.SOUND_FILES
        if not sound_files:
            await interaction.response.send_message(
                "No sound effects available.", ephemeral=True
            )
            return

        # Format the list of sound files
        formatted_sounds = "\n".join(f"- {Path(sound).name}" for sound in sound_files)
        await interaction.response.send_message(
            f"**Available sound effects:**\n{formatted_sounds}", ephemeral=True
        )

    @app_commands.command(
        name="trigger_sfx",
        description="Manually play a random sound effect",
    )
    async def trigger_sfx(self, interaction: discord.Interaction) -> None:
        """Play a random sound effect in the voice channel."""
        await interaction.response.defer(thinking=True)
        if interaction.guild is None:
            await interaction.followup.send(
                "This command can only be used in a server.", ephemeral=True
            )
            return

        # pick & fire off the effect
        sound = random.choice(audio_sfx_jobs.SOUND_FILES)  # noqa: S311
        mixer = await discord_utils.get_mixer_from_interaction(interaction)
        mixer.play_file(sound)
        await interaction.followup.send(
            f"🔊    Playing **{Path(sound).name}**", ephemeral=False
        )


async def setup(bot: commands.Bot) -> None:
    """Add the SFXCommands cog to the bot."""
    logger.info("Loading SFXCommands cog")
    await bot.add_cog(SFXCommands(bot))
