import json
import subprocess
from logging import Logger
from pathlib import Path
from typing import Any, cast

from yt_dlp import YoutubeDL

from balaambot.utils import sec_to_string
from balaambot.youtube.utils import VideoMetadata, get_metadata_path


def download_and_convert(  # noqa: PLR0913
    logger: Logger,
    url: str,
    opus_tmp: Path,
    pcm_tmp: Path,
    cache_path: Path,
    sample_rate: int,
    channels: int,
) -> None:
    """Downloads audio using yt-dlp and converts to PCM using ffmpeg.

    Arguments:
        logger: The logging object being used
        url: The youtube url to download
        opus_tmp: The path to download the initial opus file to
        pcm_tmp: The path the pcm conversion file
        cache_path: The final resting place of the downloaded data
        sample_rate: Audio sample rate
        channels: Number of channels for the audio

    """
    logger.info("Downloading audio for url: '%s'", url)
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

    logger.info("Downloaded '%s' OK. Converting to PCM", url)

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

    logger.info("Finished downloading '%s'", url)


def get_metadata(logger: Logger, url: str) -> VideoMetadata:
    """Get the track metadata from a YouTube URL, caching to JSON files."""
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "extract_flat": True,
    }

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

    # ensure directory exists and write JSON
    meta_path = get_metadata_path(url)

    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    logger.debug("Cached metadata to %s", meta_path)

    return meta
