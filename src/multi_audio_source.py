import array
import logging
import shutil
import subprocess
import threading
from collections.abc import Callable
from pathlib import Path
from typing import TypedDict

from discord import AudioSource, VoiceClient

from .youtube_audio import check_youtube_url, extract_audio_pcm

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
    after_play: Callable[[], None] | None


class MultiAudioSource(AudioSource):
    """A class that mixes multiple audio sources for Discord voice communication."""

    SAMPLE_RATE = 48000  # 48 KHz
    CHANNELS = 2  # Stereo

    CHUNK_DURATION = 0.02  # 20ms

    BYTE_SIZE = 2  # 16-bit samples, so 2 bytes per sample

    # 20ms of 16-bit 48 KHz stereo PCM (48000 * 2 channels * 2 bytes * 0.02)
    CHUNK_SIZE = int(SAMPLE_RATE * CHANNELS * BYTE_SIZE * CHUNK_DURATION)

    # int16 min/max values
    MIN_VOLUME = -32768
    MAX_VOLUME = 32767

    def __init__(self) -> None:
        """Initializes a new MultiAudioSource instance."""
        # protect track list against concurrent play_file() calls
        self._lock = threading.Lock()
        self._tracks: list[Track] = []
        self._sfx: list[Track] = []
        self._stopped = False

    def is_opus(self) -> bool:
        """Return whether this audio source is encoded in Opus format."""
        return False

    def cleanup(self) -> None:
        """Clean up the audio source by clearing all tracks and marking stopped."""
        self.stop()

    def _mix_samples(self) -> array.array[int]:
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

        # New track and sfx lists to hold tracks that are still playing
        new_tracks: list[Track] = []
        new_sfx: list[Track] = []

        # mix all tracks and sfx together
        for track in self._tracks + self._sfx:
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

            # Check if track has finished
            if end >= len(samples):
                callback = track.get("after_play")
                if callback:
                    try:
                        logger.info("Calling after_play callback for track")
                        callback()
                    except Exception:
                        logger.exception("Error in after_play callback")
            else:
                if track in self._tracks:
                    new_tracks.append(track)
                if track in self._sfx:
                    new_sfx.append(track)

        self._tracks = new_tracks
        self._sfx = new_sfx

        return total

    def read(self) -> bytes:
        """Called by discord.py every ~20ms from a background thread.

        Mixes together all active tracks and returns exactly CHUNK_SIZE bytes.
        """
        if self._stopped:
            return b""

        with self._lock:
            total = self._mix_samples()

        out = array.array("h", [0] * (self.CHUNK_SIZE // 2))
        for i, val in enumerate(total):
            if val > self.MAX_VOLUME:
                out[i] = self.MAX_VOLUME
            elif val < self.MIN_VOLUME:
                out[i] = self.MIN_VOLUME
            else:
                out[i] = val

        return out.tobytes()

    def stop(self) -> None:
        """Stops the audio source by clearing all tracks and marking it as stopped."""
        logger.info("Stopping MultiAudioSource")
        self.stop_sfx()
        self.stop_tracks()

    def stop_sfx(self) -> None:
        """Stops all sound effects by clearing the sfx track list."""
        logger.info("Stopping all sound effects")
        with self._lock:
            self._sfx.clear()
            logger.info("All sound effects stopped")

    @property
    def is_stopped(self) -> bool:
        """Checks if the audio source is stopped."""
        return self._stopped

    def stop_tracks(self) -> None:
        """Stops all tracks by clearing the track list and marking it as stopped."""
        logger.info("Stopping all tracks")
        with self._lock:
            self._tracks.clear()
            self._stopped = True
            logger.info("All tracks stopped")

    async def play_youtube(
        self,
        url: str,
        username: str | None = None,
        password: str | None = None,
        after_play: Callable[[], None] | None = None,
    ) -> None:
        """Plays a YouTube video by extracting its audio and queuing it for mixing."""
        logger.info("Playing YouTube URL %s", url)

        check_youtube_url(url)

        # extract audio from YouTube URL
        pcm_data = await extract_audio_pcm(
            url,
            sample_rate=self.SAMPLE_RATE,
            channels=self.CHANNELS,
            username=username,
            password=password,
        )
        logger.info(
            "Extracted audio (%d bytes) from YouTube URL %s",
            len(pcm_data),
            url,
        )

        # convert bytes to array of int16 samples
        samples = array.array("h")
        samples.frombytes(pcm_data)

        # enqueue the track
        with self._lock:
            self._tracks.append(
                {"samples": samples, "pos": 0, "after_play": after_play}
            )

        self._stopped = False
        logger.info("There are now %d tracks in the mixer", len(self._tracks))

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
            self._tracks.append(
                {"samples": samples, "pos": 0, "after_play": after_play}
            )

        self._stopped = False
        logger.info("There are now %d tracks in the mixer", len(self._tracks))

    def skip_current_tracks(self) -> None:
        """Skips the currently playing track by moving its position to the end.

        Triggers its callback.
        """
        with self._lock:
            # Loop over all tracks and skip them
            logger.info("Skipping current tracks")
            while self._tracks:
                track = self._tracks.pop(0)
                # move position to end
                track["pos"] = len(track["samples"])
                # trigger after_play callback if present
                callback = track.get("after_play")
                if callback:
                    try:
                        logger.info("Calling after_play callback for skipped track")
                        callback()
                    except Exception:
                        logger.exception(
                            "Error in after_play callback for skipped track"
                        )
