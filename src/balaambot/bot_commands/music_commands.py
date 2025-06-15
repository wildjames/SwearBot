import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

import discord
from discord import Client, InteractionCallbackResponse, app_commands
from discord.ext import commands
from discord.ui import Button, View

from balaambot import discord_utils, utils
from balaambot.audio_handlers import youtube_audio, youtube_utils
from balaambot.config import DiscordVoiceClient
from balaambot.schedulers import youtube_jobs

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


class SearchView(View):
    """A view containing buttons for selecting search results."""

    def __init__(
        self,
        parent: "MusicCommands",
        vc: DiscordVoiceClient,
        results_list: list[tuple[str, str, float]],
    ) -> None:
        """Set up the internal structures."""
        super().__init__(timeout=None)  # no timeout so buttons remain valid
        self.results = results_list
        self.parent = parent
        self.vc = vc
        # # Add a timeout so this doesn't hang forever
        # self.timeout = 60
        # self.on_timeout =
        # async def on_timeout(inner_interaction: discord.Interaction) ->

        for idx, (url, title, _) in enumerate(self.results):
            button = Button(  # type: ignore  This type error is daft and I hate it so fuck that
                label=f"{idx + 1}",
                style=discord.ButtonStyle.primary,
                custom_id=f"search_select_{idx}",
            )

            # Bind a callback that knows which index was clicked
            button.callback = self.make_callback(idx, url, title)  # type: ignore The button is well defined
            self.add_item(button)  # type: ignore The button is well defined

    def make_callback(
        self, idx: int, url: str, title: str
    ) -> Callable[
        [discord.Interaction], Awaitable[InteractionCallbackResponse[Client] | None]
    ]:
        """Handle the clicking of the buttons."""

        async def callback(
            inner_interaction: discord.Interaction,
        ) -> InteractionCallbackResponse[Client] | None:
            # Log which result the user picked
            logger.info(
                'User %s selected search result #%d: %s ("%s")',
                inner_interaction.user.name,
                idx + 1,
                url,
                title,
            )

            await inner_interaction.response.edit_message(
                content=f"Playing {title}", view=None, delete_after=5
            )
            await self.parent.do_play(inner_interaction, self.vc, url)

        return callback


class MusicCommands(commands.Cog):
    """Slash commands for YouTube queue and playback."""

    def __init__(self, bot: commands.Bot) -> None:
        """Initialize the MusicCommands cog."""
        self.bot = bot

    @app_commands.command(
        name="play", description="Enqueue and play a YouTube video audio"
    )
    @app_commands.describe(query="YouTube video URL, playlist URL, or search term")
    async def play(self, interaction: discord.Interaction, query: str) -> None:
        """Enqueue a YouTube URL; starts playback if idle."""
        await interaction.response.defer(thinking=True, ephemeral=True)
        # Check if the user is in a voice channel
        vc = await discord_utils.get_voice_channel(interaction)
        if vc is None:
            return

        query = query.strip()

        # Handle playlist URLs
        if youtube_utils.is_valid_youtube_playlist(query):
            logger.info("Received play command for playlist URL: '%s'", query)
            self.bot.loop.create_task(self.do_play_playlist(interaction, vc, query))
            return

        # Handle youtube videos
        if youtube_utils.is_valid_youtube_url(query):
            logger.info("Received play command for URL: '%s'", query)
            self.bot.loop.create_task(self.do_play(interaction, vc, query))
            return

        # Fall back to searching youtube and asking the user to select a search result
        if query:
            logger.info("Recieved a string. Searching youtube for videos. '%s'", query)
            self.bot.loop.create_task(self.do_search_youtube(interaction, vc, query))
            return

        # Failed to do anything. I think this is only reached if the query is empty?
        await interaction.followup.send(
            content=(
                "Invalid play command. Please provide a valid youtube video "
                "or playlist link, or a searchable string."
            ),
        )
        return

    async def do_search_youtube(
        self, interaction: discord.Interaction, vc: DiscordVoiceClient, query: str
    ) -> None:
        """Search for videos based on the query and display selection buttons."""
        results = await youtube_audio.search_youtube(query)
        # Each result is a tuple: (url, title, duration_in_seconds)

        if not results:
            await interaction.followup.send(
                "No results found for your query.", ephemeral=True
            )
            return

        # Build a text block describing each result line by line
        lines: list[str] = []
        for idx, (_, title, duration_secs) in enumerate(results):
            duration_str = utils.sec_to_string(duration_secs)
            lines.append(f"**{idx + 1}.** {title} ({duration_str})")

        description = (
            "Select a track by clicking the corresponding button:\n\n"
            + "\n".join(lines)
        )

        # Send the reply with the View
        await interaction.followup.send(
            content=description,
            view=SearchView(self, vc, results),
            ephemeral=True,
        )

    async def do_play_playlist(
        self,
        interaction: discord.Interaction,
        vc: DiscordVoiceClient,
        playlist_url: str,
    ) -> None:
        """Handle enqueuing all videos from a YouTube playlist."""
        mixer = await discord_utils.get_mixer_from_voice_client(vc)

        # Fetch playlist video URLs
        track_urls = await youtube_audio.get_playlist_video_urls(playlist_url)
        if not track_urls:
            return await interaction.followup.send(
                "Failed to fetch playlist or playlist is empty.", ephemeral=True
            )

        # Enqueue all tracks and start background fetches
        fetch_tasks: list[asyncio.Task[Path]] = []
        for track_url in track_urls:
            fetch_task = asyncio.create_task(
                youtube_audio.fetch_audio_pcm(
                    track_url,
                    sample_rate=mixer.SAMPLE_RATE,
                    channels=mixer.CHANNELS,
                )
            )
            fetch_tasks.append(fetch_task)
            await youtube_jobs.add_to_queue(
                vc, track_url, text_channel=interaction.channel_id
            )

        # Confirmation message
        await interaction.followup.send(
            f"🎵    Queued {len(track_urls)} tracks from playlist.", ephemeral=False
        )

        # And wait for the first video to download
        await fetch_tasks[0]
        return None

    async def do_play(
        self, interaction: discord.Interaction, vc: DiscordVoiceClient, url: str
    ) -> None:
        """Play a YouTube video by fetching and streaming the audio from the URL."""
        mixer = await discord_utils.get_mixer_from_voice_client(vc)

        # download and cache in background
        fetch_task = asyncio.create_task(
            youtube_audio.fetch_audio_pcm(
                url,
                sample_rate=mixer.SAMPLE_RATE,
                channels=mixer.CHANNELS,
            )
        )

        # Add to queue. Playback (in mixer) will await cache when it's time
        await youtube_jobs.add_to_queue(vc, url, text_channel=interaction.channel_id)

        track_meta = await youtube_audio.get_youtube_track_metadata(url)
        if track_meta is None:
            await interaction.followup.send(
                f"Failed to fetch track metadata. Please check the URL. [{url}]",
                ephemeral=True,
            )
            return

        queue = await youtube_jobs.list_queue(vc)
        pos = len(queue)

        runtime = track_meta["runtime_str"]

        msg = (
            f"🎵    Queued **[{track_meta['title']}]({track_meta['url']})"
            f" ({runtime})** at position {pos}."
        )
        await interaction.followup.send(msg, ephemeral=False)

        # wait for the background fetch to complete (so file is ready later)
        try:
            await fetch_task
        except Exception:
            logger.exception("Failed to fetch audio for %s", url)

    @app_commands.command(name="list_queue", description="List upcoming YouTube tracks")
    async def list_queue(self, interaction: discord.Interaction) -> None:
        """Show the current YouTube queue for this server."""
        await interaction.response.defer(ephemeral=True, thinking=True)
        # Check if the user is in a voice channel
        vc = await discord_utils.get_voice_channel(interaction)
        if vc is None:
            return
        upcoming = await youtube_jobs.list_queue(vc)

        if not upcoming:
            msg = "The queue is empty."
        else:
            lines: list[str] = []
            total_runtime = 0

            for i, url in enumerate(upcoming):
                track_meta = await youtube_audio.get_youtube_track_metadata(url)
                if track_meta is None:
                    lines.append(f"{i + 1}. [Invalid track URL]({url})")
                    continue
                lines.append(
                    f"{i + 1}. [{track_meta['title']}]({track_meta['url']})"
                    f" ({track_meta['runtime_str']})"
                )
                total_runtime += track_meta["runtime"]

            track_meta = await youtube_audio.get_youtube_track_metadata(upcoming[0])
            if track_meta is None:
                lines[0] = f"**Now playing:** [Invalid track URL]({upcoming[0]})"
            else:
                lines[0] = (
                    "**Now playing:** "
                    f"[{track_meta['title']}]({track_meta['url']})"
                    f" ({track_meta['runtime_str']})"
                )
            msg = "**Upcoming tracks:**\n" + "\n".join(lines)

            # format runtime as H:MM:SS or M:SS
            total_runtime_str = utils.sec_to_string(total_runtime)
            msg += f"\n\n🔮    Total runtime: {total_runtime_str}"

        await interaction.followup.send(msg, ephemeral=True)

    @app_commands.command(name="skip", description="Skip the current YouTube track")
    async def skip(self, interaction: discord.Interaction) -> None:
        """Stop current track and play next in queue."""
        await interaction.response.defer(ephemeral=True, thinking=True)
        # Check if the user is in a voice channel
        vc = await discord_utils.get_voice_channel(interaction)
        if vc is None:
            return

        await youtube_jobs.skip(vc)
        logger.info("Skipped track for guild_id=%s", vc.guild.id)

        track_url = youtube_jobs.get_current_track(vc)
        if not track_url:
            await interaction.followup.send(
                "No track is currently playing.", ephemeral=True
            )
            return

        track_meta = await youtube_audio.get_youtube_track_metadata(track_url)
        if track_meta is None:
            await interaction.followup.send(
                f"Failed to fetch track metadata. Please check the URL. [{track_url}]",
                ephemeral=True,
            )
            return
        await interaction.followup.send(
            f"⏭️    Skipped to next track: [{track_meta['title']}]({track_meta['url']})",
            ephemeral=False,
        )

    @app_commands.command(
        name="stop_music",
        description="Stop playback and clear YouTube queue",
    )
    async def stop_music(self, interaction: discord.Interaction) -> None:
        """Stop the current YouTube track and clear all queued tracks."""
        # Check if the user is in a voice channel
        vc = await discord_utils.get_voice_channel(interaction)
        if vc is None:
            return
        await youtube_jobs.stop(vc)
        await interaction.response.send_message(
            "⏹️    Stopped and cleared YouTube queue.", ephemeral=False
        )

    @app_commands.command(name="clear_queue", description="Clear the YouTube queue")
    async def clear_queue(self, interaction: discord.Interaction) -> None:
        """Remove all queued YouTube tracks."""
        # Check if the user is in a voice channel
        vc = await discord_utils.get_voice_channel(interaction)
        if vc is None:
            return
        logger.info("Clearing YouTube queue for guild_id=%s", vc.guild.id)

        # Clear the queue
        await youtube_jobs.clear_queue(vc)
        current_queue = await youtube_jobs.list_queue(vc)
        logger.info("queue after clearing: %s", current_queue)

        await interaction.response.send_message(
            "🗑️    Cleared the YouTube queue.", ephemeral=False
        )


#         @app_commands.command(
#             name="seek",
#             description=
# "Seek to a specific time in the current YouTube track
# (e.g., 1:23 or -30 to rewind 30s)",
#         )
#         @app_commands.describe(
#             position=
# "Time to seek to (e.g., 1:23 for 1m23s, 90 for 90s, -30 to rewind 30s)"
#         )
#         async def seek(self, interaction: discord.Interaction, position: str) -> None:
#             """Seek to a specific position in the current track."""
#             await interaction.response.defer(ephemeral=True, thinking=True)
#             vc = await discord_utils.get_voice_channel(interaction)
#             if vc is None:
#                 return

#             # Get current track and metadata
#             track_url = youtube_jobs.get_current_track(vc)
#             if not track_url:
#                 await interaction.followup.send(
#                     "No track is currently playing.", ephemeral=True
#                 )
#                 return

#             track_meta = await youtube_audio.get_youtube_track_metadata(track_url)
#             if not track_meta or "runtime" not in track_meta:
#                 await interaction.followup.send(
#                     "Could not fetch track metadata.", ephemeral=True
#                 )
#                 return

#             total_duration = track_meta["runtime"]

#             # Parse position argument
#             def parse_time_arg(arg: str) -> int | None:
#                 arg = arg.strip()
#                 if arg.startswith("-"):
#                     try:
#                         return -int(arg[1:])
#                     except ValueError:
#                         pass
#                 if ":" in arg:
#                     parts = arg.split(":")
#                     try:
#                         parts = [int(p) for p in parts]
#                         if len(parts) == 2:
#                             return parts[0] * 60 + parts[1]
#                         if len(parts) == 3:
#                             return parts[0] * 3600 + parts[1] * 60 + parts[2]
#                     except ValueError:
#                         return None
#                 try:
#                     return int(arg)
#                 except ValueError:
#                     return None

#             seek_seconds = parse_time_arg(position)
#             if seek_seconds is None:
#                 await interaction.followup.send(
#                     "Invalid time format.
# Use seconds, H:MM:SS, M:SS, or -N to rewind.",
#                     ephemeral=True,
#                 )
#                 return

#             # Get current playback position
#             current_pos = await youtube_jobs.get_current_position(vc)
#             if current_pos is None:
#                 current_pos = 0

#             if seek_seconds < 0:
#                 new_pos = max(0, current_pos + seek_seconds)
#             else:
#                 new_pos = seek_seconds

#             new_pos = min(new_pos, total_duration)
#             new_pos = max(new_pos, 0)

#             # Actually perform the seek
#             success = await youtube_jobs.seek(vc, new_pos)
#             if not success:
#                 await interaction.followup.send(
#                     "Failed to seek in the current track.", ephemeral=True
#                 )
#                 return

#             await interaction.followup.send(
#
# f"⏩    Seeked to {utils.sec_to_string(new_pos)} in **{track_meta['title']}**.",
#                 ephemeral=False,
#             )


async def setup(bot: commands.Bot) -> None:
    """Load the MusicCommands cog."""
    logger.info("Loading MusicCommands cog")
    await bot.add_cog(MusicCommands(bot))
