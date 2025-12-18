import os
import redis
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

from .m3u_parser import M3UParser
from .redis_store import RedisStore
from .models import UserData
from .utils import validate_cron_expression

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

class Scheduler:
    def __init__(self):
        self.redis_store = RedisStore(REDIS_URL)
        self.scheduler = BackgroundScheduler()

    def _fetch_and_store_m3u(self, secret_str: str, user_data: UserData):
        """Fetches M3U playlists from all sources and stores channels in Redis."""
        logger.info(f"Starting scheduled M3U fetch for secret_str: {secret_str}")
        all_channels_list = []
        errors = []
        
        for source in user_data.m3u_sources:
            try:
                m3u_parser = M3UParser(source)
                channels_list = m3u_parser.parse()
                all_channels_list.extend(channels_list)
                logger.info(f"Successfully parsed {len(channels_list)} channels from {source}")
            except Exception as e:
                error_msg = f"Error parsing M3U source {source}: {e}"
                logger.error(error_msg)
                errors.append(error_msg)
                # Continue with other sources even if one fails
        
        if all_channels_list:
            self.redis_store.store_channels(secret_str, all_channels_list)
            logger.info(f"Stored {len(all_channels_list)} channels for secret_str: {secret_str}")
        else:
            logger.warning(f"No channels were parsed for secret_str: {secret_str}")
        
        if errors:
            logger.warning(f"Encountered {len(errors)} errors during M3U fetch for secret_str: {secret_str}")

    def _scheduled_fetch_wrapper(self, secret_str: str):
        """Wrapper function for scheduled jobs that retrieves user_data from Redis."""
        user_data = self.redis_store.get_user_data(secret_str)
        if not user_data:
            logger.error(f"User data not found for secret_str: {secret_str}. Skipping scheduled fetch.")
            return
        self._fetch_and_store_m3u(secret_str, user_data)

    def trigger_m3u_fetch_for_user(self, secret_str: str, user_data: UserData):
        """Immediately triggers an M3U fetch for a user (used during configuration)."""
        self._fetch_and_store_m3u(secret_str, user_data)

    def _parse_cron_expression(self, cron_str: str) -> CronTrigger:
        """Parses a cron expression string into a CronTrigger object."""
        # Validate the cron expression first (raises ValueError if invalid)
        validated_cron = validate_cron_expression(cron_str)
        
        # Parse into CronTrigger
        # Cron format: "minute hour day month day-of-week"
        # Example: "0 */6 * * *" means every 6 hours
        parts = validated_cron.split()
        minute, hour, day, month, day_of_week = parts
        return CronTrigger(minute=minute, hour=hour, day=day, month=month, day_of_week=day_of_week)

    def start_scheduler(self):
        """Starts the scheduler and adds jobs for all configured users."""
        logger.info("Scheduler start_scheduler method called.")
        
        # Remove all existing jobs before adding new ones
        self.scheduler.remove_all_jobs()
        
        # Start scheduler if not already running
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("Scheduler started.")
        
        # Get all user configurations
        secret_strs = self.redis_store.get_all_secret_strs()
        logger.info(f"Found {len(secret_strs)} secret_strs for scheduling: {secret_strs}")
        
        if not secret_strs:
            logger.warning("No user configurations found. Scheduler will not start any jobs.")
            return
        
        # Add scheduled jobs for each user
        jobs_added = 0
        jobs_failed = 0
        
        for secret_str in secret_strs:
            user_data = self.redis_store.get_user_data(secret_str)
            if not user_data:
                logger.warning(f"User data not found for secret_str: {secret_str}. Skipping scheduling.")
                jobs_failed += 1
                continue
            
            try:
                cron_trigger = self._parse_cron_expression(user_data.parser_schedule_crontab)
                job_id = f"m3u_fetch_{secret_str}"
                
                self.scheduler.add_job(
                    func=self._scheduled_fetch_wrapper,
                    trigger=cron_trigger,
                    args=[secret_str],
                    id=job_id,
                    replace_existing=True,
                    name=f"M3U fetch for {secret_str[:8]}..."
                )
                
                logger.info(f"Added scheduled job '{job_id}' with cron '{user_data.parser_schedule_crontab}' for secret_str: {secret_str[:8]}...")
                jobs_added += 1
                
            except ValueError as e:
                logger.error(f"Failed to parse cron expression '{user_data.parser_schedule_crontab}' for secret_str {secret_str[:8]}...: {e}")
                jobs_failed += 1
            except Exception as e:
                logger.error(f"Unexpected error scheduling job for secret_str {secret_str[:8]}...: {e}")
                jobs_failed += 1
        
        logger.info(f"Scheduler initialization complete. Added {jobs_added} jobs, {jobs_failed} failed.")

    def stop_scheduler(self):
        """Stops the scheduler gracefully."""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Scheduler stopped.")
        else:
            logger.info("Scheduler was not running.")

if __name__ == "__main__":
    scheduler = Scheduler()
    scheduler.start_scheduler()
    try:
        # Keep the main thread alive
        while True:
            pass
    except (KeyboardInterrupt, SystemExit):
        scheduler.stop_scheduler()
