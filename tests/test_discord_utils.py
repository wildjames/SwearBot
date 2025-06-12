# type: ignore
import pytest

from balaambot import discord_utils
from balaambot.discord_utils import (
    get_mixer_from_interaction,
    get_mixer_from_voice_client,
)

# --- Dummy classes to simulate discord.py objects ---


class DummyVoiceClient:
    pass


class DummyMixer:
    pass


class DummyChannel:
    def __init__(self, vc):
        self._vc = vc

    async def connect(self, cls=DummyVoiceClient):
        return self._vc


class DummyVoice:
    def __init__(self, channel=None):
        self.channel = channel


class DummyMember:
    def __init__(self, user_id, voice=None):
        self.id = user_id
        self.voice = voice  # may be None or DummyVoice


class DummyGuild:
    def __init__(self, voice_client=None, members=None):
        self.voice_client = voice_client
        # members: dict mapping user_id -> DummyMember
        self._members = members or {}

    def get_member(self, user_id):
        return self._members.get(user_id)


class DummyFollowup:
    def __init__(self):
        self.sent = []

    async def send(self, message, ephemeral=False):
        # record (message, ephemeral) so tests can assert
        self.sent.append((message, ephemeral))


class DummyUser:
    def __init__(self, user_id):
        self.id = user_id


class DummyInteraction:
    def __init__(self, guild, user):
        self.guild = guild
        self.user = user
        self.followup = DummyFollowup()


# --- Tests for get_mixer_from_interaction ---


@pytest.mark.asyncio
async def test_get_mixer_from_interaction_no_guild():
    interaction = DummyInteraction(guild=None, user=DummyUser(1))
    with pytest.raises(ValueError) as exc:
        await get_mixer_from_interaction(interaction)
    assert str(exc.value) == "This command only works in a server."


@pytest.mark.asyncio
async def test_get_mixer_from_interaction_user_not_in_voice_channel():
    # guild.voice_client = None, member exists but has no voice/channel
    member = DummyMember(user_id=1, voice=None)
    guild = DummyGuild(voice_client=None, members={1: member})
    interaction = DummyInteraction(guild, DummyUser(1))

    with pytest.raises(ValueError) as exc:
        await get_mixer_from_interaction(interaction)

    # should have sent an ephemeral warning
    assert interaction.followup.sent == [
        (
            "You need to be in a voice channel (or have me already in one) to trigger a sound.",
            True,
        )
    ]
    assert str(exc.value) == "You need to be in a voice channel to trigger a sound."


@pytest.mark.asyncio
async def test_get_mixer_from_interaction_connects_and_returns_mixer(monkeypatch):
    # Setup: no VC on guild, but member is in a channel
    vc = DummyVoiceClient()
    channel = DummyChannel(vc)
    voice = DummyVoice(channel=channel)
    member = DummyMember(user_id=1, voice=voice)
    guild = DummyGuild(voice_client=None, members={1: member})
    interaction = DummyInteraction(guild, DummyUser(1))

    # Monkey‐patch ensure_mixer to return our DummyMixer
    dummy_mixer = DummyMixer()

    async def fake_ensure(vcin):
        return dummy_mixer

    monkeypatch.setattr(discord_utils, "ensure_mixer", fake_ensure)

    result = await get_mixer_from_interaction(interaction)
    assert result is dummy_mixer


@pytest.mark.asyncio
async def test_get_mixer_from_interaction_failed_ensure_sends_and_raises(monkeypatch):
    # Setup: guild already has a VC, but ensure_mixer returns None
    vc = DummyVoiceClient()
    guild = DummyGuild(voice_client=vc, members={})
    interaction = DummyInteraction(guild, DummyUser(2))

    async def fake_ensure(vcin):
        return None

    monkeypatch.setattr(discord_utils, "ensure_mixer", fake_ensure)

    with pytest.raises(ValueError) as exc:
        await get_mixer_from_interaction(interaction)

    assert interaction.followup.sent == [
        ("Failed to connect to the voice channel.", True)
    ]
    assert str(exc.value) == "Failed to connect to the voice channel."


# --- Tests for get_mixer_from_voice_client ---


@pytest.mark.asyncio
async def test_get_mixer_from_voice_client_failed_ensure(monkeypatch):
    vc = DummyVoiceClient()

    async def fake_ensure(vcin):
        return None

    monkeypatch.setattr(discord_utils, "ensure_mixer", fake_ensure)

    with pytest.raises(ValueError) as exc:
        await get_mixer_from_voice_client(vc)
    assert str(exc.value) == "Failed to connect to the voice channel."


@pytest.mark.asyncio
async def test_get_mixer_from_voice_client_success(monkeypatch):
    vc = DummyVoiceClient()
    dummy_mixer = DummyMixer()

    async def fake_ensure(vcin):
        return dummy_mixer

    monkeypatch.setattr(discord_utils, "ensure_mixer", fake_ensure)

    result = await get_mixer_from_voice_client(vc)
    assert result is dummy_mixer
