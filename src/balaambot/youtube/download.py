import asyncio
import logging
from pathlib import Path
from typing import Any

from yt_dlp import DownloadError, YoutubeDL

from balaambot import utils
from balaambot.youtube.metadata import get_youtube_track_metadata
from balaambot.youtube.utils import (
    DEFAULT_CHANNELS,
    DEFAULT_SAMPLE_RATE,
    get_cache_path,
    get_temp_paths,
)

logger = logging.getLogger(__name__)

# Locks to prevent multiple simultaneous downloads of the same URL
_download_locks: dict[str, asyncio.Lock] = {}


async def fetch_audio_pcm(
    url: str,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    channels: int = DEFAULT_CHANNELS,
    username: str | None = None,
    password: str | None = None,
) -> Path:
    """Audio fetching. Cache check, download via yt-dlp, then convert to PCM."""
    cache_path = get_cache_path(url, sample_rate, channels)
    if cache_path.exists():
        return cache_path

    lock = _download_locks.setdefault(url, asyncio.Lock())
    async with lock:
        if cache_path.exists():
            return cache_path

        opus_tmp, pcm_tmp = get_temp_paths(url)

        try:
            await asyncio.gather(
                _download_opus(url, opus_tmp, username=username, password=password),
                get_youtube_track_metadata(url),
            )
        except DownloadError as e:
            logger.exception("yt-dlp failed to download %s", url)
            msg = f"Failed to download audio for {url}"
            raise RuntimeError(msg) from e

        await _convert_opus_to_pcm(opus_tmp, pcm_tmp, cache_path, sample_rate, channels)

        return cache_path


# Helper for when running blocking download in thread
def _sync_download(opts: dict[str, Any], target_url: str) -> None:
    YoutubeDL(opts).download([target_url])  # type: ignore[no-typing]


async def _download_opus(
    url: str,
    opus_tmp: Path,
    username: str | None = None,
    password: str | None = None,
) -> None:
    """Use yt-dlp to download and extract audio as opus into ``opus_tmp``."""
    if username or password:
        msg = "YouTube authentication is not implemented yet."
        raise NotImplementedError(msg)

    opus_tmp.parent.mkdir(parents=True, exist_ok=True)

    ydl_opts: dict[str, Any] = {
        "logger": logger,
        "format": "bestaudio/best",
        "quiet": True,
        "noprogress": True,
        "nocheckcertificate": True,
        "ignoreerrors": True,
        "noplaylist": True,
        "no_warnings": True,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "opus",
            }
        ],
        "outtmpl": str(opus_tmp.with_suffix("")),
    }

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(utils.FUTURES_EXECUTOR, _sync_download, ydl_opts, url)

    final_opus = opus_tmp.with_suffix(".opus")
    if not final_opus.exists():
        msg = f"yt-dlp failed to produce {final_opus}"
        raise RuntimeError(msg)
    final_opus.replace(opus_tmp)


async def _convert_opus_to_pcm(
    opus_tmp: Path,
    pcm_tmp: Path,
    cache_path: Path,
    sample_rate: int,
    channels: int,
) -> None:
    """Convert a downloaded opus file to PCM and move to cache."""
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(opus_tmp),
        "-f",
        "s16le",
        "-acodec",
        "pcm_s16le",
        "-ac",
        str(channels),
        "-ar",
        str(sample_rate),
        str(pcm_tmp),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _out, err = await proc.communicate()
    opus_tmp.unlink(missing_ok=True)
    if proc.returncode != 0:
        pcm_tmp.unlink(missing_ok=True)
        msg = f"ffmpeg failed: {err.decode(errors='ignore')}"
        raise RuntimeError(msg)

    pcm_tmp.replace(cache_path)


# === Synchronous wrappers used by worker threads ===


def download_and_convert(  # noqa: PLR0913
    logger: logging.Logger,
    url: str,
    opus_tmp: Path,
    pcm_tmp: Path,
    cache_path: Path,
    sample_rate: int,
    channels: int,
) -> None:
    """Blocking helper to download and convert a YouTube URL."""

    async def _do() -> None:
        await _download_opus(url, opus_tmp)
        await _convert_opus_to_pcm(opus_tmp, pcm_tmp, cache_path, sample_rate, channels)

    logger.info("Downloading audio for url: '%s'", url)
    asyncio.run(_do())
    logger.info("Finished downloading '%s'", url)


def get_metadata(logger: logging.Logger, url: str) -> dict[str, Any]:
    """Blocking helper to fetch metadata for ``url``."""

    async def _do() -> dict[str, Any]:
        return await get_youtube_track_metadata(url)

    logger.info("Fetching metadata for %s", url)
    return asyncio.run(_do())
