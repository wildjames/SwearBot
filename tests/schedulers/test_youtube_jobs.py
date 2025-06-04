# type: ignore
import asyncio
import pytest

import src.schedulers.youtube_jobs as ytj
from src import discord_utils


class DummyGuild:
    def __init__(self, id):
        self.id = id


class DummyVC:
    def __init__(self, guild_id):
        self.guild = DummyGuild(guild_id)
        self.loop = asyncio.get_event_loop()


class DummyLogger:
    def __init__(self):
        self.infos = []
        self.errors = []
        self.exceptions = []

    def info(self, msg, *args, **kwargs):
        self.infos.append((msg, args))

    def error(self, msg, *args, **kwargs):
        self.errors.append((msg, args))

    def exception(self, msg, *args, **kwargs):
        self.exceptions.append((msg, args))


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
    monkeypatch.setattr(
        vc.loop,
        "create_task",
        lambda coro: asyncio.sleep(0)
    )
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

        async def play_youtube(self, play_url, after_play):
            # simulate immediate playback
            assert play_url == url
            # call the after_play callback to simulate end
            after_play(None)

    dummy_mixer = DummyMixer()

    # Patch get_mixer
    monkeypatch.setattr(
        discord_utils,
        "get_mixer_from_voice_client",
        lambda vc_in: asyncio.sleep(0, result=dummy_mixer)
    )

    # Patch create_task on vc.loop to record scheduling of next
    scheduled = []
    monkeypatch.setattr(
        vc.loop,
        "create_task",
        lambda coro: scheduled.append(coro) or asyncio.sleep(0)
    )

    # Run play_next
    await ytj._play_next(vc)

    # After playback, queue should be empty and key removed
    assert 21 not in ytj.youtube_queue

    # Should have scheduled next (even though queue is empty)
    assert len(scheduled) == 1


@pytest.mark.asyncio
async def test_play_next_mixer_failure(dummy_logger, monkeypatch):
    vc = DummyVC(guild_id=22)
    ytj.youtube_queue[22] = ["badurl"]

    # Patch get_mixer to raise
    async def bad_mixer(_):
        raise RuntimeError("mixer bad")
    monkeypatch.setattr(discord_utils, "get_mixer_from_voice_client", bad_mixer)

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
    monkeypatch.setattr(discord_utils, "get_mixer_from_voice_client", lambda vc: asyncio.sleep(0, result=Mixer()))

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
    monkeypatch.setattr(
        discord_utils,
        "get_mixer_from_voice_client",
        lambda vc: asyncio.sleep(0, result=mixer)
    )

    await ytj.skip(vc)
    assert mixer.skipped


@pytest.mark.asyncio
async def test_skip_raises(monkeypatch, dummy_logger):
    vc = DummyVC(guild_id=41)

    class Mixer:
        def skip_current_tracks(self):
            raise RuntimeError("skip fail")
    mixer = Mixer()
    monkeypatch.setattr(discord_utils, "get_mixer_from_voice_client", lambda vc: asyncio.sleep(0, result=mixer))

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

    mixer = Mixer()
    monkeypatch.setattr(
        discord_utils,
        "get_mixer_from_voice_client",
        lambda vc: asyncio.sleep(0, result=mixer)
    )

    await ytj.stop(vc)
    assert mixer.stopped
    assert 60 not in ytj.youtube_queue


@pytest.mark.asyncio
async def test_stop_stop_raises(monkeypatch, dummy_logger):
    vc = DummyVC(guild_id=61)
    ytj.youtube_queue[61] = ["one"]

    class Mixer:
        def stop(self):
            raise RuntimeError("stop fail")
    mixer = Mixer()
    monkeypatch.setattr(discord_utils, "get_mixer_from_voice_client", lambda vc: asyncio.sleep(0, result=mixer))

    await ytj.stop(vc)
    # queue cleared despite stop exception
    assert 61 not in ytj.youtube_queue
    assert dummy_logger.exceptions, "Expected exception log on stop failure"
