import os
import redis
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv

from m3u_parser import M3UParser
from epg_parser import EPGParser
from redis_store import RedisStore

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
COMBINED_PLAYLIST_SOURCES = os.getenv("COMBINED_PLAYLIST_SOURCES", "").split(",")
COMBINED_EPG_SOURCES = os.getenv("COMBINED_EPG_SOURCES", "").split(",")

class Scheduler:
    def __init__(self):
        self.redis_store = RedisStore(REDIS_URL)
        self.scheduler = BackgroundScheduler()

    def _fetch_and_store_m3u(self):
        logger.info("Fetching and parsing M3U data...")
        all_channels = []
        for source in COMBINED_PLAYLIST_SOURCES:
            if source:
                parser = M3UParser(source)
                channels = parser.parse()
                all_channels.extend(channels)
        if all_channels:
            self.redis_store.store_channels(all_channels)
            logger.info(f"Stored {len(all_channels)} channels.")
        else:
            logger.info("No M3U data to store.")

    def _fetch_and_store_epg(self):
        logger.info("Fetching and parsing EPG data...")
        all_programs = []
        for source in COMBINED_EPG_SOURCES:
            if source:
                parser = EPGParser(source)
                programs = parser.parse()
                all_programs.extend(programs)
        if all_programs:
            # Group programs by channel for efficient storage
            programs_by_channel = {}
            for program in all_programs:
                channel_id = program.get("channel")
                if channel_id:
                    if channel_id not in programs_by_channel:
                        programs_by_channel[channel_id] = []
                    programs_by_channel[channel_id].append(program)
            
            for channel_id, programs in programs_by_channel.items():
                self.redis_store.store_programs(channel_id, programs)
            logger.info(f"Stored EPG data for {len(programs_by_channel)} channels.")
        else:
            logger.info("No EPG data to store.")

    def start_scheduler(self):
        # Schedule M3U parsing (e.g., every 6 hours)
        self.scheduler.add_job(self._fetch_and_store_m3u, 'interval', hours=6)
        # Schedule EPG parsing (e.g., every 1 hour)
        self.scheduler.add_job(self._fetch_and_store_epg, 'interval', hours=1)
        
        self.scheduler.start()
        logger.info("Scheduler started.")

    def stop_scheduler(self):
        self.scheduler.shutdown()
        logger.info("Scheduler stopped.")

if __name__ == "__main__":
    scheduler = Scheduler()
    scheduler.start_scheduler()
    try:
        # Keep the main thread alive
        while True:
            pass
    except (KeyboardInterrupt, SystemExit):
        scheduler.stop_scheduler()
