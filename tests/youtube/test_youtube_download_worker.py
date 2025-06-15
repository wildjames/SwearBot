import pytest
import logging
import subprocess
from pathlib import Path
import json

import balaambot.youtube.download_worker as download_module
from balaambot.youtube.download_worker import download_and_convert, get_metadata
from balaambot.youtube.utils import VideoMetadata


def get_dummy_logger():
    logger = logging.getLogger("test_logger")
    logger.addHandler(logging.NullHandler())
    return logger


class DummyYDLDownload:
    def __init__(self, opts):
        self.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def download(self, urls):
        # Simulate creation of the expected .opus file based on outtmpl
        outtmpl = Path(self.opts['outtmpl'])
        opus_path = outtmpl.with_suffix('.opus')
        opus_path.parent.mkdir(parents=True, exist_ok=True)
        opus_path.write_bytes(b'fake opus data')


class DummyYDLExtractInfo:
    def __init__(self, opts):
        self.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def extract_info(self, url, download):
        # Return dummy metadata
        return {"title": "Test Title", "duration": 42}


class DummyYDLNoDownload:
    def __init__(self, opts):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def download(self, urls):
        # Do not create any file to simulate failure
        pass


class DummyYDLNoInfo:
    def __init__(self, opts):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def extract_info(self, url, download):
        return None


def test_download_and_convert_success(monkeypatch, tmp_path):
    opus_tmp = tmp_path / "work" / "video.opus"
    pcm_tmp = tmp_path / "work" / "video.pcm"
    cache_path = tmp_path / "cache" / "video.pcm"

    # Ensure cache directory exists so replace can succeed
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    # Patch YoutubeDL to our dummy downloader
    monkeypatch.setattr(download_module, 'YoutubeDL', DummyYDLDownload)

    # Patch subprocess.run to simulate successful ffmpeg call
    def fake_run(cmd, capture_output, check):
        # Simulate ffmpeg producing the pcm file
        dest = Path(cmd[-1])
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b'pcm data')
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(download_module.subprocess, 'run', fake_run)

    # Execute
    download_and_convert(
        get_dummy_logger(),
        "http://example.com/video",
        opus_tmp,
        pcm_tmp,
        cache_path,
        sample_rate=16000,
        channels=1
    )

    # Assert that the cache file exists with correct content
    assert cache_path.exists()
    assert cache_path.read_bytes() == b'pcm data'

    # Original .opus and .pcm temporary files should be cleaned up
    assert not (tmp_path / "work" / "video.opus").exists()
    assert not (tmp_path / "work" / "video.pcm").exists()


def test_download_and_convert_no_opus(monkeypatch, tmp_path):
    opus_tmp = tmp_path / "work" / "video.opus"
    pcm_tmp = tmp_path / "work" / "video.pcm"
    cache_path = tmp_path / "cache" / "video.pcm"

    # Patch YoutubeDL to simulate no download
    monkeypatch.setattr(download_module, 'YoutubeDL', DummyYDLNoDownload)

    with pytest.raises(RuntimeError) as exc:
        download_and_convert(
            get_dummy_logger(),
            "http://example.com/video",
            opus_tmp,
            pcm_tmp,
            cache_path,
            sample_rate=44100,
            channels=2
        )
    assert "yt-dlp failed to produce" in str(exc.value)


def test_download_and_convert_ffmpeg_fail(monkeypatch, tmp_path):
    opus_tmp = tmp_path / "work" / "video.opus"
    pcm_tmp = tmp_path / "work" / "video.pcm"
    cache_path = tmp_path / "cache" / "video.pcm"

    # Patch YoutubeDL to create the .opus file
    monkeypatch.setattr(download_module, 'YoutubeDL', DummyYDLDownload)

    # Patch subprocess.run to simulate ffmpeg failure
    def fake_run_fail(cmd, capture_output, check):
        return subprocess.CompletedProcess(cmd, 1, stderr=b"ffmpeg error")

    monkeypatch.setattr(download_module.subprocess, 'run', fake_run_fail)

    with pytest.raises(RuntimeError) as exc:
        download_and_convert(
            get_dummy_logger(),
            "http://example.com/video",
            opus_tmp,
            pcm_tmp,
            cache_path,
            sample_rate=44100,
            channels=2
        )
    assert "ffmpeg failed" in str(exc.value)
    assert not pcm_tmp.exists()


def test_get_metadata_success(monkeypatch, tmp_path):
    # Patch YoutubeDL and dependencies
    monkeypatch.setattr(download_module, 'YoutubeDL', DummyYDLExtractInfo)
    monkeypatch.setattr(download_module, 'sec_to_string', lambda s: f"{s}s")
    meta_path = tmp_path / "meta.json"
    monkeypatch.setattr(download_module, 'get_metadata_path', lambda url: meta_path)

    meta = get_metadata(get_dummy_logger(), "http://example.com/video")

    assert isinstance(meta, VideoMetadata)
    assert meta.url == "http://example.com/video"
    assert meta.title == "Test Title"
    assert meta.runtime == 42
    assert meta.runtime_str == "42s"

    data = json.loads(meta_path.read_text(encoding='utf-8'))
    assert data == {
        'url': meta.url,
        'title': meta.title,
        'runtime': meta.runtime,
        'runtime_str': meta.runtime_str
    }


def test_get_metadata_failure(monkeypatch):
    monkeypatch.setattr(download_module, 'YoutubeDL', DummyYDLNoInfo)

    with pytest.raises(ValueError) as exc:
        get_metadata(get_dummy_logger(), "http://example.com/video")
    assert "Failed to get youtube metadata" in str(exc.value)
