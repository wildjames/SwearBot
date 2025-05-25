"""youtube audio extraction.

Module to extract audio from a YouTube video and return the audio as PCM in an
int16 bytearray.

Dependencies:
  pip install yt-dlp
Requires:
  - ffmpeg installed and available on PATH

Usage:
    from youtube_audio import extract_audio_pcm, generate_cookiefile
    pcm_bytes = extract_audio_pcm("https://www.youtube.com/watch?v=...")
"""

import asyncio
import logging
import re
from typing import Any, cast

from yt_dlp import YoutubeDL  # type: ignore[import]
from yt_dlp.utils import DownloadError  # type: ignore[import]

logger = logging.getLogger(__name__)

# Dictionary to store video filenames by URL
_video_filenames: dict[str, str] = {}


async def extract_audio_pcm(
    url: str,
    sample_rate: int = 44100,
    channels: int = 2,
    username: str | None = None,  # noqa: ARG001 Will be implemented later
    password: str | None = None,  # noqa: ARG001
) -> bytearray:
    """Download audio from a YouTube URL and convert it to PCM 16-bit little-endian.

    Args:
        url: YouTube video URL.
        username: Optional YouTube (Google) username for authentication.
        password: Optional YouTube (Google) password for authentication.
        sample_rate: Output sample rate in Hz (default: 44100).
        channels: Number of audio channels (default: 2).

    Returns:
        A bytearray containing raw PCM samples (int16 little-endian).

    Raises:
        RuntimeError: If ffmpeg fails.

    """
    # Prepare yt-dlp options
    ydl_opts: dict[str, Any] = {
        "format": "bestaudio/best",
        "quiet": True,
        "nocheckcertificate": True,
        "ignoreerrors": True,
        "no_warnings": True,
        "extract_flat": True,  # Do not download the video, just get the audio URL
    }

    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(  # type: ignore[no-untyped-call]
            url,
            download=False,
        )
        if not info:
            msg = f"Could not extract info from {url}. See logs for details."
            raise RuntimeError(msg)
        info = cast("dict[str, Any]", info)

        filename = cast("str", ydl.prepare_filename(info, outtmpl="%(title)s"))  # type: ignore[no-untyped-call]
        if not filename:
            msg = "No filename found in extracted info."
            raise RuntimeError(msg)
        logger.debug("Extracted filename: %s", filename)
        _video_filenames[url] = filename

        audio_url = info.get("url")
        if not audio_url:
            msg = "No audio URL found in extracted info."
            raise RuntimeError(msg)

    # Build ffmpeg command to convert to PCM s16le
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
        "pipe:1",
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    out, err = await proc.communicate()

    if proc.returncode != 0:
        msg = f"ffmpeg failed: {err.decode(errors='ignore')}"
        raise RuntimeError(msg)

    return bytearray(out)


def check_youtube_url(url: str) -> bool:
    """Check if the URL is a valid Youtube URL."""
    if url in _video_filenames:
        # If we already have the video name, we know it's valid
        return True

    # Pattern to match YouTube URLs and extract the video ID
    pattern = re.compile(
        r"^(?:https?://)?(?:www\.)?"
        r"(?:youtube\.com/(?:watch\?(?:.*&)?v=|embed/)|youtu\.be/)"
        r"(?P<id>[A-Za-z0-9_-]{11})"
    )
    match = pattern.match(url)
    if not match:
        logger.error("Invalid YouTube URL: %s", url)
        return False
    return True


def get_youtube_track_name(url: str) -> str | None:
    """Get the track name from a YouTube URL.

    Args:
        url: YouTube video URL.

    Returns:
        The track name if available, otherwise None.

    """
    if not check_youtube_url(url):
        logger.error("Invalid YouTube URL: %s", url)
        return None

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
    # Example usage
    logger = logging.getLogger("youtube_audio")
    logging.basicConfig(level=logging.INFO)

    import time

    logger.info("Starting YouTube audio extraction example...")
    url = r"https://youtu.be/Sf_n2AOuCRA\?si\=Wy8sv3ZRl9g3L6u6"  # Long video
    url = r"https://www.youtube.com/watch?v=dQw4w9WgXcQ"  # Short video

    try:
        logger.info("First call to get track name...")
        t0 = time.perf_counter()
        track_name = get_youtube_track_name(url)
        t1 = time.perf_counter()

        logger.info(
            "YouTube track name: %s in %.1f seconds",
            track_name or "Invalid URL",
            t1 - t0,
        )

        t0 = time.perf_counter()
        pcm_data = asyncio.run(
            extract_audio_pcm(
                url,
            )
        )
        t1 = time.perf_counter()

        logger.info(
            "Extracted %.3f megabytes of PCM audio data in %.1f seconds",
            len(pcm_data) / (1024 * 1024),
            t1 - t0,
        )

        logger.info("Second call to get track name...")
        t0 = time.perf_counter()
        track_name = get_youtube_track_name(url)
        t1 = time.perf_counter()

        logger.info(
            "YouTube track name: %s in %.1f seconds",
            track_name or "Invalid URL",
            t1 - t0,
        )
    except RuntimeError as e:
        logger.exception("Error!", exc_info=e)
