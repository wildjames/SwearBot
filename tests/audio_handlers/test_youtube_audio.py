import pytest
import asyncio
from pathlib import Path
from yt_dlp import DownloadError

import balaambot.utils as utils
# Adjust import path below to match your module's filename
import balaambot.audio_handlers.youtube_audio as handler

pytestmark = pytest.mark.asyncio

@ pytest.fixture(autouse=True)
def clear_state():
    # Clear cached metadata and locks before each test
    handler.video_metadata.clear()
    handler._download_locks.clear()
    yield
    handler.video_metadata.clear()
    handler._download_locks.clear()

# Tests for get_youtube_track_metadata
async def test_invalid_url(monkeypatch):
    monkeypatch.setattr(handler, 'is_valid_youtube_url', lambda url: False)
    result = await handler.get_youtube_track_metadata('bad_url')
    assert result is None

async def test_cached_metadata(monkeypatch):
    monkeypatch.setattr(handler, 'is_valid_youtube_url', lambda url: True)
    cached = handler.VideoMetadata(url='u', title='t', runtime=5, runtime_str='0:05')
    handler.video_metadata['u'] = cached
    result = await handler.get_youtube_track_metadata('u')
    assert result is cached

async def test_download_error(monkeypatch):
    monkeypatch.setattr(handler, 'is_valid_youtube_url', lambda url: True)
    class DummyYDL:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def extract_info(self, url, download): raise DownloadError('fail')
    monkeypatch.setattr(handler, 'YoutubeDL', lambda opts: DummyYDL())
    result = await handler.get_youtube_track_metadata('u')
    assert result is None

async def test_unexpected_exception(monkeypatch):
    monkeypatch.setattr(handler, 'is_valid_youtube_url', lambda url: True)
    class DummyYDL:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def extract_info(self, url, download): raise ValueError('boom')
    monkeypatch.setattr(handler, 'YoutubeDL', lambda opts: DummyYDL())
    result = await handler.get_youtube_track_metadata('u')
    assert result is None

async def test_successful_metadata(monkeypatch):
    monkeypatch.setattr(handler, 'is_valid_youtube_url', lambda url: True)
    info = {'title': 'My Video', 'duration': 123}
    class DummyYDL:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def extract_info(self, url, download): return info
    monkeypatch.setattr(handler, 'YoutubeDL', lambda opts: DummyYDL())
    monkeypatch.setattr(utils, 'sec_to_string', lambda s: '2:03')
    result = await handler.get_youtube_track_metadata('url1')
    assert result == {'url': 'url1', 'title': 'My Video', 'runtime': 123, 'runtime_str': '2:03'}
    assert handler.video_metadata['url1'] == result

# Tests for fetch_audio_pcm
async def test_fetch_audio_cache_hit(monkeypatch, tmp_path):
    cache = tmp_path / 'audio.pcm'
    cache.write_bytes(b'data')
    monkeypatch.setattr(handler, 'get_cache_path', lambda u, sr, ch: cache)
    result = await handler.fetch_audio_pcm('any_url')
    assert result == cache

async def test_fetch_audio_auth(monkeypatch):
    monkeypatch.setattr(handler, 'get_cache_path', lambda u, sr, ch: Path('/tmp/nonexistent'))
    with pytest.raises(NotImplementedError):
        await handler.fetch_audio_pcm('u', username='user', password='pass')

async def test_fetch_audio_download_error(monkeypatch, tmp_path):
    cache = tmp_path / 'out.pcm'
    monkeypatch.setattr(handler, 'get_cache_path', lambda u, sr, ch: cache)
    monkeypatch.setattr(handler, 'get_temp_paths', lambda u: (tmp_path / 'a.opus', tmp_path / 'b.pcm'))
    async def fail_download(u, p, username=None, password=None): raise DownloadError('dl fail')
    monkeypatch.setattr(handler, '_download_opus', fail_download)
    async def dummy_meta(u): return None
    monkeypatch.setattr(handler, 'get_youtube_track_metadata', dummy_meta)
    with pytest.raises(RuntimeError) as ei:
        await handler.fetch_audio_pcm('u')
    assert 'Failed to download audio for u' in str(ei.value)

async def test_fetch_audio_success(monkeypatch, tmp_path):
    cache = tmp_path / 'cached.pcm'
    opus_tmp = tmp_path / 't.opus'
    pcm_tmp = tmp_path / 't.pcm'
    monkeypatch.setattr(handler, 'get_cache_path', lambda u, sr, ch: cache)
    monkeypatch.setattr(handler, 'get_temp_paths', lambda u: (opus_tmp, pcm_tmp))
    async def fake_download(u, p, username=None, password=None): p.write_bytes(b'o')
    monkeypatch.setattr(handler, '_download_opus', fake_download)
    async def fake_meta(u): return {'url': u, 'title': 't', 'runtime': 1, 'runtime_str': '0:01'}
    monkeypatch.setattr(handler, 'get_youtube_track_metadata', fake_meta)
    async def fake_convert(o, p, c, sr, ch): p.write_bytes(b'p'); p.replace(c)
    monkeypatch.setattr(handler, '_convert_opus_to_pcm', fake_convert)
    result = await handler.fetch_audio_pcm('u')
    assert result == cache

# Tests for _download_opus
async def test_download_opus_failure(monkeypatch, tmp_path):
    url = 'u'
    opus_tmp = tmp_path / 'file'
    class DummyYDL:
        def __init__(self, opts): pass
        def download(self, lst): pass
    monkeypatch.setattr(handler, 'YoutubeDL', lambda opts: DummyYDL(opts))
    with pytest.raises(RuntimeError) as ei:
        await handler._download_opus(url, opus_tmp)
    assert 'yt-dlp failed to produce' in str(ei.value)


async def test_download_opus_success(monkeypatch, tmp_path):
    url = "u"
    opus_tmp = tmp_path / "file"

    # Stub out the new synchronous downloader to write a dummy .opus file
    def fake_sync_download(opts, target_url) -> None:
        outtmpl = opts["outtmpl"]
        # the real code will append ".opus" to this
        opus_file = Path(f"{outtmpl}.opus")
        opus_file.parent.mkdir(parents=True, exist_ok=True)
        opus_file.write_bytes(b"dummy opus data")

    # Patch the helper so that run_in_executor just calls our fake
    monkeypatch.setattr(handler, "_sync_download", fake_sync_download)
    monkeypatch.setattr(handler.utils, "FUTURES_EXECUTOR", None)

    # Now run the async download – it should create file.opus and then rename it to file
    await handler._download_opus(url, opus_tmp)

    # Assert that the final opus_tmp (no extension) exists
    assert opus_tmp.exists()
    # And that it’s non-empty
    assert opus_tmp.read_bytes() == b"dummy opus data"

# Tests for _convert_opus_to_pcm
async def test_convert_opus_to_pcm_failure(monkeypatch, tmp_path):
    opus_tmp = tmp_path / 'in.opus'
    pcm_tmp = tmp_path / 'out.pcm'
    cache = tmp_path / 'c.pcm'
    opus_tmp.write_bytes(b'd')
    class DummyProcess:
        def __init__(self): self.returncode = 1
        async def communicate(self): return (b'', b'err')
    async def fake_exec(*args, **kwargs): return DummyProcess()
    monkeypatch.setattr(asyncio, 'create_subprocess_exec', fake_exec)
    with pytest.raises(RuntimeError) as ei:
        await handler._convert_opus_to_pcm(opus_tmp, pcm_tmp, cache, 8000, 1)
    assert 'ffmpeg failed:' in str(ei.value)

async def test_convert_opus_to_pcm_success(monkeypatch, tmp_path):
    opus_tmp = tmp_path / 'in.opus'
    pcm_tmp = tmp_path / 'out.pcm'
    cache = tmp_path / 'c.pcm'
    opus_tmp.write_bytes(b'd')
    pcm_tmp.write_bytes(b'p')
    class DummyProcess:
        def __init__(self): self.returncode = 0
        async def communicate(self): return (b'', b'')
    async def fake_exec(*args, **kwargs): return DummyProcess()
    monkeypatch.setattr(asyncio, 'create_subprocess_exec', fake_exec)
    await handler._convert_opus_to_pcm(opus_tmp, pcm_tmp, cache, 16000, 2)
    assert not opus_tmp.exists()
    assert cache.exists()

# Tests for get_playlist_video_urls
async def test_playlist_not_playlist(monkeypatch):
    monkeypatch.setattr(handler, 'check_is_playlist', lambda u: False)
    result = await handler.get_playlist_video_urls('u')
    assert result == []

async def test_playlist_download_error(monkeypatch):
    monkeypatch.setattr(handler, 'check_is_playlist', lambda u: True)
    class DummyYDL:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def extract_info(self, u, download): raise DownloadError('fail')
    monkeypatch.setattr(handler, 'YoutubeDL', lambda opts: DummyYDL())
    result = await handler.get_playlist_video_urls('u')
    assert result == []

async def test_playlist_exception(monkeypatch):
    monkeypatch.setattr(handler, 'check_is_playlist', lambda u: True)
    class DummyYDL:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def extract_info(self, u, download): raise ValueError('err')
    monkeypatch.setattr(handler, 'YoutubeDL', lambda opts: DummyYDL())
    result = await handler.get_playlist_video_urls('u')
    assert result == []

async def test_playlist_info_none(monkeypatch):
    monkeypatch.setattr(handler, 'check_is_playlist', lambda u: True)
    class DummyYDL:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def extract_info(self, u, download): return None
    monkeypatch.setattr(handler, 'YoutubeDL', lambda opts: DummyYDL())
    with pytest.raises(TypeError):
        await handler.get_playlist_video_urls('u')

async def test_playlist_entries(monkeypatch):
    monkeypatch.setattr(handler, 'check_is_playlist', lambda u: True)
    entries = [{'id': '123'}, {'noid': 'x'}, {'id': None}, {'id': 'xyz'}]
    class DummyYDL:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def extract_info(self, u, download): return {'entries': entries}
    monkeypatch.setattr(handler, 'YoutubeDL', lambda opts: DummyYDL())
    result = await handler.get_playlist_video_urls('u')
    assert result == ['https://www.youtube.com/watch?v=123', 'https://www.youtube.com/watch?v=xyz']

# Tests for search_youtube
async def test_search_download_error(monkeypatch):
    async def fake_to_thread(func): raise DownloadError('fail')
    monkeypatch.setattr(asyncio, 'to_thread', fake_to_thread)
    result = await handler.search_youtube('query')
    assert result == []

async def test_search_exception(monkeypatch):
    async def fake_to_thread(func): raise ValueError('boom')
    monkeypatch.setattr(asyncio, 'to_thread', fake_to_thread)
    result = await handler.search_youtube('query')
    assert result == []

async def test_search_info_none(monkeypatch):
    async def fake_to_thread(func, *args): return None
    monkeypatch.setattr(asyncio, 'to_thread', fake_to_thread)
    with pytest.raises(TypeError):
        await handler.search_youtube('query')

async def test_search_valid(monkeypatch):
    entries = [
        {'id': '1', 'title': 'A', 'duration': 10},
        {'id': '2', 'title': None, 'duration': 5},
        {'id': None, 'title': 'C', 'duration': 5},
        {'id': '3', 'title': 'D', 'duration': 15},
    ]
    info = {'entries': entries}
    async def fake_to_thread(func, *args): return info
    monkeypatch.setattr(asyncio, 'to_thread', fake_to_thread)
    result = await handler.search_youtube('q', n=2)
    assert result == [
        ('https://www.youtube.com/watch?v=1', 'A', 10),
        ('https://www.youtube.com/watch?v=3', 'D', 15),
    ]
