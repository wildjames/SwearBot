from typing import cast

import discord

from balaambot.audio_handlers.multi_audio_source import MultiAudioSource, ensure_mixer
from balaambot.config import DISCORD_VOICE_CLIENT


async def ensure_connected(
    guild: discord.Guild, channel: discord.VoiceChannel
) -> DISCORD_VOICE_CLIENT:
    """Connect to voice or reuse existing connection."""
    vc = guild.voice_client

    if not vc or not isinstance(vc, DISCORD_VOICE_CLIENT) or not vc.is_connected():
        vc = await channel.connect(cls=DISCORD_VOICE_CLIENT)

    elif vc.channel != channel:
        # If the voice client is connected to a different channel,
        # disconnect and reconnect
        await vc.disconnect()
        vc = await channel.connect(cls=DISCORD_VOICE_CLIENT)

    return vc


async def get_mixer_from_interaction(
    interaction: discord.Interaction,
) -> MultiAudioSource:
    """Get the mixer for the current interaction's guild.

    If the mixer is not already connected, it will attempt to connect to the
    voice channel of the user who triggered the interaction.
    """
    if interaction.guild is None:
        msg = "This command only works in a server."
        raise ValueError(msg)

    vc = interaction.guild.voice_client
    if not vc:
        member = interaction.guild.get_member(interaction.user.id)
        if member and member.voice and member.voice.channel:
            vc = await member.voice.channel.connect(cls=DISCORD_VOICE_CLIENT)
        else:
            await interaction.followup.send(
                "You need to be in a voice channel (or have me already in one)"
                " to trigger a sound.",
                ephemeral=True,
            )
            msg = "You need to be in a voice channel to trigger a sound."
            raise ValueError(msg)

    vc = cast("DISCORD_VOICE_CLIENT", vc)
    mixer = await ensure_mixer(vc)

    if not mixer:
        await interaction.followup.send(
            "Failed to connect to the voice channel.", ephemeral=True
        )
        msg = "Failed to connect to the voice channel."
        raise ValueError(msg)

    return mixer


async def get_mixer_from_voice_client(
    vc: DISCORD_VOICE_CLIENT,
) -> MultiAudioSource:
    """Get the mixer for the given voice client."""
    mixer = await ensure_mixer(vc)

    if not mixer:
        msg = "Failed to connect to the voice channel."
        raise ValueError(msg)

    return mixer


async def get_voice_channel_mixer(
    interaction: discord.Interaction,
) -> tuple[DISCORD_VOICE_CLIENT, MultiAudioSource] | None:
    """Ensure the user is in a voice channel and returns the channel and mixer."""
    if interaction.guild is None:
        await interaction.followup.send(
            "This command can only be used in a server.", ephemeral=True
        )
        return None

    member = interaction.guild.get_member(interaction.user.id)
    if (
        not member
        or not member.voice
        or not isinstance(member.voice.channel, discord.VoiceChannel)
    ):
        await interaction.followup.send("Join a voice channel first.", ephemeral=True)
        return None

    vc = await ensure_connected(
        interaction.guild,
        member.voice.channel,
    )

    mixer = await get_mixer_from_voice_client(vc)
    return vc, mixer
