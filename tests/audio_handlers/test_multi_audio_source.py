# type: ignore
import array
import shutil
import subprocess

import pytest

import src.audio_handlers.multi_audio_source as mas
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

@pytest.fixture(autouse=True)
def clear_mixers_and_tracks():
    # Clear global mixer registry and ensure fresh instances
    _mixers.clear()
    yield
    _mixers.clear()


@pytest.mark.asyncio
async def test_ensure_mixer_multiple_guilds(monkeypatch):
    class DummyGuild:
        def __init__(self, id):
            self.id = id

    class DummyVC:
        def __init__(self, id):
            self.guild = DummyGuild(id)
            self.played = []

        def play(self, source):
            # record that play() was called
            self.played.append(source)

    # First guild should create a new mixer and call play()
    vc1 = DummyVC(1)
    mixer1 = await ensure_mixer(vc1)
    assert isinstance(mixer1, MultiAudioSource)
    assert _mixers[1] is mixer1
    assert vc1.played == [mixer1]

    # Second guild should get its own mixer
    vc2 = DummyVC(2)
    mixer2 = await ensure_mixer(vc2)
    assert mixer2 is not mixer1
    assert _mixers[2] is mixer2
    assert vc2.played == [mixer2]

    # Calling again for guild 1 should reuse and not call play()
    vc1b = DummyVC(1)
    mixer1b = await ensure_mixer(vc1b)
    assert mixer1b is mixer1
    assert vc1b.played == []


@pytest.mark.asyncio
async def test_play_youtube_success(monkeypatch):
    src = MultiAudioSource()
    url = "yt://test"
    # prepare dummy PCM bytes: two int16 samples: [3, 4]
    pcm_bytes = b"\x03\x00\x04\x00"
    calls = []

    async def fake_fetch(url_in, sample_rate, channels, username, password):
        calls.append((url_in, sample_rate, channels, username, password))
    monkeypatch.setattr(mas, "fetch_audio_pcm", fake_fetch)
    monkeypatch.setattr(mas, "get_audio_pcm", lambda u: pcm_bytes if u == url else None)

    await src.play_youtube(url, username="u", password="p", after_play=None)

    # fetch_audio_pcm was awaited with correct args
    assert calls == [(url, src.SAMPLE_RATE, src.CHANNELS, "u", "p")]

    # One track enqueued
    assert len(src._tracks) == 1
    track = src._tracks[0]
    assert isinstance(track["samples"], array.array)
    assert track["samples"].tolist() == [3, 4]
    assert track["pos"] == 0
    assert src._stopped is False


@pytest.mark.asyncio
async def test_play_youtube_missing_cache(monkeypatch):
    src = MultiAudioSource()
    url = "yt://missing"

    async def fake_fetch(url_in, sample_rate, channels, username, password):
        # no-op
        return
    monkeypatch.setattr(mas, "fetch_audio_pcm", fake_fetch)
    monkeypatch.setattr(mas, "get_audio_pcm", lambda u: None)

    with pytest.raises(RuntimeError) as exc:
        await src.play_youtube(url)
    # error message should mention the URL and "missing"
    assert f"Cached file for {url} missing" in str(exc.value)


def test_mix_samples_with_callback_and_padding():
    src = MultiAudioSource()
    # Make CHUNK_SIZE small: 4 bytes => 2 samples
    src.CHUNK_SIZE = 4
    called = []

    # samples length 1, so needs padding for second sample
    samples = array.array("h", [5])
    def cb():
        called.append(True)

    track = {"samples": samples, "pos": 0, "after_play": cb}
    src._tracks = [track]
    src._sfx = []

    total = src._mix_samples()
    # Should have [5, 0] as int32 array
    assert isinstance(total, array.array) and total.typecode == "i"
    assert total.tolist() == [5, 0]
    # after_play callback should have been called once
    assert called == [True]
    # track lists should now be empty
    assert src._tracks == []
    assert src._sfx == []


def test_skip_current_tracks_invokes_callbacks_and_clears():
    src = MultiAudioSource()
    src._stopped = False

    called = []
    # Two tracks with after_play handlers
    t1 = {"samples": array.array("h", [1, 2]), "pos": 1, "after_play": lambda: called.append("a")}
    t2 = {"samples": array.array("h", [3, 4, 5]), "pos": 2, "after_play": lambda: called.append("b")}
    src._tracks = [t1, t2]

    src.skip_current_tracks()
    # All tracks should be removed
    assert src._tracks == []
    # Both callbacks called
    assert set(called) == {"a", "b"}


def test_skip_current_tracks_callback_exceptions_are_swallowed():
    src = MultiAudioSource()
    src._tracks = [{"samples": array.array("h", [1]), "pos": 0, "after_play": lambda: (_ for _ in ()).throw(ValueError())}]
    # Should not raise
    src.skip_current_tracks()
    assert src._tracks == []  # track removed despite exception


def test_stop_sfx_and_stop_tracks_and_stop():
    src = MultiAudioSource()
    src._sfx = [1, 2, 3]
    src._tracks = [4, 5, 6]
    src._stopped = False

    # stop_sfx clears only sfx
    src.stop_sfx()
    assert src._sfx == []
    assert src._tracks == [4, 5, 6]

    # stop_tracks clears tracks and sets stopped
    src.stop_tracks()
    assert src._tracks == []
    assert src._stopped is True

    # stop() should invoke both in sequence
    calls = []
    # monkeypatch instance methods
    mas.MultiAudioSource.stop_sfx = lambda self: calls.append("sfx")
    mas.MultiAudioSource.stop_tracks = lambda self: calls.append("tracks")
    src2 = MultiAudioSource()
    src2.stop()
    assert calls == ["sfx", "tracks"]


def test_cleanup_just_calls_stop(monkeypatch):
    src = MultiAudioSource()
    called = []
    monkeypatch.setattr(src, "stop", lambda: called.append(True))
    src.cleanup()
    assert called == [True]
