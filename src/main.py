import logging  # noqa: I001, RUF100
import os
from typing import cast

import discord
from discord.ext import commands
from dotenv import load_dotenv

import audio_jobs

load_dotenv()

# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Bot permissions
intents = discord.Intents.default()
intents.voice_states = True

bot = commands.Bot(command_prefix="!", case_insensitive=True, intents=intents)

BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not BOT_TOKEN:
    err = "DISCORD_BOT_TOKEN environment variable is not set."
    raise ValueError(err)


@bot.event
async def on_ready() -> None:
    """Call when the bot is ready; synchronizes slash commands with Discord."""
    # Sync slash commands with Discord
    await bot.tree.sync()
    logger.info("Logged in as %s", bot.user)


@bot.tree.command(name="start", description="Start random SFX in your voice channel")
async def start(interaction: discord.Interaction) -> None:
    """Join the user's voice channel and start playing random sound effects."""
    # Ensure this is used in a guild
    if interaction.guild is None:
        await interaction.response.send_message(
            "This command only works in a server.", ephemeral=True
        )
        return

    # Get the member and their voice channel
    member = interaction.guild.get_member(interaction.user.id)
    if not member or not member.voice or not member.voice.channel:
        await interaction.response.send_message(
            "You need to be in a voice channel to start the loop.", ephemeral=True
        )
        return
    if not isinstance(member.voice.channel, discord.VoiceChannel):
        await interaction.response.send_message(
            "Stage channels are not supported by the SFX loop.", ephemeral=True
        )
        return

    # Connect to voice and start loop
    vc = await audio_jobs.ensure_connected(interaction.guild, member.voice.channel)
    try:
        await audio_jobs.start_loop(vc)
        await interaction.response.send_message(
            f"🎶 Started SFX loop in **{member.voice.channel.name}**.", ephemeral=True
        )
    except RuntimeError:
        await interaction.response.send_message(
            "SFX loop is already running in this server!", ephemeral=True
        )


@bot.tree.command(name="stop", description="Stop the random SFX loop")
async def stop(interaction: discord.Interaction) -> None:
    """Stop the random sound effect loop and disconnect from the voice channel."""
    if interaction.guild is None:
        await interaction.response.send_message(
            "This command only works in a server.", ephemeral=True
        )
        return

    try:
        await audio_jobs.stop_loop(interaction.guild)
        await interaction.response.send_message(
            "Stopped the SFX loop and left the channel.", ephemeral=True
        )
    except KeyError:
        await interaction.response.send_message(
            "No SFX loop is currently running here.", ephemeral=True
        )


@bot.tree.command(name="ping")
async def ping(interaction: discord.Interaction) -> None:
    """Check if the bot is alive."""
    await interaction.response.send_message("Pong!", ephemeral=True)


@bot.tree.command(name="trigger", description="Manually play a random sound effect")
async def trigger(interaction: discord.Interaction) -> None:
    """Play a random sound effect in the voice channel."""
    await interaction.response.defer(thinking=True)
    if interaction.guild is None:
        await interaction.followup.send(
            "This command can only be used in a server.", ephemeral=True
        )
        return

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
            return

    vc = cast("discord.VoiceClient", vc)
    sfx = await audio_jobs.trigger_sfx(vc)
    await interaction.followup.send(f"🔊 Playing **{sfx}**!", ephemeral=True)


# Run the bot
bot.run(BOT_TOKEN)
