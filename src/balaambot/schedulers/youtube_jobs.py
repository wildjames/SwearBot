import logging

from balaambot import discord_utils

# TODO: This should maintain a "playing" state so we can pause and resume playback

# Mapping from voice client to its queue of YouTube URLs
# The key is the guild ID, and the value is a list of URLs.
youtube_queue: dict[int, list[str]] = {}

logger = logging.getLogger(__name__)


async def add_to_queue(vc: discord_utils.DISCORD_VOICE_CLIENT, url: str) -> None:
    """Add a YouTube URL to the playback queue for the given voice client.

    If nothing is playing, start playback immediately.
    """
    queue = youtube_queue.setdefault(vc.guild.id, [])
    queue.append(url)
    logger.info(
        "Queued URL %s for guild_id=%s (queue length=%d)", url, vc.guild.id, len(queue)
    )

    # If this is the only item, start playback
    if len(queue) == 1:
        logger.info("Queue created for guild_id=%s, starting playback", vc.guild.id)

        # Start playback immediately
        try:
            vc.loop.create_task(_play_next(vc))
        except Exception:
            logger.exception("Failed to start playback for guild_id=%s", vc.guild.id)
            # If we fail to start playback, we should clear the queue
            youtube_queue.pop(vc.guild.id, None)
            raise


async def _play_next(vc: discord_utils.DISCORD_VOICE_CLIENT) -> None:
    """Internal: play the next URL in the queue for vc, if any."""
    queue = youtube_queue.get(vc.guild.id)
    logger.info("Queue length for guild_id=%s: %d", vc.guild.id, len(queue or []))

    if not queue:
        logger.info("No more tracks in queue for guild_id=%s", vc.guild.id)
        youtube_queue.pop(vc.guild.id, None)
        return

    url = queue[0]
    logger.info("Starting playback of %s for guild_id=%s", url, vc.guild.id)

    def _after_play(_err: Exception | None = None) -> None:
        if _err:
            logger.error(
                "Error playing YouTube URL %s for guild_id=%s: %s",
                url,
                vc.guild.id,
                _err,
            )
            raise _err

        # Remove the URL from the queue after playback
        youtube_queue[vc.guild.id].pop(0)

        # If the queue is now empty, remove the guild entry
        if not youtube_queue[vc.guild.id]:
            youtube_queue.pop(vc.guild.id, None)
            logger.info("Queue empty for guild_id=%s, removed queue", vc.guild.id)

        # Schedule the next track when this one finishes
        logger.info("Finished playing %s for guild_id=%s", url, vc.guild.id)
        try:
            vc.loop.create_task(_play_next(vc))
        except Exception:
            logger.exception(
                "Failed to schedule next track for guild_id=%s", vc.guild.id
            )

    try:
        mixer = await discord_utils.get_mixer_from_voice_client(vc)
        await mixer.play_youtube(url, after_play=_after_play)
        # After transmitting silence, discord stops calling the read() method.
        # So, we need to call the play method again to get it going again.
        if not vc.is_playing():
            vc.play(mixer)
    except Exception:
        logger.exception("Error playing YouTube URL %s", url)
        # Clear the queue to avoid infinite retries
        youtube_queue.pop(vc.guild.id, None)


def get_current_track(vc: discord_utils.DISCORD_VOICE_CLIENT) -> str | None:
    """Get the currently playing YouTube URL for the voice client."""
    queue = youtube_queue.get(vc.guild.id)
    if queue and len(queue) > 0:
        return queue[0]
    return None


async def skip(vc: discord_utils.DISCORD_VOICE_CLIENT) -> None:
    """Skip the current track and play the next in queue."""
    mixer = await discord_utils.get_mixer_from_voice_client(vc)
    try:
        # This triggers the after_play callback which will handle the next track
        logger.info("Skipping current track for guild_id=%s", vc.guild.id)
        mixer.skip_current_tracks()
    except Exception:
        logger.exception("Error stopping current track for guild_id=%s", vc.guild.id)


async def clear_queue(vc: discord_utils.DISCORD_VOICE_CLIENT) -> None:
    """Clear all queued tracks for the voice client. Excludes current playback."""
    if vc.guild.id in youtube_queue:
        # Remove all but the currently playing track
        youtube_queue[vc.guild.id] = youtube_queue[vc.guild.id][:1]
        logger.info("Cleared YouTube queue for guild_id=%s", vc.guild.id)


async def list_queue(vc: discord_utils.DISCORD_VOICE_CLIENT) -> list[str]:
    """Return the list of queued URLs for the voice client."""
    return list(youtube_queue.get(vc.guild.id, []))


async def stop(vc: discord_utils.DISCORD_VOICE_CLIENT) -> None:
    """Stop playback and clear the queue."""
    # Stop current playback
    mixer = await discord_utils.get_mixer_from_voice_client(vc)
    try:
        mixer.clear_tracks()
        mixer.pause()
    except Exception:
        logger.exception("Error stopping playback for guild_id=%s", vc.guild.id)
    # Remove queue
    youtube_queue.pop(vc.guild.id, None)
