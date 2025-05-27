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


def _get_temp_paths(url: str) -> tuple[Path, Path]:
    vid = _get_video_id(url)
    base = vid or url.replace("/", "_")
    opus_tmp = audio_tmp_dir / f"{base}.opus.part"
    pcm_tmp = audio_tmp_dir / f"{base}.pcm.part"
    return opus_tmp, pcm_tmp


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

        await _download_opus(url, opus_tmp)
        await _convert_opus_to_pcm(opus_tmp, pcm_tmp, cache_path, sample_rate, channels)

        return cache_path


async def _download_opus(url: str, opus_tmp: Path) -> None:
    """Use yt-dlp to download and extract audio as opus into opus_tmp."""
    # Ensure directory exists
    opus_tmp.parent.mkdir(parents=True, exist_ok=True)
    ydl_opts: dict[str, Any] = {
        "format": "bestaudio",
        "quiet": True,
        "nocheckcertificate": True,
        "ignoreerrors": True,
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
    await loop.run_in_executor(None, lambda: YoutubeDL(ydl_opts).download([url]))  # type: ignore  # noqa: PGH003

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
