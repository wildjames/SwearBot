# type: ignore
import asyncio

import pytest

import balaambot.schedulers.youtube_jobs as ytj
from balaambot import discord_utils


class DummyGuild:
    def __init__(self, id):
        self.id = id


class DummyVC:
    def __init__(self, guild_id):
        self.guild = DummyGuild(guild_id)
        self.loop = asyncio.get_event_loop()

    def play(self, *args, **kwargs):
        self.playing = True


class DummyLogger:
    def __init__(self):
        self.infos = []
        self.errors = []
        self.exceptions = []
        self.warnings = []

    def info(self, msg, *args, **kwargs):
        self.infos.append((msg, args))

    def error(self, msg, *args, **kwargs):
        self.errors.append((msg, args))

    def exception(self, msg, *args, **kwargs):
        self.exceptions.append((msg, args))

    def warning(self, msg, *args, **kwargs):
        self.warnings.append((msg, args))


@pytest.fixture(autouse=True)
def clear_queue():
    """Ensure queue is empty between tests."""
    ytj.youtube_queue.clear()
    yield
    ytj.youtube_queue.clear()


@pytest.fixture
def dummy_logger(monkeypatch):
    """Replace module logger with a dummy one."""
    log = DummyLogger()
    monkeypatch.setattr(ytj, "logger", log)
    return log


@pytest.mark.asyncio
async def test_add_to_queue_first_item_schedules_playback(monkeypatch, dummy_logger):
    vc = DummyVC(guild_id=10)
    recorded = []

    # Patch create_task to record the coroutine passed
    def fake_create_task(coro):
        recorded.append(coro)
        # return a dummy task
        return asyncio.sleep(0)

    monkeypatch.setattr(vc.loop, "create_task", fake_create_task)

    await ytj.add_to_queue(vc, "yt://video1")

    # Queue should have one item
    assert ytj.youtube_queue[10] == ["yt://video1"]

    # create_task called exactly once with a coroutine for _play_next
    assert len(recorded) == 1
    assert asyncio.iscoroutine(recorded[0])


@pytest.mark.asyncio
async def test_add_to_queue_subsequent_items_do_not_schedule(monkeypatch, dummy_logger):
    vc = DummyVC(guild_id=11)
    scheduled = False

    # First invocation: schedule
    monkeypatch.setattr(vc.loop, "create_task", lambda coro: asyncio.sleep(0))
    await ytj.add_to_queue(vc, "first")

    # Second invocation: patch create_task to fail if called
    def fail_create_task(_):
        nonlocal scheduled
        scheduled = True

    monkeypatch.setattr(vc.loop, "create_task", fail_create_task)

    await ytj.add_to_queue(vc, "second")

    # Queue has both items
    assert ytj.youtube_queue[11] == ["first", "second"]

    # create_task should not have been called the second time
    assert not scheduled


@pytest.mark.asyncio
async def test_add_to_queue_create_task_fails_clears_queue(monkeypatch):
    vc = DummyVC(guild_id=12)

    # Patch create_task to raise
    def bad_create_task(_):
        raise RuntimeError("no loop")

    monkeypatch.setattr(vc.loop, "create_task", bad_create_task)

    with pytest.raises(RuntimeError):
        await ytj.add_to_queue(vc, "failyt")

    # Queue should be cleared on failure
    assert 12 not in ytj.youtube_queue


@pytest.mark.asyncio
async def test_play_next_no_queue(dummy_logger):
    vc = DummyVC(guild_id=20)
    # ensure empty or missing queue
    await ytj._play_next(vc)

    # Should log "No more tracks..." and remove any key
    assert 20 not in ytj.youtube_queue


@pytest.mark.asyncio
async def test_play_next_success(monkeypatch, dummy_logger):
    vc = DummyVC(guild_id=21)
    url = "yt://abc"
    ytj.youtube_queue[21] = [url]

    # Dummy mixer that records calls
    class DummyMixer:
        def __init__(self):
            self.played = []

        async def play_youtube(self, play_url, after_play=None, before_play=None):
            # simulate immediate playback
            assert play_url == url
            # call the after_play callback to simulate end
            if after_play:
                after_play()

    dummy_mixer = DummyMixer()

    # Patch ensure_mixer to return our dummy
    monkeypatch.setattr(ytj, "ensure_mixer", lambda vc: dummy_mixer)

    # Run play_next
    await ytj._play_next(vc)

    # After playback, queue should be empty and key removed
    assert 21 not in ytj.youtube_queue


@pytest.mark.asyncio
async def test_play_next_mixer_failure(dummy_logger, monkeypatch):
    vc = DummyVC(guild_id=22)
    ytj.youtube_queue[22] = ["badurl"]

    # Patch ensure_mixer to raise
    def bad_mixer(vc):
        raise RuntimeError("mixer bad")

    monkeypatch.setattr(ytj, "ensure_mixer", bad_mixer)

    await ytj._play_next(vc)

    # Queue should be cleared on exception
    assert 22 not in ytj.youtube_queue
    # Exception logged
    assert dummy_logger.exceptions, "Expected exception log for mixer failure"


@pytest.mark.asyncio
async def test_play_next_play_youtube_raises(dummy_logger, monkeypatch):
    vc = DummyVC(guild_id=23)
    ytj.youtube_queue[23] = ["url23"]

    # Return a dummy mixer whose play_youtube raises
    class Mixer:
        async def play_youtube(self, *_):
            raise RuntimeError("play error")

    monkeypatch.setattr(ytj, "ensure_mixer", lambda vc: Mixer())
    await ytj._play_next(vc)

    # Queue should be cleared
    assert 23 not in ytj.youtube_queue
    assert dummy_logger.exceptions, "Expected exception log for play failure"


def test_get_current_track_empty():
    vc = DummyVC(guild_id=30)
    assert ytj.get_current_track(vc) is None


def test_get_current_track_non_empty():
    vc = DummyVC(guild_id=31)
    ytj.youtube_queue[31] = ["first", "second"]
    assert ytj.get_current_track(vc) == "first"


@pytest.mark.asyncio
async def test_skip_success(monkeypatch, dummy_logger):
    vc = DummyVC(guild_id=40)

    class Mixer:
        def __init__(self):
            self.skipped = False

        def skip_current_tracks(self):
            self.skipped = True

    mixer = Mixer()
    # Patch ensure_mixer to return our mixer
    monkeypatch.setattr(ytj, "ensure_mixer", lambda vc: mixer)

    await ytj.skip(vc)
    assert mixer.skipped


@pytest.mark.asyncio
async def test_skip_raises(monkeypatch, dummy_logger):
    vc = DummyVC(guild_id=41)

    class Mixer:
        def skip_current_tracks(self):
            raise RuntimeError("skip fail")

    mixer = Mixer()
    monkeypatch.setattr(ytj, "ensure_mixer", lambda vc: mixer)

    await ytj.skip(vc)
    assert dummy_logger.exceptions, "Expected exception log on skip failure"


@pytest.mark.asyncio
async def test_clear_and_list_queue():
    vc = DummyVC(guild_id=50)
    ytj.youtube_queue[50] = ["a", "b", "c"]

    await ytj.clear_queue(vc)
    assert 50 in ytj.youtube_queue

    # list_queue on empty
    result = await ytj.list_queue(vc)
    assert result == ["a"]


@pytest.mark.asyncio
async def test_list_queue_with_items():
    vc = DummyVC(guild_id=51)
    ytj.youtube_queue[51] = ["x", "y"]
    result = await ytj.list_queue(vc)
    assert result == ["x", "y"]


@pytest.mark.asyncio
async def test_stop_success(monkeypatch, dummy_logger):
    vc = DummyVC(guild_id=60)
    ytj.youtube_queue[60] = ["one", "two"]

    class Mixer:
        def __init__(self):
            self.stopped = False

        def clear_tracks(self):
            self.stopped = True

        def pause(self):
            # simulate pause error to check exception logging
            raise RuntimeError("pause fail")

    mixer = Mixer()
    monkeypatch.setattr(ytj, "ensure_mixer", lambda vc: mixer)

    await ytj.stop(vc)
    assert mixer.stopped
    assert 60 not in ytj.youtube_queue
    assert dummy_logger.exceptions, "Expected exception log on pause failure"


@pytest.mark.asyncio
async def test_stop_stop_raises(monkeypatch, dummy_logger):
    vc = DummyVC(guild_id=61)
    ytj.youtube_queue[61] = ["one"]

    class Mixer:
        def clear_tracks(self):
            raise RuntimeError("clear fail")

        def pause(self):
            pass

    mixer = Mixer()
    monkeypatch.setattr(ytj, "ensure_mixer", lambda vc: mixer)

    await ytj.stop(vc)
    # queue cleared despite clear_tracks exception
    assert 61 not in ytj.youtube_queue
    assert dummy_logger.exceptions, "Expected exception log on clear_tracks failure"


@pytest.mark.asyncio
async def test_maybe_preload_skips_cached(monkeypatch, dummy_logger):
    vc = DummyVC(guild_id=70)
    queue = ["url1", "url2", "url3"]
    class Mixer:
        SAMPLE_RATE = 48000
        CHANNELS = 2
    mixer = Mixer()
    monkeypatch.setattr(ytj, "ensure_mixer", lambda vc: mixer)
    class Path:
        def __init__(self, exists): self._exists = exists
        def exists(self): return self._exists
    cache_map = {"url2": Path(True), "url3": Path(True)}
    monkeypatch.setattr(ytj, "get_cache_path", lambda url, sr, ch: cache_map.get(url, Path(False)))
    recorded = []
    async def fake_run(executor, func, url, opus_tmp, pcm_tmp, cache_path, sr, ch):
        recorded.append(url)
    vc.loop.run_in_executor = fake_run
    await ytj._maybe_preload_next_tracks(vc, queue)
    assert recorded == []


@pytest.mark.asyncio
async def test_maybe_preload_download_and_remove_on_failure(monkeypatch, dummy_logger):
    vc = DummyVC(guild_id=71)
    queue = ["url1", "url2", "url3"]
    class Mixer:
        SAMPLE_RATE = 44100
        CHANNELS = 1
    mixer = Mixer()
    monkeypatch.setattr(ytj, "ensure_mixer", lambda vc: mixer)
    monkeypatch.setattr(ytj, "get_cache_path", lambda url, sr, ch: type("P", (), {"exists": lambda self: False})())
    monkeypatch.setattr(ytj, "get_temp_paths", lambda url: ("opus_tmp", "pcm_tmp"))
    recorded = []
    async def fake_run(executor, func, url, opus_tmp, pcm_tmp, cache_path, sr, ch):
        if url == "url2":
            raise Exception("fail")
        recorded.append(url)
    vc.loop.run_in_executor = fake_run
    await ytj._maybe_preload_next_tracks(vc, queue)
    assert "url2" not in queue
    assert "url3" in recorded


@pytest.mark.asyncio
async def test_create_before_after_functions_before_and_after(monkeypatch, dummy_logger):
    vc = DummyVC(guild_id=80)
    url1, url2 = "yt://1", "yt://2"
    ytj.youtube_queue[80] = [url1, url2]
    class TextChannel:
        def __init__(self): self.sent = []
        def send(self, content):
            self.sent.append(content)
            return asyncio.sleep(0)
    channel = TextChannel()
    vc.guild.get_channel = lambda id: channel
    ytj.video_metadata.clear()
    ytj.video_metadata[url1] = {"title": "Title1", "url": "http://u1"}
    calls = []
    vc.loop.create_task = lambda coro: calls.append(coro) or asyncio.sleep(0)
    before_play, after_play = ytj.create_before_after_functions(url1, vc, text_channel=100)
    before_play()
    assert channel.sent and "Now playing" in channel.sent[0]
    before_calls = len(calls)
    after_play()
    assert ytj.youtube_queue[80] == [url2]
    assert len(calls) > before_calls


@pytest.mark.asyncio
async def test_after_play_finishes_queue(monkeypatch, dummy_logger):
    vc = DummyVC(guild_id=81)
    url = "yt://finish"
    ytj.youtube_queue[81] = [url]
    class TextChannel:
        def __init__(self): self.sent = []
        def send(self, content):
            self.sent.append(content)
            return asyncio.sleep(0)
    channel = TextChannel()
    vc.guild.get_channel = lambda id: channel
    calls = []
    vc.loop.create_task = lambda coro: calls.append(coro) or asyncio.sleep(0)
    _, after_play = ytj.create_before_after_functions(url, vc, text_channel=200)
    after_play()
    assert 81 not in ytj.youtube_queue
    assert channel.sent and "Finished playing queue" in channel.sent[0]


def test_before_after_no_text_channel(dummy_logger):
    vc = DummyVC(guild_id=90)
    ytj.youtube_queue[90] = ["u"]
    before_play, after_play = ytj.create_before_after_functions("u", vc, text_channel=None)
    before_play()
    after_play()
