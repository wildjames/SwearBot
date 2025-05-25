import asyncio
import logging
import re
from pathlib import Path
from typing import Any, cast

from yt_dlp import YoutubeDL  # type: ignore[import]
from yt_dlp.utils import DownloadError  # type: ignore[import]

logger = logging.getLogger(__name__)

DEFAULT_SAMPLE_RATE = 48000  # Default sample rate for PCM audio
DEFAULT_CHANNELS = 2  # Default number of audio channels (stereo)

# Directory for caching PCM audio files
audio_cache_dir = Path("./audio_cache")
audio_cache_dir.mkdir(parents=True, exist_ok=True)

# In-memory mapping of URL to cached file path
_url_cache: dict[str, Path] = {}

# Dictionary to store video filenames by URL
_video_filenames: dict[str, str] = {}

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
    """,
    re.VERBOSE,
)


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


async def fetch_audio_pcm(
    url: str,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    channels: int = DEFAULT_CHANNELS,
    username: str | None = None,
    password: str | None = None,
) -> Path:
    """Download and cache PCM audio from a YouTube URL.

    If the audio is already cached, it will return the cached file path.
    If not cached, it will download the audio, convert it to PCM format,
    and save it to the cache directory.

    Args:
        url: YouTube video URL.
        sample_rate: Output sample rate (Hz).
        channels: Number of audio channels.
        username: YouTube account username for authentication (NOT IMPLEMENTED).
        password: YouTube account password for authentication (NOT IMPLEMENTED).

    Returns:
        Path to the cached PCM file.

    Raises:
        RuntimeError: On download or conversion failure.

    """
    cache_path = _get_cache_path(url, sample_rate, channels)
    # Skip if already cached
    if cache_path.exists():
        logger.debug("Using cached audio at %s", cache_path)
        _url_cache[url] = cache_path
        return cache_path

    if username or password:
        msg = "YouTube authentication is not implemented yet."
        raise NotImplementedError(msg)

    # Prepare yt-dlp options
    ydl_opts: dict[str, Any] = {
        "format": "bestaudio/best",
        "quiet": True,
        "nocheckcertificate": True,
        "ignoreerrors": True,
        "no_warnings": True,
    }

    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)  # type: ignore  # noqa: PGH003
        if not info:
            msg = f"Could not extract info from {url}"
            raise RuntimeError(msg)

        info = cast("dict[str, Any]", info) if isinstance(info, dict) else {}
        audio_url = cast("str", info.get("url"))

        if not audio_url:
            msg = f"No audio URL found in info for {url}"
            raise RuntimeError(msg)

        filename = cast("str", ydl.prepare_filename(info, outtmpl="%(title)s"))  # type: ignore[no-untyped-call]
        if not filename:
            msg = "No filename found in extracted info."
            raise RuntimeError(msg)
        logger.debug("Extracted filename: %s", filename)
        _video_filenames[url] = filename

    # FFMPEG command to convert and write to file
    cmd: list[str] = [
        "ffmpeg",
        "-y",
        "-i",
        audio_url,
        "-f",
        "s16le",
        "-acodec",
        "pcm_s16le",
        "-ac",
        str(channels),
        "-ar",
        str(sample_rate),
        str(cache_path),
    ]

    t0 = asyncio.get_event_loop().time()
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    _out, err = await proc.communicate()
    if proc.returncode != 0:
        msg = f"ffmpeg failed: {err.decode(errors='ignore')}"
        raise RuntimeError(msg)
    t1 = asyncio.get_event_loop().time()

    _url_cache[url] = cache_path
    logger.info(
        "Cached audio for %s at %s. Took %.1fs",
        url,
        cache_path,
        t1 - t0,
    )
    return cache_path


def get_audio_pcm(url: str) -> bytearray | None:
    """Retrieve PCM audio data for a previously fetched URL.

    Args:
        url: YouTube video URL.

    Returns:
        Bytearray of PCM data, or None if not cached.

    """
    path = _url_cache.get(url) or _get_cache_path(
        url, DEFAULT_SAMPLE_RATE, DEFAULT_CHANNELS
    )
    if not path.exists():
        logger.error("No cached audio for URL: %s", url)
        return None
    data = path.read_bytes()
    return bytearray(data)


def remove_audio_pcm(url: str) -> bool:
    """Remove cached PCM audio for a URL.

    Args:
        url: YouTube video URL.

    Returns:
        True if removed, False if not found.

    """
    path = _url_cache.get(url) or _get_cache_path(
        url, DEFAULT_SAMPLE_RATE, DEFAULT_CHANNELS
    )
    if path.exists():
        path.unlink()
        _url_cache.pop(url, None)
        logger.info("Removed cached audio for %s", url)
        return True
    logger.warning("Attempted to remove non-existent cache for %s", url)
    return False


def get_youtube_track_name(url: str) -> str | None:
    """Get the track name from a YouTube URL.

    Args:
        url: YouTube video URL.

    Returns:
        The track name if available, otherwise None.

    """
    if url in _video_filenames:
        # If we already have the video name, return it
        return _video_filenames[url]

    try:
        ydl_opts = {"quiet": True, "skip_download": True}
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)  # type: ignore[untyped-call]
            if info is None:
                return None

            title = cast("str", ydl.prepare_filename(info, outtmpl="%(title)s"))  # type: ignore[no-untyped-call]
            _video_filenames[url] = title or url

            return title

    except DownloadError:
        return None
    else:
        return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    async def main() -> None:
        """Test the audio fetching and caching functionality."""
        logger.info("Testing audio fetching for URL: %s", test_url)
        # Fetch and cache audio
        t0 = asyncio.get_event_loop().time()
        cache_path = await fetch_audio_pcm(test_url)
        t1 = asyncio.get_event_loop().time()
        logger.info("Fetched audio cache at: %s", cache_path)
        logger.info("Fetch took %.2f seconds", t1 - t0)

        # Get track name
        t0 = asyncio.get_event_loop().time()
        track_name = get_youtube_track_name(test_url)
        t1 = asyncio.get_event_loop().time()
        if track_name:
            logger.info("Track name: %s", track_name)
            logger.info("Track name fetch took %.2f seconds", t1 - t0)
        else:
            logger.warning("Could not fetch track name for URL: %s", test_url)

        # Read raw PCM bytes
        t0 = asyncio.get_event_loop().time()
        pcm_data = get_audio_pcm(test_url)
        t1 = asyncio.get_event_loop().time()
        if pcm_data:
            logger.info("Loaded %s bytes of PCM data", len(pcm_data))
            logger.info("PCM data read took %.2f seconds", t1 - t0)

        await asyncio.sleep(5)

        # Remove cached file
        removed = remove_audio_pcm(test_url)
        logger.info("Cache removed: %s", removed)

    asyncio.run(main())
