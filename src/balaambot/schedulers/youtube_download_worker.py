import subprocess
from pathlib import Path
from typing import Any

from yt_dlp import YoutubeDL


def download_and_convert(  # noqa: PLR0913
    url: str,
    opus_tmp: Path,
    pcm_tmp: Path,
    cache_path: Path,
    sample_rate: int,
    channels: int,
) -> None:
    """Downloads audio using yt-dlp and converts to PCM using ffmpeg.

    Arguments:
        url: The youtube url to download
        opus_tmp: The path to download the initial opus file to
        pcm_tmp: The path the pcm conversion file
        cache_path: The final resting place of the downloaded data
        sample_rate: Audio sample rate
        channels: Number of channels for the audio

    """
    outdir = opus_tmp.parent
    base_name = opus_tmp.stem  # Remove suffix
    outtmpl = outdir / base_name  # yt-dlp adds the correct extension

    ydl_opts: dict[str, Any] = {
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
        "outtmpl": str(outtmpl),
    }

    # Download the audio
    with YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    # Look for the resulting .opus file
    expected_opus = outdir / f"{base_name}.opus"
    if not expected_opus.exists():
        msg = f"yt-dlp failed to produce {expected_opus}"
        raise RuntimeError(msg)

    # Convert .opus -> .pcm using ffmpeg
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

    # Move the PCM file to cache location
    pcm_tmp.replace(cache_path)
