# type: ignore
import pytest
import asyncio
import random
import uuid

from src.audio_jobs import (
    loop_jobs,
    add_job,
    remove_job,
    _play_sfx_loop,
)
from src import utils


@pytest.fixture(autouse=True)
def clear_jobs(monkeypatch):
    # Clear loop_jobs before each test
    loop_jobs.clear()
    yield
    loop_jobs.clear()

class DummyGuild:
    def __init__(self, id, vc=None):
        self.id = id
        self.voice_client = vc

class DummyVC:
    def __init__(self, guild_id, connected=True):
        self.guild = DummyGuild(guild_id)
        self._connected = connected
        self.disconnect_called = False
        self.loop = asyncio.get_event_loop()

    def is_connected(self):
        return self._connected

    async def disconnect(self, force=False):
        self.disconnect_called = True
        self._connected = False

    async def connect(self):
        self._connected = True
        return self

class DummyChannel:
    def __init__(self, vc):
        self._vc = vc

    async def connect(self, cls=DummyVC):
        return self._vc

@pytest.mark.asyncio
async def test_add_and_remove_job_disconnect(monkeypatch):
    # Setup dummy voice client
    vc = DummyVC(guild_id=1, connected=True)

    # add_job
    job_id = await add_job(vc, sound="sfx.wav", min_interval=0.1, max_interval=0.2)
    assert job_id in loop_jobs
    stored_vc, task, sound, mi, ma = loop_jobs[job_id]
    assert stored_vc is vc
    assert sound == "sfx.wav"
    assert mi == 0.1
    assert ma == 0.2

    # simulate no other jobs, remove
    await remove_job(job_id)
    assert job_id not in loop_jobs

@pytest.mark.asyncio
async def test_remove_job_not_found():
    with pytest.raises(KeyError):
        await remove_job("nonexistent")

@pytest.mark.asyncio
async def test_ensure_connected_existing(monkeypatch):
    # Case 1: existing connected vc
    vc = DummyVC(guild_id=2, connected=True)
    guild = DummyGuild(id=2, vc=vc)
    channel = DummyChannel(vc)
    out = await utils.ensure_connected(guild, channel)
    assert out is vc

    # Case 2: no vc
    guild2 = DummyGuild(id=3, vc=None)
    new_vc = DummyVC(guild_id=3, connected=False)
    channel2 = DummyChannel(new_vc)
    out2 = await utils.ensure_connected(guild2, channel2)
    assert out2 is new_vc

@pytest.mark.asyncio
async def test_play_sfx_loop_client_not_connected(monkeypatch):
    # Setup dummy VC that's not connected
    vc = DummyVC(guild_id=4, connected=False)
    job_id = uuid.uuid4().hex

    # Insert a real dummy task so remove_job can cancel it cleanly
    dummy_task = asyncio.get_event_loop().create_task(asyncio.sleep(0))
    loop_jobs[job_id] = (vc, dummy_task, "sound.wav", 0.0, 0.0)

    # Run loop
    # Should remove job due to not connected
    await _play_sfx_loop(vc, job_id)
    assert job_id not in loop_jobs

@pytest.mark.asyncio
async def test_play_sfx_loop_play_error(monkeypatch):
    # Setup dummy VC always connected
    vc = DummyVC(guild_id=5, connected=True)
    job_id = uuid.uuid4().hex

    # Insert a real dummy task
    dummy_task = asyncio.get_event_loop().create_task(asyncio.sleep(0))
    loop_jobs[job_id] = (vc, dummy_task, "sound.wav", 0.0, 0.0)

    # Patch random.uniform to zero wait
    monkeypatch.setattr(random, 'uniform', lambda a, b: 0.0)

    # Patch asyncio.sleep to no-op
    orig_sleep = asyncio.sleep
    monkeypatch.setattr(asyncio, 'sleep', lambda x, _orig=orig_sleep: _orig(0))

    # Patch utils.get_mixer_from_voice_client to throw
    async def fake_get_mixer(vc_in):
        raise RuntimeError("fail")
    monkeypatch.setattr(utils, 'get_mixer_from_voice_client', fake_get_mixer)

    await _play_sfx_loop(vc, job_id)

    # Should remove job due to error
    assert job_id not in loop_jobs

@pytest.mark.asyncio
async def test_play_sfx_loop_success_one_iteration(monkeypatch):
    # Setup dummy VC always connected
    vc = DummyVC(guild_id=6, connected=True)
    job_id = uuid.uuid4().hex

    # Create simple mixer that plays immediately
    class DummyMixer:
        def __init__(self):
            self.played = []
        def play_file(self, sound, after_play=None):
            # simulate immediate playback
            if after_play:
                after_play()
    dummy_mixer = DummyMixer()

    # Insert a real dummy task so remove_job can cancel it
    dummy_task = asyncio.get_event_loop().create_task(asyncio.sleep(0))
    loop_jobs[job_id] = (vc, dummy_task, "sound.wav", 0.0, 0.0)

    # Patch random.uniform and sleep
    monkeypatch.setattr(random, 'uniform', lambda a, b: 0.0)
    orig_sleep = asyncio.sleep
    monkeypatch.setattr(asyncio, 'sleep', lambda x, _orig=orig_sleep: _orig(0))

    # Patch utils.get_mixer_from_voice_client
    async def fake_get_mixer(vc_in):
        return dummy_mixer
    monkeypatch.setattr(utils, 'get_mixer_from_voice_client', fake_get_mixer)

    # To exit after one iteration, remove job within after_play
    original_after = dummy_mixer.play_file
    def wrapped_play_file(sound, after_play=None):
        # call original then schedule removal
        original_after(sound, after_play)
        # remove job to break loop
        asyncio.get_event_loop().create_task(remove_job(job_id))
    dummy_mixer.play_file = wrapped_play_file

    # Run loop
    task = asyncio.create_task(_play_sfx_loop(vc, job_id))
    await asyncio.wait_for(task, timeout=1)
    assert job_id not in loop_jobs
