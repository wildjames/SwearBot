# type: ignore
import pytest

from balaambot import discord_utils
from balaambot.discord_utils import (
    ensure_connected,
    get_mixer_from_interaction,
    get_mixer_from_voice_client,
    get_voice_channel_mixer,
    require_guild,
    require_voice_channel,
)

# --- Dummy classes to simulate discord.py objects ---


class DummyVoiceClient:
    def __init__(self, channel=None):
        self.channel = channel
        self._disconnected = False

    def is_connected(self):
        return not self._disconnected

    async def disconnect(self):
        self._disconnected = True


class DummyMixer:
    pass


class DummyChannel:
    def __init__(self, vc):
        self._vc = vc

    async def connect(self, cls=None):
        # ignore cls, just return dummy vc
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


class DummyResponse:
    def __init__(self):
        self.sent: list[tuple[str, bool]] = []
        self._done = False

    async def send_message(self, message, ephemeral=False):
        self.sent.append((message, ephemeral))
        self._done = True

    async def defer(self, thinking=False, ephemeral=False):
        self._done = True

    def is_done(self):
        return self._done


class DummyUser:
    def __init__(self, user_id):
        self.id = user_id


class DummyInteraction:
    def __init__(self, guild, user):
        self.guild = guild
        self.user = user
        self.followup = DummyFollowup()
        self.response = DummyResponse()


# ---------------------------------------------------------------------------
# Tests for ensure_connected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ensure_connected_no_existing_vc(monkeypatch):
    # guild.voice_client = None, so should call channel.connect
    vc = DummyVoiceClient()
    channel = DummyChannel(vc)
    guild = DummyGuild(voice_client=None)

    # monkey‐patch DISCORD_VOICE_CLIENT to accept DummyVoiceClient
    monkeypatch.setattr(discord_utils, "DISCORD_VOICE_CLIENT", DummyVoiceClient)

    returned = await ensure_connected(guild, channel)
    assert returned is vc


@pytest.mark.asyncio
async def test_ensure_connected_wrong_type_reconnects(monkeypatch):
    # guild.voice_client exists but not instance of DISCORD_VOICE_CLIENT, so reconnect
    wrong_vc = object()
    new_vc = DummyVoiceClient()
    channel = DummyChannel(new_vc)
    guild = DummyGuild(voice_client=wrong_vc)

    monkeypatch.setattr(discord_utils, "DISCORD_VOICE_CLIENT", DummyVoiceClient)

    returned = await ensure_connected(guild, channel)
    assert returned is new_vc


@pytest.mark.asyncio
async def test_ensure_connected_already_connected_same_channel(monkeypatch):
    # guild.voice_client is correct type, connected, and on same channel, so reuse
    vc = DummyVoiceClient(channel="chan1")
    # is_connected returns True by default
    guild = DummyGuild(voice_client=vc)
    channel = type("C", (), {"connect": None})()  # dummy, won't be called

    monkeypatch.setattr(discord_utils, "DISCORD_VOICE_CLIENT", DummyVoiceClient)
    # override channel just to compare by identity
    vc.channel = channel

    returned = await ensure_connected(guild, channel)
    assert returned is vc


@pytest.mark.asyncio
async def test_ensure_connected_connected_diff_channel(monkeypatch):
    # guild.voice_client is correct type and connected, but on a different channel, so disconnect & reconnect
    old_vc = DummyVoiceClient(channel="old")
    old_vc._disconnected = False
    new_vc = DummyVoiceClient(channel="new")
    channel = DummyChannel(new_vc)
    guild = DummyGuild(voice_client=old_vc)

    monkeypatch.setattr(discord_utils, "DISCORD_VOICE_CLIENT", DummyVoiceClient)

    returned = await ensure_connected(guild, channel)
    # old_vc should have been disconnected
    assert old_vc._disconnected is True
    assert returned is new_vc


# ---------------------------------------------------------------------------
# Existing tests for get_mixer_from_interaction
# ---------------------------------------------------------------------------


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

    def fake_ensure(vcin):
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

    def fake_ensure(vcin):
        return None

    monkeypatch.setattr(discord_utils, "ensure_mixer", fake_ensure)

    with pytest.raises(ValueError) as exc:
        await get_mixer_from_interaction(interaction)

    assert interaction.followup.sent == [
        ("Failed to connect to the voice channel.", True)
    ]
    assert str(exc.value) == "Failed to connect to the voice channel."


# ---------------------------------------------------------------------------
# Tests for get_mixer_from_voice_client
# ---------------------------------------------------------------------------


def test_get_mixer_from_voice_client_failed_ensure(monkeypatch):
    vc = DummyVoiceClient()

    def fake_ensure(vcin):
        return None

    monkeypatch.setattr(discord_utils, "ensure_mixer", fake_ensure)

    with pytest.raises(ValueError) as exc:
        get_mixer_from_voice_client(vc)
    assert str(exc.value) == "Failed to connect to the voice channel."


def test_get_mixer_from_voice_client_success(monkeypatch):
    vc = DummyVoiceClient()
    dummy_mixer = DummyMixer()

    def fake_ensure(vcin):
        return dummy_mixer

    monkeypatch.setattr(discord_utils, "ensure_mixer", fake_ensure)

    result = get_mixer_from_voice_client(vc)
    assert result is dummy_mixer


# ---------------------------------------------------------------------------
# Tests for get_voice_channel_mixer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_voice_channel_mixer_no_guild():
    interaction = DummyInteraction(guild=None, user=DummyUser(1))
    result = await get_voice_channel_mixer(interaction)
    # Should send an ephemeral message and return None
    assert interaction.followup.sent == [
        ("This command can only be used in a server.", True)
    ]
    assert result is None


@pytest.mark.asyncio
async def test_get_voice_channel_mixer_user_not_in_channel():
    # Guild exists but member not in voice (voice=None)
    member = DummyMember(user_id=1, voice=None)
    guild = DummyGuild(voice_client=None, members={1: member})
    interaction = DummyInteraction(guild, DummyUser(1))

    result = await get_voice_channel_mixer(interaction)
    assert interaction.followup.sent == [("Join a voice channel first.", True)]
    assert result is None


@pytest.mark.asyncio
async def test_get_voice_channel_mixer_success(monkeypatch):
    # Member in channel, ensure_connected returns vc, get_mixer returns mixer
    vc = DummyVoiceClient()
    channel = DummyChannel(vc)
    member = DummyMember(user_id=1, voice=DummyVoice(channel=channel))
    guild = DummyGuild(voice_client=None, members={1: member})
    interaction = DummyInteraction(guild, DummyUser(1))

    dummy_mixer = DummyMixer()

    async def fake_ensure(g, ch):
        assert g is guild and ch is channel
        return vc

    def fake_get_mixer(vcin):
        assert vcin is vc
        return dummy_mixer

    monkeypatch.setattr(discord_utils, "ensure_connected", fake_ensure)
    monkeypatch.setattr(discord_utils, "get_mixer_from_voice_client", fake_get_mixer)
    monkeypatch.setattr(
        discord_utils.discord, "VoiceChannel", DummyChannel, raising=False
    )

    result = await get_voice_channel_mixer(interaction)
    assert result == (vc, dummy_mixer)


# ---------------------------------------------------------------------------
# Tests for require_guild and require_voice_channel
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_require_guild_none():
    interaction = DummyInteraction(guild=None, user=DummyUser(1))
    result = await require_guild(interaction)
    # Should send ephemeral message
    assert interaction.response.sent == [("This command only works in a server.", True)]
    assert result is None


@pytest.mark.asyncio
async def test_require_guild_returns_guild():
    guild = DummyGuild()
    interaction = DummyInteraction(guild, DummyUser(1))
    result = await require_guild(interaction)
    assert result is guild


@pytest.mark.asyncio
async def test_require_voice_channel_no_member():
    guild = DummyGuild(members={})
    interaction = DummyInteraction(guild, DummyUser(1))
    result = await require_voice_channel(interaction)
    assert interaction.response.sent == [
        ("You need to be in a standard voice channel to use this command.", True)
    ]
    assert result is None


@pytest.mark.asyncio
async def test_require_voice_channel_success(monkeypatch):
    vc = DummyVoiceClient()
    channel = DummyChannel(vc)
    member = DummyMember(user_id=1, voice=DummyVoice(channel=channel))
    guild = DummyGuild(members={1: member})
    interaction = DummyInteraction(guild, DummyUser(1))

    monkeypatch.setattr(
        discord_utils.discord, "VoiceChannel", DummyChannel, raising=False
    )

    result = await require_voice_channel(interaction)
    assert result == (channel, member)
