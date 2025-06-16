import asyncio
import json
import logging
import subprocess
from pathlib import Path
from typing import Any, cast

from yt_dlp import DownloadError, YoutubeDL

from balaambot import utils
from balaambot.utils import sec_to_string
from balaambot.youtube import metadata
from balaambot.youtube.utils import (
    DEFAULT_CHANNELS,
    DEFAULT_SAMPLE_RATE,
    VideoMetadata,
    get_cache_path,
    get_metadata_path,
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
                metadata.get_youtube_track_metadata(url),
            )
        except DownloadError as e:
            logger.exception("yt-dlp failed to download %s", url)
            msg = f"Failed to download audio for {url}"
            raise RuntimeError(msg) from e

        await _convert_opus_to_pcm(opus_tmp, pcm_tmp, cache_path, sample_rate, channels)

        return cache_path


# Helper for when running blocking download in thread
def _sync_download(opts: dict[str, Any], target_url: str) -> None:
    metadata.YoutubeDL(opts).download([target_url])  # type: ignore[no-typing]


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
    logger.info("Downloading audio for url: '%s'", url)
    outdir = opus_tmp.parent
    base_name = opus_tmp.stem
    outtmpl = outdir / base_name

    ydl_opts: dict[str, Any] = {
        "format": "bestaudio/best",
        "quiet": True,
        "noprogress": True,
        "nocheckcertificate": True,
        "ignoreerrors": True,
        "noplaylist": True,
        "no_warnings": True,
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "opus"}],
        "outtmpl": str(outtmpl),
    }

    with YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    expected_opus = outdir / f"{base_name}.opus"
    if not expected_opus.exists():
        msg = f"yt-dlp failed to produce {expected_opus}"
        raise RuntimeError(msg)

    logger.info("Downloaded '%s' OK. Converting to PCM", url)

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(expected_opus),
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
    proc = subprocess.run(cmd, capture_output=True, check=False)  # noqa: S603
    expected_opus.unlink(missing_ok=True)

    if proc.returncode != 0:
        pcm_tmp.unlink(missing_ok=True)
        msg = f"ffmpeg failed: {proc.stderr.decode(errors='ignore')}"
        raise RuntimeError(msg)

    pcm_tmp.replace(cache_path)
    logger.info("Finished downloading '%s'", url)


def get_metadata(logger: logging.Logger, url: str) -> VideoMetadata:
    """Blocking helper to fetch metadata for ``url`` and cache the JSON."""
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "extract_flat": True,
    }

    logger.info("Fetching metadata for %s", url)
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)  # type: ignore[no-typing]

    if not info:
        msg = "Failed to get youtube metadata"
        raise ValueError(msg)

    title = cast("str", info.get("title")) or url  # type: ignore[no-typing]
    duration_s = cast("int", info.get("duration")) or 0  # type: ignore[no-typing]

    meta: VideoMetadata = VideoMetadata(
        url=url,
        title=title,
        runtime=duration_s,
        runtime_str=sec_to_string(duration_s),
    )

    meta_path = get_metadata_path(url)
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    logger.debug("Cached metadata to %s", meta_path)

    return meta
