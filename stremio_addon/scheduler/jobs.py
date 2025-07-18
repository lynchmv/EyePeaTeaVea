import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from stremio_addon.core.config import settings
from stremio_addon.parser.playlist_parser import CombinedPlaylistParser
from stremio_addon.db import crud # We will create this file next

async def run_parser_job():
    """
    This is the main job function that the scheduler will call.
    It instantiates the parser and runs it.
    """
    logging.info("Scheduler is starting the combined playlist parser job...")
    try:
        if not settings.combined_playlist_sources:
            logging.warning("COMBINED_PLAYLIST_SOURCES is not set. Skipping parser job.")
            return

        source_urls = [url.strip() for url in settings.combined_playlist_sources.split(',')]

        parser = CombinedPlaylistParser(source_urls=source_urls)
        parsed_data = await parser.parse()

        # Process and save the regular channels
        if parsed_data.get("channels"):
            logging.info(f"Saving {len(parsed_data['channels'])} TV channels to the database.")
            await crud.save_tv_channels(parsed_data["channels"])

        # Process and save the live events
        if parsed_data.get("events"):
            logging.info(f"Saving {len(parsed_data['events'])} live events to the database.")
            await crud.save_live_events(parsed_data["events"])

        logging.info("Combined playlist parser job finished successfully.")

    except Exception as e:
        logging.exception(f"An error occurred during the parser job: {e}")

def setup_scheduler(scheduler: AsyncIOScheduler):
    """
    Adds the parser job to the scheduler instance.
    """
    scheduler.add_job(
        run_parser_job,
        CronTrigger.from_crontab(settings.parser_schedule_crontab),
        name="combined_playlist_parser",
    )

