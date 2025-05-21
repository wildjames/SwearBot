import asyncio
import logging
import os
import random
from typing import Any, cast

import anyio
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
)

# Bot permissions
intents = discord.Intents.default()
intents.voice_states = True

bot = commands.Bot(command_prefix="!", case_insensitive=True, intents=intents)

# Configuration
SOUND_FILES = [
    "sounds/mlg/Damn Son Where_d You Find This - MLG Sound Effect (HD) ( 160kbps ).mp3",
    "sounds/mlg/OH BABY A TRIPLE - MLG Sound Effects (HD) ( 160kbps ).mp3",
]

MIN_INTERVAL = 30
MAX_INTERVAL = 120

BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not BOT_TOKEN:
    err = "DISCORD_BOT_TOKEN environment variable not set."
    raise ValueError(err)


@bot.event
async def on_ready() -> None:
    """Call when the bot is ready; synchronizes slash commands with Discord."""
    # Sync slash commands with Discord
    await bot.tree.sync()
    logger.debug("Logged in as %s", bot.user)


@bot.command(name="join")
async def join(ctx: commands.Context[Any]) -> None:
    """Join the user's voice channel if available."""
    if isinstance(ctx.author, discord.Member) and ctx.author.voice:
        channel = ctx.author.voice.channel
        if channel is None:
            await ctx.send("You need to be in a voice channel first.")
            return
        if not hasattr(channel, "connect"):
            await ctx.send("Unable to join this voice channel.")
            return
        vc = await channel.connect()
        bot.loop.create_task(play_sfx_loop(vc))
        await ctx.send(f"Joined {channel.name} and started random SFX loop!")
    else:
        await ctx.send("You need to be in a voice channel first.")


@bot.command(name="leave")
async def leave(ctx: commands.Context[Any]) -> None:
    """Leave the voice channel if connected."""
    if ctx.voice_client:
        await ctx.voice_client.disconnect(force=True)
        await ctx.send("Left the voice channel.")
    else:
        await ctx.send("I'm not in a voice channel.")


async def play_sfx_loop(vc: discord.VoiceClient) -> None:
    """Play random sound effects in a loop."""
    if not vc.is_connected():
        logger.warning("Voice client is not connected.")
        return

    while True:
        wait = random.uniform(MIN_INTERVAL, MAX_INTERVAL)  # noqa: S311
        await asyncio.sleep(wait)

        sfx = random.choice(SOUND_FILES)  # noqa: S311

        # create an event to signal when playback is done
        done_event = anyio.Event()

        def _after_play(
            error: Exception | None,
            sfx: str = sfx,
            done_event: anyio.Event = done_event,
        ) -> None:
            """Callback function to be called after playback."""
            if error:
                logger.error("Error playing %s: %s", sfx, error)
            done_event.set()

        vc.play(discord.FFmpegPCMAudio(sfx), after=_after_play)

        # wait for the track to finish
        await done_event.wait()


@bot.tree.command(name="trigger", description="Manually play a random sound effect")
async def trigger(interaction: discord.Interaction) -> None:
    """Trigger a random sound effect in the voice channel."""
    # Defer the response (so the user sees it's processing)
    await interaction.response.defer(thinking=True)

    # Check if already connected
    if interaction.guild is None:
        await interaction.followup.send(
            "This command can only be used in a server.",
            ephemeral=True,
        )
        return

    vc = interaction.guild.voice_client
    if not vc:
        # Try to connect to the user's channel using the member attribute from the guild
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

    # Play the SFX
    sfx = random.choice(SOUND_FILES)  # noqa: S311
    voice_client = cast("discord.VoiceClient", vc)
    voice_client.play(
        discord.FFmpegPCMAudio(sfx),
        after=lambda e: logger.info("Finished %s: %s", sfx, e),
    )

    # Let the user know
    await interaction.followup.send(f"🔊 Playing **{sfx}**!", ephemeral=True)


# Run the bot
bot.run(BOT_TOKEN)
