import asyncio
import json
import logging
from pathlib import Path
from typing import Any, cast

from yt_dlp import DownloadError, YoutubeDL

from balaambot import utils
from balaambot.youtube.utils import (
    DEFAULT_CHANNELS,
    DEFAULT_SAMPLE_RATE,
    VideoMetadata,
    check_is_playlist,
    extract_metadata,
    get_cache_path,
    get_metadata_path,
    get_temp_paths,
    is_valid_youtube_url,
)

logger = logging.getLogger(__name__)


# This will hold the upcoming tracks metadata
youtube_queue: list[VideoMetadata] = []

# Locks to prevent multiple simultaneous downloads of the same URL
_download_locks: dict[str, asyncio.Lock] = {}


async def get_youtube_track_metadata(url: str) -> VideoMetadata:
    """Get the track metadata from a YouTube URL, caching to JSON files."""
    # quick URL validation
    if not is_valid_youtube_url(url):
        msg = "Invalid YouTube URL: %s"
        raise ValueError(msg, url)

    # If it's not in memory, then check the disk
    meta_path = get_metadata_path(url)
    # load from JSON cache if available
    if meta_path.exists():
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        data = cast("VideoMetadata", data)
        logger.info("Loaded metadata from cache: '%s'", meta_path)
        return data

    logger.info("Fetching track metadata for URL: '%s'", url)

    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "extract_flat": True,
    }

    # This should run in a subprocess
    def _extract_info(opts: dict[str, Any], target_url: str) -> dict[str, Any] | None:
        with YoutubeDL(opts) as ydl:
            return ydl.extract_info(target_url, download=False)  # type: ignore[no-typing]

    info = await asyncio.to_thread(_extract_info, ydl_opts, url)

    if not info:
        msg = "Failed to get youtube metadata"
        raise ValueError(msg)

    title = cast("str", info.get("title")) or url  # type: ignore[no-typing]
    duration_s = cast("int", info.get("duration")) or 0  # type: ignore[no-typing]

    meta: VideoMetadata = VideoMetadata(
        url=url,
        title=title,
        runtime=duration_s,
        runtime_str=utils.sec_to_string(duration_s),
    )

    # ensure directory exists and write JSON
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    logger.debug("Cached metadata to %s", meta_path)

    return meta


def fetch_cached_youtube_track_metadata(url: str) -> VideoMetadata:
    """Fetch cached track metadata from the disk. If it's not found, throw an  error."""
    # If it's not in memory, then check the disk
    meta_path = get_metadata_path(url)
    # load from JSON cache if available
    if meta_path.exists():
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        data = cast("VideoMetadata", data)
        logger.info("Loaded metadata from cache: '%s'", meta_path)
        return data

    msg = f"No metadata cached for url '{url}'"
    raise FileNotFoundError(msg)


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

        # download audio and fetch metadata concurrently
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
        # TODO: Dispatch ffmpeg to normalise the volume here

        return cache_path


# Helper for when I run blocking download in thread
def _sync_download(opts: dict[str, Any], target_url: str) -> None:
    YoutubeDL(opts).download([target_url])  # type: ignore[no-typing]


async def _download_opus(
    url: str,
    opus_tmp: Path,
    username: str | None = None,
    password: str | None = None,
) -> None:
    """Use yt-dlp to download and extract audio as opus into opus_tmp."""
    if username or password:
        msg = "YouTube authentication is not implemented yet."
        raise NotImplementedError(msg)

    # Ensure directory exists
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
    # Rename to .part path for consistency
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


async def get_playlist_video_urls(playlist_url: str) -> list[str]:
    """Given a YouTube playlist URL, return a list of all video URLs in that playlist.

    If yt-dlp fails or the URL isn't a playlist, returns an empty list.
    """
    if not check_is_playlist(playlist_url):
        return []

    ydl_opts: dict[str, Any] = {
        "logger": logger,
        "quiet": True,
        "skip_download": True,
        "extract_flat": "in_playlist",
    }

    # run blocking playlist extraction in thread
    def _extract_playlist(opts: dict[str, Any], url: str) -> dict[str, Any] | None:
        with YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)  # type: ignore[no-typing]

    try:
        info = await asyncio.to_thread(_extract_playlist, ydl_opts, playlist_url)
    except DownloadError as e:
        logger.warning(
            "yt-dlp failed to extract playlist info for %s: %s", playlist_url, e
        )
        return []
    except Exception:
        logger.exception("Unexpected error fetching playlist info for %s", playlist_url)
        return []

    if info is None:
        msg = "Retrieved info from youtube was None"
        raise TypeError(msg)

    entries = cast("list[dict[str, Any]]", info.get("entries")) or []  # type: ignore[no-typing]

    video_urls: list[str] = []
    for entry in entries:
        vid_id = entry.get("id")
        if not vid_id:
            continue

        # build a standard watch URL
        video_urls.append(f"https://www.youtube.com/watch?v={vid_id}")

        # Store the metadata for each track
        extract_metadata(entry)

    return video_urls


async def search_youtube(search: str, n: int = 5) -> list[tuple[str, str, float]]:
    """Given a search string, return the top `n` results.

    Returns a list of (url, title, duration (s)
    """
    ydl_opts: dict[str, Any] = {
        "logger": logger,
        "extract_flat": True,
        "forceid": True,
        "forcetitle": True,
        "noprogress": True,
        "quiet": True,
        "skip_download": True,
    }

    # As a kludge, search for an extra two entries and only return the top 5 video
    # results
    search = f"ytsearch{n + 2}:{search}"

    try:
        # Run the (blocking) extract info call in an async thread
        def _run_extract(opts: dict[str, Any], query: str) -> dict[str, Any] | None:
            with YoutubeDL(opts) as ydl:
                return ydl.extract_info(query, download=False)  # type: ignore[no-typing]

        info: dict[str, Any] | None = await asyncio.to_thread(
            _run_extract, ydl_opts, search
        )

    except DownloadError as e:
        logger.warning("yt-dlp failed to extract search for %s: %s", search, e)
        return []
    except Exception:
        logger.exception("Unexpected error fetching search for %s", search)
        return []

    if info is None:
        msg = "Retrieved info from youtube was None"
        raise TypeError(msg)

    entries = cast("list[dict[str, Any]]", info.get("entries")) or []  # type: ignore[no-typing]

    results: list[tuple[str, str, float]] = []
    for entry in entries:
        # Only keep actual videos (they always have a "duration" field)
        duration = entry.get("duration")
        video_id = entry.get("id")
        title = entry.get("title")

        if duration is None or not video_id or not title:
            # missing duration is a channel/playlist/etc.
            continue

        url = f"https://www.youtube.com/watch?v={video_id}"
        results.append((url, title, duration))
        if len(results) == n:
            break

    logger.info('Search for "%s" return %d results', search, len(results))
    return results
