import logging
import os
import random
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from src import discord_utils
from src.audio_handlers import youtube_audio
from src.schedulers import audio_sfx_jobs, youtube_jobs

load_dotenv()

# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Bot permissions
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
if not BOT_TOKEN:
    msg = "DISCORD_BOT_TOKEN environment variable is not set."
    raise ValueError(msg)


YOUTUBE_USERNAME = os.getenv("YOUTUBE_USERNAME", None)
YOUTUBE_PASSWORD = os.getenv("YOUTUBE_PASSWORD", None)


@bot.event
async def on_ready() -> None:
    """Call when the bot is ready; synchronizes slash commands with Discord."""
    await bot.tree.sync()
    logger.info("Logged in as %s", bot.user)


# ------------ SFX Commands ------------


@bot.tree.command(
    name="add_sfx",
    description="Add a scheduled SFX job",
)
@app_commands.describe(
    sound="Filename of the sound effect (including extension)",
    min_interval="Minimum seconds between plays",
    max_interval="Maximum seconds between plays",
)
async def add_sfx(
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

    vc = await discord_utils.ensure_connected(interaction.guild, member.voice.channel)
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


@bot.tree.command(name="remove_sfx", description="Remove a scheduled SFX job")
@app_commands.describe(job_id="The ID of the job to remove")
async def remove_sfx(interaction: discord.Interaction, job_id: str) -> None:
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


@bot.tree.command(name="list_sfx_jobs", description="List active SFX jobs")
async def list_sfx_jobs(interaction: discord.Interaction) -> None:
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


@bot.tree.command(name="list_sfx", description="List available sound effects")
async def list_sfx(interaction: discord.Interaction) -> None:
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


@bot.tree.command(name="trigger_sfx", description="Manually play a random sound effect")
async def trigger_sfx(interaction: discord.Interaction) -> None:
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


# ------------ YouTube Queue Commands ------------


@bot.tree.command(name="play", description="Enqueue and play a YouTube video audio")
@app_commands.describe(
    url="YouTube video URL",
)
async def play(
    interaction: discord.Interaction,
    url: str,
) -> None:
    """Enqueue a YouTube URL; starts playback if idle."""
    try:
        await interaction.response.defer(thinking=True, ephemeral=False)
    except discord.NotFound:
        # if this ever fires, the interaction token already expired
        return

    bot.loop.create_task(_do_play(interaction, url))


async def _do_play(interaction: discord.Interaction, url: str) -> None:
    """Helper function to handle the play command logic.

    This is so I can use asyncio.create_task to run it in the background,
    allowing the interaction to complete without blocking. This is necessary
    because the YouTube audio extraction can take a while to download.

    Args:
        interaction: The Discord interaction that triggered the command.
        url: The YouTube video URL to play.

    Returns:
        None

    """
    if interaction.guild is None:
        return await interaction.followup.send(
            "This command can only be used in a server.", ephemeral=False
        )
    member = interaction.guild.get_member(interaction.user.id)
    if (
        not member
        or not member.voice
        or not isinstance(member.voice.channel, discord.VoiceChannel)
    ):
        return await interaction.followup.send(
            "You need to be in a standard voice channel to play audio.", ephemeral=True
        )

    vc = await discord_utils.ensure_connected(interaction.guild, member.voice.channel)

    try:
        await youtube_jobs.add_to_queue(vc, url)
        track_name = youtube_audio.get_youtube_track_name(url)

        queue = await youtube_jobs.list_queue(vc)
        position = len(queue)
        msg = (
            f"🎵 Queued **{track_name}** at position {position}."
            if position > 1
            else f"▶️ Now playing **{track_name}**"
        )
        await interaction.followup.send(msg, ephemeral=False)

    except Exception as e:
        logger.exception("Error queueing YouTube audio")
        await interaction.followup.send(f"Failed to queue audio: {e}", ephemeral=True)


@bot.tree.command(name="list_queue", description="List upcoming YouTube tracks")
async def list_queue(interaction: discord.Interaction) -> None:
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
    vc = await discord_utils.ensure_connected(interaction.guild, member.voice.channel)
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


@bot.tree.command(name="skip", description="Skip the current YouTube track")
async def skip(interaction: discord.Interaction) -> None:
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
    vc = await discord_utils.ensure_connected(interaction.guild, member.voice.channel)
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
        f"⏭️ Skipped to next track: {track_name}",
        ephemeral=False,
    )


@bot.tree.command(name="stopmusic", description="Stop playback and clear YouTube queue")
async def stopmusic(interaction: discord.Interaction) -> None:
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
            "You need to be in a standard voice channel to stop music.", ephemeral=True
        )
        return
    vc = await discord_utils.ensure_connected(interaction.guild, member.voice.channel)
    await youtube_jobs.stop(vc)
    await interaction.response.send_message(
        "⏹️ Stopped and cleared YouTube queue.", ephemeral=False
    )


@bot.tree.command(name="clearqueue", description="Clear the YouTube queue")
async def clearqueue(interaction: discord.Interaction) -> None:
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
    vc = await discord_utils.ensure_connected(interaction.guild, member.voice.channel)
    logger.info("Clearing YouTube queue for guild_id=%s", interaction.guild.id)

    # Clear the queue
    await youtube_jobs.clear_queue(vc)
    current_queue = await youtube_jobs.list_queue(vc)
    logger.info("queue after clearing: %s", current_queue)

    await interaction.response.send_message(
        "🗑️ Cleared the YouTube queue.", ephemeral=False
    )


# ------------ Bot Commands ------------


@bot.tree.command(name="stop", description="Stop the bot, and leave the voice channel")
async def stop(interaction: discord.Interaction) -> None:
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
            "You need to be in a standard voice channel to add a job.", ephemeral=True
        )
        return
    vc = await discord_utils.ensure_connected(interaction.guild, member.voice.channel)

    await audio_sfx_jobs.stop_all_jobs(vc)
    await youtube_jobs.stop(vc)

    await vc.disconnect(force=True)

    logger.info(
        "Bot stopped and left the voice channel for guild_id=%s", interaction.guild.id
    )
    await interaction.response.send_message(
        "🔴    Stopped and left the voice channel.",
        ephemeral=False,
    )


@bot.tree.command(name="ping", description="Check if the bot is alive")
async def ping(interaction: discord.Interaction) -> None:
    """Check if the bot is alive."""
    await interaction.response.send_message("Pong!", ephemeral=True)


def start() -> None:
    """Start the bot."""
    if not BOT_TOKEN:
        msg = "DISCORD_BOT_TOKEN environment variable is not set."
        raise ValueError(msg)

    bot.run(
        BOT_TOKEN,
    )


if __name__ == "__main__":
    start()
