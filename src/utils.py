from typing import cast

import discord

from .multi_audio_source import MultiAudioSource, ensure_mixer


async def ensure_connected(
    guild: discord.Guild, channel: discord.VoiceChannel
) -> discord.VoiceClient:
    """Connect to voice or reuse existing connection."""
    vc = guild.voice_client
    if not vc or not isinstance(vc, discord.VoiceClient) or not vc.is_connected():
        vc = await channel.connect()
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
            vc = await member.voice.channel.connect()
        else:
            await interaction.followup.send(
                "You need to be in a voice channel (or have me already in one)"
                " to trigger a sound.",
                ephemeral=True,
            )
            msg = "You need to be in a voice channel to trigger a sound."
            raise ValueError(msg)

    vc = cast("discord.VoiceClient", vc)
    mixer = await ensure_mixer(vc)

    if not mixer:
        await interaction.followup.send(
            "Failed to connect to the voice channel.", ephemeral=True
        )
        msg = "Failed to connect to the voice channel."
        raise ValueError(msg)

    return mixer


async def get_mixer_from_voice_client(
    vc: discord.VoiceClient,
) -> MultiAudioSource:
    """Get the mixer for the given voice client."""
    if not vc:
        msg = "No active voice client."
        raise ValueError(msg)

    mixer = await ensure_mixer(vc)

    if not mixer:
        msg = "Failed to connect to the voice channel."
        raise ValueError(msg)

    return mixer
