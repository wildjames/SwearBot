import asyncio
import contextlib
import logging
import random
import uuid
from pathlib import Path

import anyio
import discord

import utils

# Load all sound files from the sounds directory
SOUND_FILES = [str(p) for p in Path("sounds").rglob("*") if p.is_file()]
logger = logging.getLogger(__name__)
logger.info(
    "Loaded %d sound files from %s", len(SOUND_FILES), Path("sounds").absolute()
)

# Track active jobs:
#   job_id -> (VoiceClient, asyncio.Task, sound_file, min_interval, max_interval)
loop_jobs: dict[
    str, tuple[discord.VoiceClient, asyncio.Task[None], str, float, float]
] = {}


async def _play_sfx_loop(vc: discord.VoiceClient, job_id: str) -> None:
    """Internal loop: play the given SFX on its own schedule.

    This function is run in a separate task and will be cancelled when the
    job is removed. It will also stop if the voice client disconnects.
    """
    try:
        while True:
            data = loop_jobs.get(job_id)
            if not data:
                logger.info("SFX job %s not found in guild_id=%s", job_id, vc.guild.id)
                break
            _, _, sound, min_interval, max_interval = data

            if not vc.is_connected():
                logger.info(
                    "SFX job %s: voice client not connected in guild_id=%s",
                    job_id,
                    vc.guild.id,
                )
                await remove_job(job_id)
                return

            wait = random.uniform(min_interval, max_interval)  # noqa: S311
            await asyncio.sleep(wait)

            done_event = anyio.Event()

            def _after_play(done_event: anyio.Event = done_event) -> None:
                done_event.set()

            try:
                mixer = await utils.get_mixer_from_voice_client(vc)
                mixer.play_file(sound, after_play=_after_play)
            except Exception:
                logger.exception("Error playing %s", sound)
                await remove_job(job_id)
                return

            await done_event.wait()
    except asyncio.CancelledError:
        logger.info("SFX job %s cancelled in guild_id=%s", job_id, vc.guild.id)
        raise


async def add_job(
    vc: discord.VoiceClient,
    sound: str,
    min_interval: float,
    max_interval: float,
) -> str:
    """Start a new SFX job for a specific sound and interval; returns job_id."""
    job_id = uuid.uuid4().hex
    task = vc.loop.create_task(_play_sfx_loop(vc, job_id))
    loop_jobs[job_id] = (vc, task, sound, min_interval, max_interval)
    logger.info(
        "Started SFX job %s for sound %s in guild_id=%s", job_id, sound, vc.guild.id
    )
    return job_id


async def remove_job(job_id: str) -> None:
    """Stop and remove the SFX job by its job_id."""
    data = loop_jobs.get(job_id)
    if not data:
        msg = f"No active job with id {job_id}"
        raise KeyError(msg)
    vc, task, sound, *_ = data
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    # Optionally disconnect if no other jobs for this guild remain
    check = [j_vc.guild.id == vc.guild.id for j_vc, *_ in loop_jobs.values()]
    if vc.is_connected() and not any(check):
        await vc.disconnect(force=True)

    del loop_jobs[job_id]
    logger.info(
        "Stopped SFX job %s for sound %s in guild_id=%s", job_id, sound, vc.guild.id
    )


async def ensure_connected(
    guild: discord.Guild, channel: discord.VoiceChannel
) -> discord.VoiceClient:
    """Connect to voice or reuse existing connection."""
    vc = guild.voice_client
    if not vc or not isinstance(vc, discord.VoiceClient) or not vc.is_connected():
        vc = await channel.connect()
    return vc
