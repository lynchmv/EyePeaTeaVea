import os
import redis
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

from .m3u_parser import M3UParser
from .redis_store import RedisStore
from .models import UserData

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

class Scheduler:
    def __init__(self):
        self.redis_store = RedisStore(REDIS_URL)
        self.scheduler = BackgroundScheduler()

    def _fetch_and_store_m3u(self, secret_str: str, user_data: UserData):
        all_channels_list = []
        for source in user_data.m3u_sources:
            m3u_parser = M3UParser(source)
            channels_list = m3u_parser.parse()
            all_channels_list.extend(channels_list)
        channels_dict = {channel["tvg_id"]: channel for channel in all_channels_list if channel.get("tvg_id")}
        self.redis_store.store_channels(channels_dict)

    def trigger_m3u_fetch_for_user(self, secret_str: str, user_data: UserData):
        self._fetch_and_store_m3u(secret_str, user_data)


    def start_scheduler(self):
        logger.info("Scheduler start_scheduler method called.")
        self.scheduler.remove_all_jobs()
        secret_strs = self.redis_store.get_all_secret_strs()
        logger.info(f"Found {len(secret_strs)} secret_strs for scheduling: {secret_strs}")
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("Scheduler started.")
        
        if not secret_strs:
            logger.warning("No user configurations found. Scheduler will not start any jobs.")
            return

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
