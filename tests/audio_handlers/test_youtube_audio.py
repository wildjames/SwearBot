# type: ignore
import asyncio
import os
import importlib
import sys
from pathlib import Path
import pytest
from yt_dlp.utils import DownloadError

# Helper to import the module under test with custom dirs
def import_module(tmp_cache_dir: Path, tmp_tmp_dir: Path):
    # Set environment variables before import
    os.environ['AUDIO_CACHE_DIR'] = str(tmp_cache_dir)
    os.environ['AUDIO_DOWNLOAD_DIR'] = str(tmp_tmp_dir)

    # Ensure fresh import
    module_name = 'src.audio_handlers.youtube_audio'
    if module_name in sys.modules:
        del sys.modules[module_name]
    module = importlib.import_module(module_name)
    return module

# Fixture for temporary cache and tmp directories
@pytest.fixture
def tmp_dirs(tmp_path):
    cache_dir = tmp_path / 'cache'
    tmp_dir = tmp_path / 'tmp'
    cache_dir.mkdir()
    tmp_dir.mkdir()
    return cache_dir, tmp_dir

# -- URL/id and path tests --

@pytest.mark.parametrize("url,expected_id", [
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("http://youtu.be/ABCDEFGHIJK", "ABCDEFGHIJK"),
    ("https://music.youtube.com/watch?v=12345678901&list=PL", "12345678901"),
    ("invalid_url", None),
])
def test_get_video_id_param(tmp_dirs, url, expected_id):
    cache_dir, tmp_dir = tmp_dirs
    mod = import_module(cache_dir, tmp_dir)
    assert mod._get_video_id(url) == expected_id


def test_get_video_id_various_urls(tmp_dirs):
    cache_dir, tmp_dir = tmp_dirs
    mod = import_module(cache_dir, tmp_dir)
    # Additional URL forms
    assert mod._get_video_id("https://youtu.be/12345678901") == "12345678901"
    assert mod._get_video_id("https://www.youtube.com/embed/ZYXWVUTSRQP") == "ZYXWVUTSRQP"

@pytest.mark.parametrize("url,rate,channels,expected_suffix", [
    ("https://youtu.be/ABCDEFGHIJK", 48000, 2, "ABCDEFGHIJK_48000Hz_2ch.pcm"),
    ("foo/bar", 44100, 1, "foo_bar_44100Hz_1ch.pcm"),
])
def test_get_cache_path_param(tmp_dirs, url, rate, channels, expected_suffix):
    cache_dir, tmp_dir = tmp_dirs
    mod = import_module(cache_dir, tmp_dir)
    path = mod._get_cache_path(url, rate, channels)
    assert path.parent == cache_dir.resolve()
    assert path.name == expected_suffix

# -- is_valid_youtube_url tests --
@pytest.mark.parametrize("url,valid", [
    ("https://www.youtube.com/watch?v=abcdEFGHijk", True),
    ("https://youtu.be/abcdEFGHijk", True),
    ("https://www.youtube.com/watch?v=shortID", False),
    ("not a url", False),
])
def test_is_valid_youtube_url(tmp_dirs, url, valid):
    cache_dir, tmp_dir = tmp_dirs
    mod = import_module(cache_dir, tmp_dir)
    assert mod.is_valid_youtube_url(url) == valid

# -- Sync API tests for PCM retrieval/removal --

def test_get_audio_pcm_and_remove(tmp_dirs):
    cache_dir, tmp_dir = tmp_dirs
    mod = import_module(cache_dir, tmp_dir)
    url = "https://youtu.be/TESTVIDEOID"

    # Nothing cached initially
    assert mod.get_audio_pcm(url) is None

    # Create a fake PCM file
    pcm_path = cache_dir / "TESTVIDEOID_48000Hz_2ch.pcm"
    content = b"\x01\x02\x03"
    pcm_path.write_bytes(content)

    # Retrieval
    data = mod.get_audio_pcm(url)
    assert isinstance(data, bytearray)
    assert data == bytearray(content)

    # Removal
    removed = mod.remove_audio_pcm(url)
    assert removed is True
    assert not pcm_path.exists()
    # Removing again
    assert not mod.remove_audio_pcm(url)

# -- Async fetch_audio_pcm tests --

@pytest.mark.asyncio
async def test_fetch_audio_pcm_cached(tmp_dirs):
    cache_dir, tmp_dir = tmp_dirs
    mod = import_module(cache_dir, tmp_dir)
    url = 'https://youtu.be/ZZZZZZZZZZZ'

    # Pre-cache data
    expected = mod._get_cache_path(url, mod.DEFAULT_SAMPLE_RATE, mod.DEFAULT_CHANNELS)
    expected.write_bytes(b'data')

    # Should return cached path without calling download
    result = await mod.fetch_audio_pcm(url)
    assert result == expected
    assert result.read_bytes() == b'data'

@pytest.mark.asyncio
async def test_fetch_audio_pcm_success(tmp_dirs, monkeypatch):
    cache_dir, tmp_dir = tmp_dirs
    mod = import_module(cache_dir, tmp_dir)
    url = "https://youtu.be/SOMEID12345"

    # Stub out download & conversion internals
    async def fake_download_opus(u, opus_tmp):
        opus_tmp.parent.mkdir(parents=True, exist_ok=True)
        # simulate yt-dlp output: create .opus.part file
        opus_tmp.write_bytes(b"")

    async def fake_convert_opus(opus_tmp, pcm_tmp, cache_path, sample_rate, channels):
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(b"\x00" * 10)

    monkeypatch.setattr(mod, '_download_opus', fake_download_opus)
    monkeypatch.setattr(mod, '_convert_opus_to_pcm', fake_convert_opus)

    # First fetch should invoke stubs and create cache
    result = await mod.fetch_audio_pcm(url)
    expected = cache_dir / f"SOMEID12345_{mod.DEFAULT_SAMPLE_RATE}Hz_{mod.DEFAULT_CHANNELS}ch.pcm"
    assert result == expected
    assert expected.exists()

    # Second fetch should use cache
    result2 = await mod.fetch_audio_pcm(url)
    assert result2 == expected

@pytest.mark.asyncio
async def test_fetch_audio_pcm_ffmpeg_fail(tmp_dirs, monkeypatch):
    cache_dir, tmp_dir = tmp_dirs
    mod = import_module(cache_dir, tmp_dir)
    url = "https://youtu.be/FAILID00001"

    # Stub download to create an opus_tmp file
    async def fake_download_opus(u, opus_tmp):
        opus_tmp.parent.mkdir(parents=True, exist_ok=True)
        opus_tmp.write_bytes(b"")

    monkeypatch.setattr(mod, '_download_opus', fake_download_opus)

    # Simulate ffmpeg failure in conversion
    class DummyProcessFail:
        def __init__(self, returncode=1, stderr=b"error"):  # noqa: D107
            self.returncode = returncode
            self._stderr = stderr
        async def communicate(self):
            return (b"", self._stderr)

    async def fake_create(*args, **kwargs):
        return DummyProcessFail()

    monkeypatch.setattr(asyncio, 'create_subprocess_exec', fake_create)

    with pytest.raises(RuntimeError) as excinfo:
        await mod.fetch_audio_pcm(url)
    assert "ffmpeg failed" in str(excinfo.value)

@pytest.mark.asyncio
async def test_fetch_audio_pcm_auth_error(tmp_dirs):
    cache_dir, tmp_dir = tmp_dirs
    mod = import_module(cache_dir, tmp_dir)
    with pytest.raises(NotImplementedError):
        await mod.fetch_audio_pcm('http://example.com', username='user', password='pass')

# -- Track name tests --

def test_get_youtube_track_name_success(tmp_dirs, monkeypatch):
    cache_dir, tmp_dir = tmp_dirs
    mod = import_module(cache_dir, tmp_dir)
    url = 'https://youtu.be/TRACKID12345'

    class DYDL:
        def __init__(self, opts): pass
        def __enter__(self): return self
        def __exit__(self, exc_type, exc, tb): pass
        def extract_info(self, url, download=False): return {'title': 'My Track', 'url': 'audio_url'}
        def prepare_filename(self, info, outtmpl): return info['title']

    monkeypatch.setattr(mod, 'YoutubeDL', DYDL)
    name = mod.get_youtube_track_name(url)
    assert name == 'My Track'

    # cached
    name2 = mod.get_youtube_track_name(url)
    assert name2 == 'My Track'


def test_get_youtube_track_name_error(tmp_dirs, monkeypatch):
    cache_dir, tmp_dir = tmp_dirs
    mod = import_module(cache_dir, tmp_dir)
    url = 'https://youtu.be/BADID'

    class DYDLFail:
        def __init__(self, opts): pass
        def __enter__(self): return self
        def __exit__(self, exc_type, exc, tb): pass
        def extract_info(self, url, download=False): raise DownloadError("fail")

    monkeypatch.setattr(mod, 'YoutubeDL', DYDLFail)
    assert mod.get_youtube_track_name(url) is None

# -- Real integration test --
@pytest.mark.asyncio
@pytest.mark.integration
async def test_integration_fetch_and_cache(tmp_dirs):
    cache_dir, tmp_dir = tmp_dirs
    mod = import_module(cache_dir, tmp_dir)

    # Use a short public YouTube video for testing
    url = "https://youtu.be/xYJ63OTMDL4"

    # First fetch: downloads and caches
    path1 = await mod.fetch_audio_pcm(url)
    assert path1.exists()
    size1 = path1.stat().st_size
    assert size1 > 0

    # Second fetch: should use cache without new download
    path2 = await mod.fetch_audio_pcm(url)
    assert path2 == path1
    size2 = path2.stat().st_size
    assert size2 == size1
