import array
import logging
import shutil
import subprocess
import threading
from collections.abc import Callable
from pathlib import Path
from typing import TypedDict

from discord import AudioSource, VoiceClient

logger = logging.getLogger(__name__)

# Keep one mixer per guild
_mixers: dict[int, "MultiAudioSource"] = {}


async def ensure_mixer(vc: VoiceClient) -> "MultiAudioSource":
    """Attach (or reuse) a MultiAudioSource on this VoiceClient."""
    gid = vc.guild.id
    if gid not in _mixers:
        mixer = MultiAudioSource()
        vc.play(mixer)  # start the background mixer thread
        _mixers[gid] = mixer
        logger.info("Created mixer for guild %s", gid)
    return _mixers[gid]


class Track(TypedDict):
    """Represents an audio track with its samples and current playback position."""

    samples: array.array[int]
    pos: int


class MultiAudioSource(AudioSource):
    """A class that mixes multiple audio sources for Discord voice communication."""

    # 20ms of 16-bit 48 KHz stereo PCM (48000 * 2 channels * 2 bytes * 0.02)
    CHUNK_SIZE = int(48000 * 2 * 2 * 0.02)

    # int16 min/max values
    MIN_VOLUME = -32768
    MAX_VOLUME = 32767

    def __init__(self) -> None:
        """Initializes a new MultiAudioSource instance."""
        # protect track list against concurrent play_file() calls
        self._lock = threading.Lock()
        self._tracks: list[Track] = []
        self._stopped = False

    def is_opus(self) -> bool:
        """Return whether this audio source is encoded in Opus format."""
        return False

    def cleanup(self) -> None:
        """Clean up the audio source by clearing all tracks and marking stopped."""
        with self._lock:
            self._tracks.clear()
            self._stopped = True

    def _mix_samples(self, tracks: list[Track]) -> tuple[array.array[int], list[Track]]:
        """Mixes the samples of all tracks together.

        Args:
        ----
            tracks: A list of tracks to mix.

        Returns:
        -------
            A tuple containing the mixed samples and the updated list of tracks.

        """
        # create a new array for the mixed samples. Use int32 to avoid overflow.
        total = array.array("i", [0] * (self.CHUNK_SIZE // 2))
        new_tracks: list[Track] = []

        # mix all tracks together
        for track in tracks:
            samples = track["samples"]

            # Get the range of samples to mix
            pos = track["pos"]
            end = pos + (self.CHUNK_SIZE // 2)

            # if the track is near the end, pad it with zeros
            if end > len(samples):
                pad = array.array("h", [0] * (end - len(samples)))
                samples.extend(pad)

            chunk = samples[pos:end]

            for i, s in enumerate(chunk):
                total[i] += s

            track["pos"] = end

            # if the track is not finished, keep it in the list
            # otherwise, don't
            if end < len(samples):
                new_tracks.append(track)

        return total, new_tracks

    def read(self) -> bytes:
        """Called by discord.py every ~20ms from a background thread.

        Mixes together all active tracks and returns exactly CHUNK_SIZE bytes.
        """
        if self._stopped:
            return b"\x00" * self.CHUNK_SIZE

        with self._lock:
            total, self._tracks = self._mix_samples(self._tracks)

        out = array.array("h", [0] * (self.CHUNK_SIZE // 2))
        for i, val in enumerate(total):
            if val > self.MAX_VOLUME:
                out[i] = self.MAX_VOLUME
            elif val < self.MIN_VOLUME:
                out[i] = self.MIN_VOLUME
            else:
                out[i] = val

        return out.tobytes()

    def play_file(
        self, filename: str, after_play: Callable[[], None] | None = None
    ) -> None:
        """Plays an audio file by decoding it with ffmpeg and queues it for mixing."""
        logger.info("Playing file %s", filename)

        if not Path(filename).is_file():
            msg = f"{filename!r} does not exist"
            raise FileNotFoundError(msg)

        # check if ffmpeg is in PATH
        ffmpeg_path = shutil.which("ffmpeg")
        if ffmpeg_path is None:
            msg = "ffmpeg not found in PATH"
            raise RuntimeError(msg)

        # use ffmpeg to decode to s16le
        proc = subprocess.Popen(  # noqa: S603 We're safe here
            [
                ffmpeg_path,
                "-v",
                "quiet",
                "-i",
                filename,
                "-f",
                "s16le",
                "-ar",
                "48000",
                "-ac",
                "2",
                "pipe:1",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        pcm_data, err = proc.communicate()
        if proc.returncode != 0:
            msg = f"ffmpeg failed: {err.decode(errors='ignore')}"
            raise RuntimeError(msg)

        # convert bytes to array of int16 samples
        samples = array.array("h")
        samples.frombytes(pcm_data)

        # enqueue the track
        with self._lock:
            self._tracks.append({"samples": samples, "pos": 0})

        # call the callback if provided
        if after_play:
            after_play()
