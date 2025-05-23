import logging  # noqa: I001, RUF100
import os
from typing import cast

import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv

import audio_jobs

load_dotenv()

# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Bot permissions
intents = discord.Intents.default()
intents.voice_states = True

bot = commands.Bot(command_prefix="!", case_insensitive=True, intents=intents)

BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not BOT_TOKEN:
    msg = "DISCORD_BOT_TOKEN environment variable is not set."
    raise ValueError(msg)


@bot.event
async def on_ready() -> None:
    """Call when the bot is ready; synchronizes slash commands with Discord."""
    await bot.tree.sync()
    logger.info("Logged in as %s", bot.user)


@bot.tree.command(name="addjob", description="Add a scheduled SFX job")
@app_commands.describe(
    sound="Filename of the sound effect (including extension)",
    min_interval="Minimum seconds between plays",
    max_interval="Maximum seconds between plays",
)
async def addjob(
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
            "You need to be in a standard voice channel to add a job.", ephemeral=True
        )
        return

    vc = await audio_jobs.ensure_connected(interaction.guild, member.voice.channel)
    try:
        job_id = await audio_jobs.add_job(vc, sound, min_interval, max_interval)
        message = (
            f"✅ Added job `{job_id}`: `{sound}` "
            f"every {min_interval:.1f}-{max_interval:.1f}s."
        )
        await interaction.response.send_message(message, ephemeral=True)
    except ValueError as e:
        await interaction.response.send_message(
            f"Failed to add job: {e}", ephemeral=True
        )


@bot.tree.command(name="removejob", description="Remove a scheduled SFX job")
@app_commands.describe(job_id="The ID of the job to remove")
async def removejob(interaction: discord.Interaction, job_id: str) -> None:
    """Remove a scheduled SFX job using its job identifier."""
    if interaction.guild is None:
        await interaction.response.send_message(
            "This command only works in a server.", ephemeral=True
        )
        return

    try:
        await audio_jobs.remove_job(job_id)
        await interaction.response.send_message(
            f"🗑️ Removed job `{job_id}`.", ephemeral=True
        )
    except KeyError:
        await interaction.response.send_message(
            f"No job found with ID `{job_id}`.", ephemeral=True
        )


@bot.tree.command(name="listjobs", description="List active SFX jobs")
async def listjobs(interaction: discord.Interaction) -> None:
    """Send a list of active jobs in the server."""
    if interaction.guild is None:
        await interaction.response.send_message(
            "This command only works in a server.", ephemeral=True
        )
        return

    jobs: list[str] = []
    for jid, (vc, _task, sound, mi, ma) in audio_jobs.loop_jobs.items():
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


@bot.tree.command(name="ping")
async def ping(interaction: discord.Interaction) -> None:
    """Check if the bot is alive."""
    await interaction.response.send_message("Pong!", ephemeral=True)


@bot.tree.command(name="trigger", description="Manually play a random sound effect")
async def trigger(interaction: discord.Interaction) -> None:
    """Play a random sound effect in the voice channel."""
    await interaction.response.defer(thinking=True)
    if interaction.guild is None:
        await interaction.followup.send(
            "This command can only be used in a server.", ephemeral=True
        )
        return

    vc = interaction.guild.voice_client
    if not vc:
        member = interaction.guild.get_member(interaction.user.id)
        if member and member.voice and member.voice.channel:
            vc = await member.voice.channel.connect()
        else:
            await interaction.followup.send(
                "You need to be in a voice channel (or have me already in one)"
                " to trigger a sound.",
                ephemeral=True,
            )
            return

    vc = cast("discord.VoiceClient", vc)
    sfx = await audio_jobs.trigger_sfx(vc)
    await interaction.followup.send(f"🔊 Playing **{sfx}**!", ephemeral=True)


# Run the bot
bot.run(BOT_TOKEN)
