# type: ignore
import asyncio
import os
import importlib
import sys
from pathlib import Path
import pytest
from yt_dlp.utils import DownloadError

# Helper to import the module under test with custom dirs
def import_module(tmp_cache_root: Path):
    # Set environment variable before import
    os.environ['AUDIO_CACHE_DIR'] = str(tmp_cache_root)

    # Ensure a fresh import
    module_name = 'src.audio_handlers.youtube_audio'
    if module_name in sys.modules:
        del sys.modules[module_name]
    module = importlib.import_module(module_name)
    return module

# Fixture for temporary cache and tmp directories
@pytest.fixture
def tmp_cache_root(tmp_path):
    root = tmp_path / 'cache_root'
    root.mkdir()
    return root

# -- Directory creation tests --
def test_directories_created(tmp_cache_root):
    mod = import_module(tmp_cache_root)

    # The module should create and expose audio_cache_dir and audio_tmp_dir
    assert hasattr(mod, 'audio_cache_dir')
    assert hasattr(mod, 'audio_tmp_dir')

    # In the new code, AUDIO_CACHE_DIR is treated as the root, and subdirectories
    # 'cached' and 'downloading' are created underneath it
    expected_cache = (tmp_cache_root / 'cached').resolve()
    expected_tmp = (tmp_cache_root / 'downloading').resolve()

    assert mod.audio_cache_dir == expected_cache
    assert mod.audio_tmp_dir == expected_tmp

    # Both directories should exist on disk
    assert mod.audio_cache_dir.exists()
    assert mod.audio_tmp_dir.exists()

# -- URL/id and path tests --

@pytest.mark.parametrize("url,expected_id", [
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("http://youtu.be/ABCDEFGHIJK", "ABCDEFGHIJK"),
    ("https://music.youtube.com/watch?v=12345678901&list=PL", "12345678901"),
    ("invalid_url", None),
])
def test_get_video_id_param(tmp_cache_root, url, expected_id):
    mod = import_module(tmp_cache_root)
    assert mod._get_video_id(url) == expected_id


def test_get_video_id_various_urls(tmp_cache_root):
    mod = import_module(tmp_cache_root)
    # Additional URL forms
    assert mod._get_video_id("https://youtu.be/12345678901") == "12345678901"
    assert mod._get_video_id("https://www.youtube.com/embed/ZYXWVUTSRQP") == "ZYXWVUTSRQP"

@pytest.mark.parametrize("url,rate,channels,expected_suffix", [
    ("https://youtu.be/ABCDEFGHIJK", 48000, 2, "ABCDEFGHIJK_48000Hz_2ch.pcm"),
    ("foo/bar", 44100, 1, "foo_bar_44100Hz_1ch.pcm"),
])
def test_get_cache_path_param(tmp_cache_root, url, rate, channels, expected_suffix):
    mod = import_module(tmp_cache_root)
    path = mod._get_cache_path(url, rate, channels)
    expected_parent = (tmp_cache_root / 'cached').resolve()
    assert path.parent == expected_parent
    assert path.name == expected_suffix

# -- Temp path tests --
@pytest.mark.parametrize("url", [
    "https://youtu.be/IDABCDE1234",
    "https://www.youtube.com/watch?v=XYZ12345678",
])
def test_get_temp_paths(tmp_cache_root, url):
    mod = import_module(tmp_cache_root)
    opus_tmp, pcm_tmp = mod._get_temp_paths(url)
    vid = mod._get_video_id(url)
    expected_tmp_dir = (tmp_cache_root / 'downloading').resolve()
    assert opus_tmp.parent == expected_tmp_dir
    assert pcm_tmp.parent == expected_tmp_dir
    assert opus_tmp.name == f"{vid}.opus.part"
    assert pcm_tmp.name == f"{vid}.pcm.part"

# -- is_valid_youtube_url tests --
@pytest.mark.parametrize("url,valid", [
    ("https://www.youtube.com/watch?v=abcdEFGHijk", True),
    ("https://youtu.be/abcdEFGHijk", True),
    ("https://www.youtube.com/watch?v=shortID", False),
    ("not a url", False),
])
def test_is_valid_youtube_url(tmp_cache_root, url, valid):
    mod = import_module(tmp_cache_root)
    assert mod.is_valid_youtube_url(url) == valid

# -- is_valid_youtube_playlist tests --
@pytest.mark.parametrize("url,valid", [
    ("https://www.youtube.com/playlist?list=PL67890", True),
    ("https://www.youtube.com/watch?v=PL123456789&list=PL67890", True),
    ("https://youtu.be/XYZ12345678?list=ABCDEF&foo=bar", True),
    ("https://www.youtube.com/watch?v=abcdefghiJK", False),
    ("not a playlist", False),
])
def test_is_valid_youtube_playlist(tmp_cache_root, url, valid):
    mod = import_module(tmp_cache_root)
    assert mod.is_valid_youtube_playlist(url) == valid

# -- Sync API tests for PCM retrieval/removal --

def test_get_audio_pcm_and_remove(tmp_cache_root):
    mod = import_module(tmp_cache_root)
    url = "https://youtu.be/TESTVIDEOID"
    cache_dir = mod.audio_cache_dir

    # Nothing cached initially
    assert mod.get_audio_pcm(url) is None

    # Create a fake PCM file in the cache directory
    filename = f"TESTVIDEOID_{mod.DEFAULT_SAMPLE_RATE}Hz_{mod.DEFAULT_CHANNELS}ch.pcm"
    pcm_path = cache_dir / filename
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
    # Removing again should return False
    assert not mod.remove_audio_pcm(url)


# -- Async fetch_audio_pcm tests --

@pytest.mark.asyncio
async def test_fetch_audio_pcm_cached(tmp_cache_root):
    mod = import_module(tmp_cache_root)
    url = 'https://youtu.be/ZZZZZZZZZZZ'
    cache_path = mod._get_cache_path(url, mod.DEFAULT_SAMPLE_RATE, mod.DEFAULT_CHANNELS)
    # Pre-cache data
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(b'data')

    # Should return cached path without calling download
    result = await mod.fetch_audio_pcm(url)
    assert result == cache_path
    assert result.read_bytes() == b'data'

@pytest.mark.asyncio
async def test_fetch_audio_pcm_success(tmp_cache_root, monkeypatch):
    mod = import_module(tmp_cache_root)
    url = "https://youtu.be/SOMEID12345"
    cache_dir = mod.audio_cache_dir

    # Stub out download & conversion internals
    async def fake_download_opus(u, opus_tmp):
        opus_tmp.parent.mkdir(parents=True, exist_ok=True)
        # simulate yt-dlp output: create .opus.part file
        opus_tmp.write_bytes(b"")

    async def fake_convert_opus(opus_tmp, pcm_tmp, cache_path, sample_rate, channels):
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(b"\x00" * 10)

    async def fake_get_youtube_track_metadata(url):
        return {"title": "fake title", "runtime": 0, "runtime_str": "00:00:00", "url": url}

    monkeypatch.setattr(mod, '_download_opus', fake_download_opus)
    monkeypatch.setattr(mod, '_convert_opus_to_pcm', fake_convert_opus)
    monkeypatch.setattr(mod, "get_youtube_track_metadata", fake_get_youtube_track_metadata)

    # First fetch should invoke stubs and create cache
    result = await mod.fetch_audio_pcm(url)
    expected = cache_dir / f"SOMEID12345_{mod.DEFAULT_SAMPLE_RATE}Hz_{mod.DEFAULT_CHANNELS}ch.pcm"
    assert result == expected
    assert expected.exists()

    # Second fetch should use cache
    result2 = await mod.fetch_audio_pcm(url)
    assert result2 == expected

@pytest.mark.asyncio
async def test_fetch_audio_pcm_ffmpeg_fail(tmp_cache_root, monkeypatch):
    mod = import_module(tmp_cache_root)
    url = "https://youtu.be/FAILID00001"

    # Stub download to create an opus_tmp file
    async def fake_download_opus(u, opus_tmp):
        opus_tmp.parent.mkdir(parents=True, exist_ok=True)
        opus_tmp.write_bytes(b"")

    class DummyProcessFail:
        def __init__(self, returncode=1, stderr=b"error"):
            self.returncode = returncode
            self._stderr = stderr
        async def communicate(self):
            return (b"", self._stderr)

    async def fake_create(*args, **kwargs):
        return DummyProcessFail()

    async def fake_get_youtube_track_metadata(url):
        return {"title": "fake title", "runtime": 0, "runtime_str": "00:00:00", "url": url}

    monkeypatch.setattr(mod, '_download_opus', fake_download_opus)
    monkeypatch.setattr(mod, "get_youtube_track_metadata", fake_get_youtube_track_metadata)
    monkeypatch.setattr(asyncio, 'create_subprocess_exec', fake_create)

    with pytest.raises(RuntimeError) as excinfo:
        await mod.fetch_audio_pcm(url)
    assert "ffmpeg failed" in str(excinfo.value)

@pytest.mark.asyncio
async def test_fetch_audio_pcm_auth_error(tmp_cache_root):
    mod = import_module(tmp_cache_root)
    with pytest.raises(NotImplementedError):
        await mod.fetch_audio_pcm('http://example.com', username='user', password='pass')

# -- Track name tests --

@pytest.mark.asyncio
async def test_get_youtube_track_metadata_success_and_format(tmp_cache_root, monkeypatch):
    mod = import_module(tmp_cache_root)
    url = 'https://youtu.be/TRACKID12345'

    # Simulate metadata with duration > 1 hour
    class DYDL:
        def __init__(self, opts): pass
        def __enter__(self): return self
        def __exit__(self, exc_type, exc, tb): pass
        def extract_info(self, url, download=False):
            return {'title': 'My Track', 'duration': 3665}

    monkeypatch.setattr(mod, 'YoutubeDL', DYDL)
    meta = await mod.get_youtube_track_metadata(url)
    assert meta['title'] == 'My Track'
    assert isinstance(meta['runtime'], int)
    assert meta['runtime'] == 3665
    assert meta['runtime_str'] == '01:01:05'
    assert meta['url'] == url

    # Cached behavior
    meta2 = await mod.get_youtube_track_metadata(url)
    assert meta2 == meta

@pytest.mark.asyncio
async def test_get_youtube_track_metadata_error(tmp_cache_root, monkeypatch):
    mod = import_module(tmp_cache_root)
    url = 'https://youtu.be/BADID'

    class DYDLFail:
        def __init__(self, opts): pass
        def __enter__(self): return self
        def __exit__(self, exc_type, exc, tb): pass
        def extract_info(self, url, download=False): raise DownloadError("fail")

    monkeypatch.setattr(mod, 'YoutubeDL', DYDLFail)
    assert await mod.get_youtube_track_metadata(url) is None

# -- Playlist URL tests --
@pytest.mark.parametrize("url,expected", [
    ("https://www.youtube.com/playlist?list=PL67890", True),
    ("https://www.youtube.com/watch?v=PL123456789&list=PL67890", True),
    ("https://www.youtube.com/playlist?list=PLtyo3aqsNv_Oe686OmaAi1heDjjnxYRmw", True),
    ("https://youtu.be/XYZ12345678?list=ABCDEF&foo=bar", True),
    ("https://www.youtube.com/watch?v=abcdefghiJK", False),
    ("https://youtu.be/abcdefghiJK", False),
    # malformed
    ("not a url at all", False),
])
def test_check_is_playlist(tmp_cache_root, url, expected):
    mod = import_module(tmp_cache_root)
    assert mod.check_is_playlist(url) is expected


# -- get_playlist_video_urls tests --

@pytest.mark.asyncio
async def test_get_playlist_video_urls_no_list(tmp_cache_root):
    mod = import_module(tmp_cache_root)
    # URL without 'list' should immediately return empty list
    url = "https://www.youtube.com/watch?v=abcdefghiJK"
    result = await mod.get_playlist_video_urls(url)
    assert result == []

@pytest.mark.asyncio
async def test_get_playlist_video_urls_info_none(tmp_cache_root, monkeypatch):
    mod = import_module(tmp_cache_root)
    playlist_id = "PLTESTID"
    playlist_url = f"https://www.youtube.com/playlist?list={playlist_id}"

    # Simulate extract_info returning None
    class FakeDLNone:
        def __init__(self, opts): pass
        def __enter__(self): return self
        def __exit__(self, exc_type, exc, tb): pass
        def extract_info(self, url, download=False): return None

    monkeypatch.setattr(mod, 'YoutubeDL', FakeDLNone)
    with pytest.raises(TypeError) as excinfo:
        await mod.get_playlist_video_urls(playlist_url)
    assert "Retrieved info from youtube was None" in str(excinfo.value)

@pytest.mark.asyncio
async def test_get_playlist_video_urls_success(tmp_cache_root, monkeypatch):
    mod = import_module(tmp_cache_root)
    playlist_id = "PLtyo3aqsNv_Oe686OmaAi1heDjjnxYRmw"
    playlist_url = f"https://www.youtube.com/playlist?list={playlist_id}"

    # Stub out YoutubeDL to return a fake playlist
    class FakeDL:
        def __init__(self, opts): pass
        def __enter__(self): return self
        def __exit__(self, exc_type, exc, tb): pass
        def extract_info(self, url, download=False):
            # simulate flat-playlist entries
            return {
                "entries": [
                    {"id": "VID11111111"},
                    {"id": "VID22222222"},
                ]
            }

    monkeypatch.setattr(mod, "YoutubeDL", FakeDL)

    result = await mod.get_playlist_video_urls(playlist_url)
    assert isinstance(result, list)
    assert result == [
        "https://www.youtube.com/watch?v=VID11111111",
        "https://www.youtube.com/watch?v=VID22222222",
    ]

@pytest.mark.asyncio
async def test_get_playlist_video_urls_error(tmp_cache_root, monkeypatch):
    mod = import_module(tmp_cache_root)
    playlist_url = "https://www.youtube.com/playlist?list=PLFAKEID123"

    # Raise DownloadError inside extract_info
    class FailDL:
        def __init__(self, opts): pass
        def __enter__(self): return self
        def __exit__(self, exc_type, exc, tb): pass
        def extract_info(self, url, download=False): raise DownloadError("playlist fetch failed")

    monkeypatch.setattr(mod, "YoutubeDL", FailDL)

    result = await mod.get_playlist_video_urls(playlist_url)
    # On yt-dlp error we return []
    assert result == []

# -- search_youtube tests --

@pytest.mark.asyncio
async def test_search_youtube_success(tmp_cache_root, monkeypatch):
    mod = import_module(tmp_cache_root)

    # Prepare fake entries: include some invalid ones to ensure filtering
    fake_entries = [
        {"id": "VIDA1234567", "title": "First Video", "duration": 120},
        {"id": None, "title": "MissingID", "duration": 90},
        {"id": "VIDB2345678", "title": "Second Video", "duration": None},
        {"id": "VIDC3456789", "title": None, "duration": 150},
        {"id": "VIDD4567890", "title": "Third Video", "duration": 200},
    ]

    class FakeDL:
        def __init__(self, opts): pass
        def __enter__(self): return self
        def __exit__(self, exc_type, exc, tb): pass
        def extract_info(self, search_str, download=False):
            # Return fake entries under 'entries' key
            return {"entries": fake_entries}

    monkeypatch.setattr(mod, "YoutubeDL", FakeDL)

    # Request top 2 valid results
    results = await mod.search_youtube("test query", n=2)
    assert isinstance(results, list)
    # Should filter out entries missing id or title
    assert len(results) == 2
    # First valid entry: ID and title correct
    assert results[0] == ("https://www.youtube.com/watch?v=VIDA1234567", "First Video", 120)
    # Second valid entry: skip invalids, next is VIDD
    assert results[1] == ("https://www.youtube.com/watch?v=VIDD4567890", "Third Video", 200)


@pytest.mark.asyncio
async def test_search_youtube_download_error(tmp_cache_root, monkeypatch):
    mod = import_module(tmp_cache_root)

    class FailDL:
        def __init__(self, opts): pass
        def __enter__(self): return self
        def __exit__(self, exc_type, exc, tb): pass
        def extract_info(self, search_str, download=False): raise DownloadError("search failed")

    monkeypatch.setattr(mod, "YoutubeDL", FailDL)

    results = await mod.search_youtube("anything", n=3)
    assert results == []

@pytest.mark.asyncio
async def test_search_youtube_info_none(tmp_cache_root, monkeypatch):
    mod = import_module(tmp_cache_root)

    class FakeDLNone:
        def __init__(self, opts): pass
        def __enter__(self): return self
        def __exit__(self, exc_type, exc, tb): pass
        def extract_info(self, search_str, download=False): return None

    monkeypatch.setattr(mod, "YoutubeDL", FakeDLNone)

    with pytest.raises(TypeError) as excinfo:
        await mod.search_youtube("no info", n=1)
    assert "Retrieved info from youtube was None" in str(excinfo.value)

# -- Real integration test --
@pytest.mark.asyncio
@pytest.mark.integration
async def test_integration_fetch_and_cache(tmp_cache_root):
    mod = import_module(tmp_cache_root)

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
