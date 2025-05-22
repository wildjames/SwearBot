import asyncio
import contextlib
import logging
import random

import anyio
import discord

# Configuration
SOUND_FILES = [
    "sounds/mlg/Damn Son Where_d You Find This - MLG Sound Effect (HD) ( 160kbps ).mp3",
    "sounds/mlg/OH BABY A TRIPLE - MLG Sound Effects (HD) ( 160kbps ).mp3",
    "sounds/mlg/MLG Horns - MLG Sound Effects (HD) ( 160kbps ).mp3",
]
MIN_INTERVAL = 5
MAX_INTERVAL = 30

logger = logging.getLogger(__name__)

# Track active loops per guild: guild_id -> (VoiceClient, asyncio.Task)
loop_tasks: dict[int, tuple[discord.VoiceClient, asyncio.Task[None]]] = {}


async def _play_sfx_loop(vc: discord.VoiceClient) -> None:
    """Internal loop: play random SFX until cancelled."""
    try:
        while True:
            wait = random.uniform(MIN_INTERVAL, MAX_INTERVAL)  # noqa: S311
            await asyncio.sleep(wait)

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
        logger.info("SFX loop cancelled for guild_id=%s", vc.guild.id)
        raise


async def start_loop(vc: discord.VoiceClient) -> None:
    """Start the SFX loop on a connected VoiceClient."""
    guild_id = vc.guild.id
    if guild_id in loop_tasks:
        err = "Loop already running for this guild"
        raise RuntimeError(err)

    task = vc.loop.create_task(_play_sfx_loop(vc))
    loop_tasks[guild_id] = (vc, task)
    logger.info("Started SFX loop for guild_id=%s", guild_id)


async def stop_loop(guild: discord.Guild) -> None:
    """Stop and remove the SFX loop for a guild."""
    guild_id = guild.id
    data = loop_tasks.get(guild_id)
    if not data:
        err = "No active loop for this guild"
        raise KeyError(err)

    vc, task = data
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    if vc.is_connected():
        await vc.disconnect(force=True)

    del loop_tasks[guild_id]
    logger.info("Stopped SFX loop for guild_id=%s", guild_id)


async def trigger_sfx(vc: discord.VoiceClient) -> str:
    """Play one random SFX immediately. Returns the filename."""
    sfx = random.choice(SOUND_FILES)  # noqa: S311
    vc.play(
        discord.FFmpegPCMAudio(sfx),
        after=lambda e: logger.info("Finished %s: %s", sfx, e),
    )
    logger.info("Triggered SFX %s on guild_id=%s", sfx, vc.guild.id)
    return sfx


async def ensure_connected(
    guild: discord.Guild, channel: discord.VoiceChannel
) -> discord.VoiceClient:
    """Connect to voice or reuse existing connection."""
    vc = guild.voice_client
    if not vc or not isinstance(vc, discord.VoiceClient) or not vc.is_connected():
        vc = await channel.connect()
    return vc
