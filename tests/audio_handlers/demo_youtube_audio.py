import asyncio
import logging

from src.audio_handlers.youtube_audio import (
    fetch_audio_pcm,
    get_youtube_track_metadata,
    get_audio_pcm,
    remove_audio_pcm,
    get_playlist_video_urls,
    search_youtube,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


if __name__ == "__main__":
    test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    async def main() -> None:
        """Test the audio fetching and caching functionality."""
        logger.info("Testing audio fetching for URL: %s", test_url)
        # Fetch and cache audio
        t0 = asyncio.get_event_loop().time()
        cache_path = await fetch_audio_pcm(test_url)
        t1 = asyncio.get_event_loop().time()
        logger.info("Fetched audio cache at: %s", cache_path)
        logger.info("Fetch took %.2f seconds", t1 - t0)

        # Get track name
        t0 = asyncio.get_event_loop().time()
        track_metadata = await get_youtube_track_metadata(test_url)
        t1 = asyncio.get_event_loop().time()
        if track_metadata:
            logger.info("Track name: %s", track_metadata["title"])
            logger.info("Track runtime: %s seconds", track_metadata["runtime"])
            logger.info("Track name fetch took %.2f seconds", t1 - t0)
        else:
            logger.warning("Could not fetch track name for URL: %s", test_url)

        # Read raw PCM bytes
        t0 = asyncio.get_event_loop().time()
        pcm_data = get_audio_pcm(test_url)
        t1 = asyncio.get_event_loop().time()
        if pcm_data:
            logger.info("Loaded %s bytes of PCM data", len(pcm_data))
            logger.info("PCM data read took %.2f seconds", t1 - t0)

        await asyncio.sleep(5)

        # Remove cached file
        removed = remove_audio_pcm(test_url)
        logger.info("Cache removed: %s", removed)

        playlist_url = "https://www.youtube.com/watch?v=Z0Uh3OJCx3o&list=PLJDafirWnxGR5H0rSeJKgxC6rIj78JKce"
        logger.info("Fetching a playlist of URLs: %s", playlist_url)
        urls = await get_playlist_video_urls(playlist_url)
        logger.info("URLs:")
        for url in urls:
            logger.info(" - %s", url)

        # search for a video
        search = "aphex twin"
        logger.info("Fetching search results for query '%s'", search)
        results = await search_youtube(search)
        logger.info("Results:")
        for result in results:
            logger.info(" - %s", result)

    asyncio.run(main())
