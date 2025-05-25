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

import logging
import subprocess
from typing import Any

from yt_dlp import YoutubeDL

logger = logging.getLogger(__name__)


def extract_audio_pcm(
    url: str,
    sample_rate: int = 44100,
    channels: int = 2,
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
    }

    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        if not info:
            msg = f"Could not extract info from {url}"
            raise RuntimeError(msg)
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

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)  # noqa: S603
    out, err = proc.communicate()
    if proc.returncode != 0:
        msg = f"ffmpeg error: {err.decode('utf-8', errors='ignore')}"
        raise RuntimeError(msg)

    return bytearray(out)


if __name__ == "__main__":
    # Example usage
    logger = logging.getLogger("youtube_audio")
    logging.basicConfig(level=logging.INFO)
    logger.info("Starting YouTube audio extraction example...")
    try:
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"  # Example URL
        pcm_data = extract_audio_pcm(
            url,
        )
        logger.info("Extracted %d bytes of PCM audio data.", len(pcm_data))
    except RuntimeError as e:
        logger.exception("Error!", exc_info=e)
