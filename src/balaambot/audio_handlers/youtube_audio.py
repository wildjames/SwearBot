import asyncio
import atexit
import logging
import re
import shutil
import time
import urllib.parse
from pathlib import Path
from typing import Any, TypedDict, cast

from yt_dlp import DownloadError, YoutubeDL  # type: ignore[import]

import balaambot.config

logger = logging.getLogger(__name__)

DEFAULT_SAMPLE_RATE = 48000  # Default sample rate for PCM audio
DEFAULT_CHANNELS = 2  # Default number of audio channels (stereo)

AUDIO_CACHE_ROOT = Path(balaambot.config.PERSISTENT_DATA_DIR) / "audio_cache"

logger.info(
    "Using a sample rate of %dHz with %d channels",
    DEFAULT_SAMPLE_RATE,
    DEFAULT_CHANNELS,
)
logger.info("Using audio download and caching directory: '%s'", AUDIO_CACHE_ROOT)

# Directory for caching PCM audio files
audio_cache_dir = (AUDIO_CACHE_ROOT / "cached").resolve()
audio_cache_dir.mkdir(parents=True, exist_ok=True)

# Temporary directory for in-progress downloads
audio_tmp_dir = (AUDIO_CACHE_ROOT / "downloading").resolve()
audio_tmp_dir.mkdir(parents=True, exist_ok=True)


# Cleanup temp directory on exit
def _cleanup_tmp() -> None:
    shutil.rmtree(audio_tmp_dir, ignore_errors=True)


atexit.register(_cleanup_tmp)


# Dictionary to store video metadata by URL
class VideoMetadata(TypedDict):
    """Metadata for a YouTube video."""

    url: str
    title: str
    runtime: int  # in seconds
    runtime_str: str  # formatted as H:MM:SS or M:SS


# Keyed by URL, values are VideoMetadata
_video_metadata: dict[str, VideoMetadata] = {}

# Locks to prevent multiple simultaneous downloads of the same URL
_download_locks: dict[str, asyncio.Lock] = {}

# Regex to extract YouTube video ID
_YT_ID_RE = re.compile(
    r"""
    ^(?:https?://)?                     # optional scheme
    (?:(?:www|music)\.)?                # optional www. or music.
    (?:                                 # host + path alternatives:
        youtube\.com/
        (?:
            watch\?(?:.*&)?v=
            |embed/
            |shorts/
        )
      |youtu\.be/                       # optional short URL
    )
    (?P<id>[A-Za-z0-9_-]{11})           # the 11-char video ID
    .*                                  # Any extra query parameters
    """,
    re.VERBOSE,
)
_VALID_YT_URL_RE = re.compile(
    r"""
    ^(?:https?://)?                     # optional scheme
    (?:(?:www|music)\.)?                # optional www. or music.
    (?:                                 # host + path alternatives:
        youtube\.com/
        (?:
            watch\?(?:.*&)?v=
            |embed/
            |shorts/
            |playlist/
        )
      |youtu\.be/                       # optional short URL
    )
    [A-Za-z0-9_-]{11}                   # the 11-char video ID
    .*                                  # Any extra query parameters
    """,
    re.VERBOSE,
)
_VALID_YT_PLAYLIST_URL = re.compile(
    r"""
    ^(?:https?://)?                    # optional scheme
    (?:(?:www|music)\.)?               # optional www. or music.
    (?:
        youtube\.com/
        (?:
            playlist\?list=           #   /playlist?list=ID
          | watch\?(?:.*&)?list=      #   /watch?...&list=ID
          | embed/videoseries\?list=  #   /embed/videoseries?list=ID
        )
      | youtu\.be/[A-Za-z0-9_-]{11}\? #   youtu.be/VIDEO_ID?
        (?:.*&)?list=                 #   ...&list=ID
    )
    (?P<playlist_id>[A-Za-z0-9_-]+)    # capture the playlist ID
    (?:[&?].*)?                        # optional extra params
    $
    """,
    re.VERBOSE,
)


def sec_to_string(val: float) -> str:
    """Convert a number of seconds to a human-readable string, (HH:)MM:SS."""
    sec_in_hour = 60 * 60
    d = ""
    if val >= sec_in_hour:
        d += f"{int(val // sec_in_hour):02d}:"
        val = val % sec_in_hour
    d += f"{int(val // 60):02d}:{int(val % 60):02d}"
    return d


def is_valid_youtube_url(url: str) -> bool:
    """Check if a URL is a valid YouTube video URL."""
    return _VALID_YT_URL_RE.match(url) is not None


def _get_video_id(url: str) -> str | None:
    """Extract the video ID from a YouTube URL."""
    match = _YT_ID_RE.match(url)
    return match.group("id") if match else None


def _get_cache_path(url: str, sample_rate: int, channels: int) -> Path:
    """Compute the cache file path for a URL and audio parameters."""
    vid = _get_video_id(url)
    base = vid or url.replace("/", "_")
    filename = f"{base}_{sample_rate}Hz_{channels}ch.pcm"
    return audio_cache_dir / filename


def _get_temp_paths(url: str) -> tuple[Path, Path]:
    vid = _get_video_id(url)
    base = vid or url.replace("/", "_")
    opus_tmp = audio_tmp_dir / f"{base}.opus.part"
    pcm_tmp = audio_tmp_dir / f"{base}.pcm.part"
    return opus_tmp, pcm_tmp


async def get_youtube_track_metadata(url: str) -> VideoMetadata | None:
    """Get the track metadata from a YouTube URL."""
    # quick URL validation
    if not is_valid_youtube_url(url):
        logger.debug("Invalid YouTube URL: %s", url)
        return None

    # return cached metadata if available
    if url in _video_metadata:
        return _video_metadata[url]

    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "extract_flat": True,  # faster metadata-only extraction
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)  # type: ignore[no-typing]
    except DownloadError as e:
        logger.warning("yt-dlp failed to extract info for %s: %s", url, e)
        return None
    except Exception:
        logger.exception("Unexpected error fetching metadata for %s", url)
        return None

    if not info:
        return None

    # pull out title and duration (seconds)
    title = cast("str", info.get("title")) or url  # type: ignore[no-typing]
    duration_s = cast("int", info.get("duration")) or 0  # type: ignore[no-typing]

    # format runtime as H:MM:SS or M:SS
    runtime = time.strftime("%H:%M:%S", time.gmtime(duration_s))
    # strip leading "00:" for videos under an hour
    runtime = runtime.removeprefix("00:")

    runtime_str = (
        f"{duration_s // 3600:02}:{(duration_s % 3600) // 60:02}:{duration_s % 60:02}"
    )

    # cache and return
    _video_metadata[url] = VideoMetadata(
        url=url,
        title=title,
        runtime=duration_s,
        runtime_str=runtime_str,
    )
    logger.debug("Cached metadata for %s: %s", url, _video_metadata[url])
    return _video_metadata[url]


async def fetch_audio_pcm(
    url: str,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    channels: int = DEFAULT_CHANNELS,
    username: str | None = None,
    password: str | None = None,
) -> Path:
    """Audio fetching. Cache check, download via yt-dlp, then convert to PCM."""
    cache_path = _get_cache_path(url, sample_rate, channels)
    if cache_path.exists():
        return cache_path

    if username or password:
        msg = "YouTube authentication is not implemented yet."
        raise NotImplementedError(msg)

    lock = _download_locks.setdefault(url, asyncio.Lock())
    async with lock:
        if cache_path.exists():
            return cache_path

        opus_tmp, pcm_tmp = _get_temp_paths(url)

        promises = [  # type: ignore[no-typing]
            _download_opus(url, opus_tmp),
            get_youtube_track_metadata(url),
        ]

        # Run download and metadata fetch concurrently
        try:
            await asyncio.gather(*promises)  # type: ignore[no-typing]
        except DownloadError as e:
            logger.exception("yt-dlp failed to download %s", url)
            msg = f"Failed to download audio for {url}"
            raise RuntimeError(msg) from e

        await _convert_opus_to_pcm(opus_tmp, pcm_tmp, cache_path, sample_rate, channels)

        return cache_path


async def _download_opus(url: str, opus_tmp: Path) -> None:
    """Use yt-dlp to download and extract audio as opus into opus_tmp."""
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
        "outtmpl": str(opus_tmp.with_suffix("")),  # drop .part suffix
    }
    loop = asyncio.get_event_loop()
    # Blocking download in executor
    await loop.run_in_executor(None, lambda: YoutubeDL(ydl_opts).download([url]))  # type: ignore[no-typing]

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


def get_audio_pcm(
    url: str, sample_rate: int = DEFAULT_SAMPLE_RATE, channels: int = DEFAULT_CHANNELS
) -> bytearray | None:
    """Retrieve PCM audio data for a previously fetched URL."""
    path = _get_cache_path(url, sample_rate, channels)
    if not path.exists():
        logger.error("No cached audio for URL: %s", url)
        return None
    data = path.read_bytes()
    return bytearray(data)


def remove_audio_pcm(
    url: str, sample_rate: int = DEFAULT_SAMPLE_RATE, channels: int = DEFAULT_CHANNELS
) -> bool:
    """Remove cached PCM audio for a URL."""
    path = _get_cache_path(url, sample_rate, channels)
    if path.exists():
        path.unlink()
        logger.info("Removed cached audio for %s", url)
        return True
    logger.warning("Attempted to remove non-existent cache for %s", url)
    return False


def is_valid_youtube_playlist(url: str) -> bool:
    """Check if a URL is a valid YouTube playlist URL."""
    return _VALID_YT_PLAYLIST_URL.match(url) is not None


def check_is_playlist(url: str) -> bool:
    """Check if the given url is a playlist by looking for the 'link' parameter.

    Returns True if a non-empty 'list' query parameter is present.
    """
    if not is_valid_youtube_playlist(url):
        return False

    parsed = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed.query)

    # 'list' will be a key if there's a playlist ID in the URL
    return bool(params.get("list", False))


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

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(playlist_url, download=False)  # type: ignore[no-typing]
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
        def _run_extract() -> dict[str, Any] | None:
            with YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(search, download=False)  # type: ignore[no-typing]

        info: dict[str, Any] | None = await asyncio.to_thread(_run_extract)

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
