import asyncio
import atexit
import logging
import os
import re
import shutil
from pathlib import Path
from typing import Any, cast

from yt_dlp import YoutubeDL  # type: ignore[import]
from yt_dlp.utils import DownloadError  # type: ignore[import]

logger = logging.getLogger(__name__)

DEFAULT_SAMPLE_RATE = 48000  # Default sample rate for PCM audio
DEFAULT_CHANNELS = 2  # Default number of audio channels (stereo)

AUDIO_CACHE_DIR = os.getenv("AUDIO_CACHE_DIR", "./audio_cache/cached")
AUDIO_DOWNLOAD_DIR = os.getenv("AUDIO_DOWNLOAD_DIR", "./audio_cache/downloading")

# Directory for caching PCM audio files
audio_cache_dir = Path(AUDIO_CACHE_DIR).resolve()
audio_cache_dir.mkdir(parents=True, exist_ok=True)

# Temporary directory for in-progress downloads
audio_tmp_dir = Path(AUDIO_DOWNLOAD_DIR).resolve()
audio_tmp_dir.mkdir(parents=True, exist_ok=True)

# Track the reported file sizes of downloading files
download_sizes: dict[str, int] = {}


# Cleanup temp directory on exit
def _cleanup_tmp() -> None:
    shutil.rmtree(audio_tmp_dir, ignore_errors=True)


atexit.register(_cleanup_tmp)

# Dictionary to store video filenames by URL
_video_filenames: dict[str, str] = {}

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
        )
      |youtu\.be/                       # optional short URL
    )
    [A-Za-z0-9_-]{11}                   # the 11-char video ID
    """,
    re.VERBOSE,
)


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


def _get_download_path(url: str) -> Path:
    """Compute the temporary download file path for a URL."""
    vid = _get_video_id(url)
    base = vid or url.replace("/", "_")
    return audio_tmp_dir / f"{base}.part"


async def fetch_audio_pcm(
    url: str,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    channels: int = DEFAULT_CHANNELS,
    username: str | None = None,
    password: str | None = None,
) -> Path:
    """Download and cache PCM audio from a YouTube URL.

    If the audio is already cached, it will return the cached file path.
    If not cached, it will download the audio to a temp dir, convert it to
    PCM format, and move it into the cache directory upon success.

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
        NotImplementedError: If authentication is requested.

    """
    cache_path = _get_cache_path(url, sample_rate, channels)
    logger.info("Fetching audio for URL: %s", url)
    logger.debug("Cache path: %s", cache_path)
    # Return immediately if already cached
    if cache_path.exists():
        logger.debug("Using cached audio at %s", cache_path)
        return cache_path

    if username or password:
        msg = "YouTube authentication is not implemented yet."
        raise NotImplementedError(msg)

    # Prevent concurrent downloads of the same URL
    lock = _download_locks.setdefault(url, asyncio.Lock())
    async with lock:
        # Double-check cache inside lock
        if cache_path.exists():
            logger.debug("Using cached audio at %s", cache_path)
            return cache_path

        # Prepare yt-dlp options
        ydl_opts: dict[str, Any] = {
            "format": "bestaudio/best",
            "quiet": True,
            "nocheckcertificate": True,
            "ignoreerrors": True,
            "no_warnings": True,
        }

        logger.info("Extracting audio info from %s", url)
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

            filename = cast(
                "str",
                ydl.prepare_filename(info, outtmpl="%(title)s"),  # type: ignore[no-untyped-call]
            )
            if not filename:
                msg = "No filename found in extracted info."
                raise RuntimeError(msg)
            logger.debug("Extracted filename: %s", filename)
            _video_filenames[url] = filename

            video_size = cast("int", info.get("filesize", 0))
            if video_size > 0:
                download_sizes[url] = video_size
                logger.info("Estimated download size for %s: %d bytes", url, video_size)

        # Download & convert via ffmpeg into a temp file
        logger.info("Downloading audio from %s", url)
        temp_path = _get_download_path(url)
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
            str(temp_path),
        ]

        t0 = asyncio.get_event_loop().time()
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        out, err = await proc.communicate()
        if proc.returncode != 0:
            temp_path.unlink(missing_ok=True)
            msg = f"ffmpeg failed: {err.decode(errors='ignore')}"
            raise RuntimeError(msg)
        logger.info("ffmpeg completed successfully for %s", url)
        logger.debug("ffmpeg output: %s", out.decode())
        # Move completed file into cache
        temp_path.replace(cache_path)
        t1 = asyncio.get_event_loop().time()

        logger.info(
            "Downloaded and cached audio for %s at %s. Took %.1fs",
            url,
            cache_path,
            t1 - t0,
        )
        return cache_path


def get_audio_download_progress(
    url: str,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    channels: int = DEFAULT_CHANNELS,
) -> tuple[int, int]:
    """Get the download progress for a YouTube URL.

    Returns:
        A tuple of (downloaded bytes, total bytes).
        If the URL is not being downloaded, returns (total bytes, total bytes).

    """
    cache_path = _get_cache_path(url, sample_rate, channels)
    if cache_path.exists():
        # The file is cached, return its size
        logger.debug("Cache exists for %s, returning cached size", url)
        return (download_sizes.get(url, 0), download_sizes.get(url, 0))

    lock = _download_locks.get(url)
    if not lock or not lock.locked():
        # If no lock exists or it's not locked, we are not downloading
        logger.debug("No download in progress for %s, returning cached size", url)
        return (download_sizes.get(url, 0), download_sizes.get(url, 0))

    # If the lock is held, we are downloading, and need to get the current size on disk
    total = download_sizes.get(url, 0)
    download_path = _get_download_path(url)
    downloaded = download_path.stat().st_size if download_path.exists() else 0
    return (downloaded, total)


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


def get_youtube_track_name(url: str) -> str | None:
    """Get the track name from a YouTube URL."""
    if url in _video_filenames:
        return _video_filenames[url]

    try:
        ydl_opts = {"quiet": True, "skip_download": True}
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)  # type: ignore[untyped-call]
            if info is None:
                return None

            title = cast(
                "str",
                ydl.prepare_filename(info, outtmpl="%(title)s"),  # type: ignore[untyped-call]
            )
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
