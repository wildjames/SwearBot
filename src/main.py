import asyncio
import contextlib
import logging
import os
import random
from typing import cast

import anyio
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Bot permissions
intents = discord.Intents.default()
intents.voice_states = True

bot = commands.Bot(command_prefix="!", case_insensitive=True, intents=intents)

# Configuration
SOUND_FILES = [
    "sounds/mlg/Damn Son Where_d You Find This - MLG Sound Effect (HD) ( 160kbps ).mp3",
    "sounds/mlg/OH BABY A TRIPLE - MLG Sound Effects (HD) ( 160kbps ).mp3",
    "sounds/mlg/MLG Horns - MLG Sound Effects (HD) ( 160kbps ).mp3",
]

MIN_INTERVAL = 5
MAX_INTERVAL = 30

BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not BOT_TOKEN:
    err = "DISCORD_BOT_TOKEN environment variable not set."
    raise ValueError(err)

# Keep track of one loop task per guild:
# guild.id -> (VoiceClient, asyncio.Task)
loop_tasks: dict[int, tuple[discord.VoiceClient, asyncio.Task[None]]] = {}


async def play_sfx_loop(vc: discord.VoiceClient) -> None:
    """Play random sound effects in a loop until cancelled."""
    try:
        while True:
            # Pick a random delay
            wait = random.uniform(MIN_INTERVAL, MAX_INTERVAL)  # noqa: S311
            await asyncio.sleep(wait)

            # Pick and play
            sfx = random.choice(SOUND_FILES)  # noqa: S311
            done_event = anyio.Event()

            def _after_play(
                error: Exception | None, sfx: str = sfx, event: anyio.Event = done_event
            ) -> None:
                if error:
                    logger.error("Error playing %s: %s", sfx, error)
                event.set()

            vc.play(discord.FFmpegPCMAudio(sfx), after=_after_play)
            await done_event.wait()
    except asyncio.CancelledError:
        # Clean up if the task is cancelled
        logger.info("SFX loop cancelled for %s", vc.guild.name)
        raise


@bot.event
async def on_ready() -> None:
    """Call when the bot is ready; synchronizes slash commands with Discord."""
    # Sync slash commands with Discord
    await bot.tree.sync()
    logger.info("Logged in as %s", bot.user)


@bot.tree.command(name="start", description="Start random SFX in your voice channel")
async def start(interaction: discord.Interaction) -> None:
    """Join the user's voice channel and start playing random sound effects."""
    # Ensure this is used in a guild
    if interaction.guild is None:
        await interaction.response.send_message(
            "This command only works in a server.", ephemeral=True
        )
        return

    guild_id = interaction.guild.id

    # Are we already running?
    if guild_id in loop_tasks:
        await interaction.response.send_message(
            "SFX loop is already running in this server!", ephemeral=True
        )
        return

    # Get the member and their voice channel
    member = interaction.guild.get_member(interaction.user.id)
    if not member or not member.voice or not member.voice.channel:
        await interaction.response.send_message(
            "You need to be in a voice channel to start the loop.", ephemeral=True
        )
        return

    # Connect (or reuse existing VC)
    vc = interaction.guild.voice_client
    if not vc or not (isinstance(vc, discord.VoiceClient) and vc.is_connected()):
        vc = await member.voice.channel.connect()

    # Spin up the loop
    task = bot.loop.create_task(play_sfx_loop(vc))
    loop_tasks[guild_id] = (vc, task)

    await interaction.response.send_message(
        f"🎶 Started SFX loop in **{member.voice.channel.name}**.", ephemeral=True
    )


@bot.tree.command(name="stop", description="Stop the random SFX loop")
async def stop(interaction: discord.Interaction) -> None:
    """Stop the random sound effect loop and disconnect from the voice channel."""
    if interaction.guild is None:
        await interaction.response.send_message(
            "This command only works in a server.", ephemeral=True
        )
        return

    guild_id = interaction.guild.id
    data = loop_tasks.get(guild_id)
    if not data:
        await interaction.response.send_message(
            "No SFX loop is currently running here.", ephemeral=True
        )
        return

    vc, task = data

    # Cancel loop, disconnect
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    if vc.is_connected():
        await vc.disconnect(force=True)

    del loop_tasks[guild_id]
    await interaction.response.send_message(
        "Stopped the SFX loop and left the channel.", ephemeral=True
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
    sfx = random.choice(SOUND_FILES)  # noqa: S311

    vc = cast("discord.VoiceClient", vc)
    vc.play(
        discord.FFmpegPCMAudio(sfx),
        after=lambda e: logger.info("Finished %s: %s", sfx, e),
    )
    await interaction.followup.send(f"🔊 Playing **{sfx}**!", ephemeral=True)


# Run the bot
bot.run(BOT_TOKEN)
