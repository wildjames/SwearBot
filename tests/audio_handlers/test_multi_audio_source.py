# type: ignore
import array
import shutil
import subprocess

import pytest

from src.audio_handlers.multi_audio_source import (
    MultiAudioSource,
    _mixers,
    ensure_mixer,
)


def test_is_opus_returns_false():
    src = MultiAudioSource()
    assert not src.is_opus()


def test_mix_samples_combines_and_clears_tracks():
    src = MultiAudioSource()

    # Use small chunk size for testing (8 bytes -> 4 samples)
    src.CHUNK_SIZE = 8
    # Prepare tracks with after_play key for TypedDict
    track1 = {"samples": array.array("h", [1, 1, 1, 1]), "pos": 0, "after_play": None}
    track2 = {"samples": array.array("h", [2, 2, 2, 2]), "pos": 0, "after_play": None}
    # Assign tracks
    src._tracks = [track1, track2]
    src._sfx = []

    total = src._mix_samples()

    # The sum needs to be an int32 array
    assert isinstance(total, array.array)
    assert total.typecode == "i"
    assert list(total) == [3, 3, 3, 3]

    # Both tracks reached end, so internal _tracks and _sfx should be empty
    assert src._tracks == []
    assert src._sfx == []


def test_read_clips_and_respects_stopped(monkeypatch):
    src = MultiAudioSource()
    src.CHUNK_SIZE = 8

    # Stub mix to produce values outside clip range
    def fake_mix():
        return array.array("i", [100, -100, 0, 10])

    src._mix_samples = fake_mix
    src.MAX_VOLUME = 10
    src.MIN_VOLUME = -10

    # Test normal read with clipping
    data = src.read()
    out = array.array("h")
    out.frombytes(data)
    assert list(out) == [10, -10, 0, 10]

    # Test stopped state returns silence
    src._stopped = True
    silence = src.read()
    assert silence == b""


def test_cleanup_clears_tracks_and_sets_stopped():
    src = MultiAudioSource()
    src._tracks = [{"samples": array.array("h", [1]), "pos": 0}]
    src._stopped = False
    src.cleanup()
    assert src._stopped is True
    assert src._tracks == []


def test_play_file_success(monkeypatch, tmp_path):
    src = MultiAudioSource()
    # Create a dummy file
    dummy = tmp_path / "dummy.wav"
    dummy.write_bytes(b"")

    # Stub ffmpeg detection
    monkeypatch.setattr(shutil, "which", lambda name: "ffmpeg")

    # Stub subprocess.Popen
    class DummyPopen:
        def __init__(self, args, stdout, stderr):
            self.returncode = 0

        def communicate(self):
            return (b"\x01\x00\x02\x00", b"")

    monkeypatch.setattr(subprocess, "Popen", DummyPopen)

    # Track callback invocation
    called = []

    def after_play():
        called.append(True)

    src.play_file(str(dummy), after_play=after_play)

    # One track enqueued
    assert len(src._tracks) == 1
    track = src._tracks[0]

    # Samples converted correctly
    assert track["samples"] == array.array("h", [1, 2])
    assert track["pos"] == 0

    # Callback not called until playback finishes
    assert called == []

    # read until the track is done
    while track["pos"] < len(track["samples"]):
        src.read()

    # After reading all samples, callback should be called
    assert called == [True]


def test_play_file_ffmpeg_not_found(monkeypatch, tmp_path):
    src = MultiAudioSource()
    dummy = tmp_path / "dummy.wav"
    dummy.write_bytes(b"")
    monkeypatch.setattr(shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError) as exc:
        src.play_file(str(dummy))
    assert "ffmpeg not found" in str(exc.value)


def test_play_file_file_not_found():
    src = MultiAudioSource()
    with pytest.raises(FileNotFoundError):
        src.play_file("nonexistent.wav")


@pytest.mark.asyncio
async def test_ensure_mixer_creates_and_reuses():
    # Clear existing mixers
    _mixers.clear()

    calls = []

    class DummyGuild:
        def __init__(self, id):
            self.id = id

    class DummyVC:
        def __init__(self, id):
            self.guild = DummyGuild(id)
            self.played = []

        def play(self, source):
            calls.append(source)
            self.played.append(source)

    vc1 = DummyVC(42)
    mixer1 = await ensure_mixer(vc1)
    assert isinstance(mixer1, MultiAudioSource)
    assert mixer1 in calls

    # Calling again for same guild should not create a new mixer or call play
    vc2 = DummyVC(42)
    mixer2 = await ensure_mixer(vc2)
    assert mixer2 is mixer1
    assert vc2.played == []
