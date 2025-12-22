"""
Scheduler module for managing background M3U playlist fetching.

This module provides a Scheduler class that uses APScheduler to periodically
fetch M3U playlists from configured sources and store the parsed channels
in Redis. Each user can have their own cron schedule for updates.
"""
import os
import redis
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

from .m3u_parser import M3UParser
from .epg_parser import EPGParser
from .redis_store import RedisStore, RedisConnectionError
from .models import UserData
from .utils import validate_cron_expression

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

class Scheduler:
    """
    Manages scheduled background tasks for fetching M3U playlists.
    
    Uses APScheduler to schedule periodic M3U playlist fetches based on
    user-configured cron expressions. Each user can have their own schedule.
    
    Attributes:
        redis_store: RedisStore instance for data access
        scheduler: BackgroundScheduler instance for managing jobs
    """
    def __init__(self) -> None:
        """
        Initialize the Scheduler with Redis connection and background scheduler.
        """
        self.redis_store = RedisStore(REDIS_URL)
        self.scheduler = BackgroundScheduler()

    def _fetch_and_store_m3u(self, secret_str: str, user_data: UserData) -> None:
        """
        Fetch M3U playlists from all configured sources and store channels in Redis.
        
        Processes all M3U sources for a user, parses channels, and stores them.
        Continues processing other sources even if one fails.
        
        Args:
            secret_str: User's unique secret string
            user_data: UserData containing M3U sources and configuration
        """
        logger.info(f"Starting scheduled M3U fetch for secret_str: {secret_str[:8]}...")
        all_channels_list = []
        errors = []
        
        for source in user_data.m3u_sources:
            try:
                m3u_parser = M3UParser(source)
                channels_list = m3u_parser.parse()
                all_channels_list.extend(channels_list)
                logger.info(f"Successfully parsed {len(channels_list)} channels from {source}")
            except (ValueError, IOError, ConnectionError) as e:
                # More specific exceptions for parsing/network errors
                error_msg = f"Error parsing M3U source {source}: {e}"
                logger.error(error_msg)
                errors.append(error_msg)
                # Continue with other sources even if one fails
            except Exception as e:
                # Catch-all for unexpected errors
                error_msg = f"Unexpected error parsing M3U source {source}: {e}"
                logger.error(error_msg, exc_info=True)
                errors.append(error_msg)
        
        if all_channels_list:
            try:
                self.redis_store.store_channels(secret_str, all_channels_list)
                # Invalidate manifest cache when channels are updated
                try:
                    self.redis_store.redis_client.delete(f"manifest:{secret_str}")
                except Exception:
                    # Non-critical, log but don't fail
                    logger.debug(f"Could not invalidate manifest cache for {secret_str[:8]}...")
                logger.info(f"Stored {len(all_channels_list)} channels for secret_str: {secret_str[:8]}...")
            except RedisConnectionError as e:
                logger.error(f"Failed to store channels for {secret_str[:8]}...: {e}")
                errors.append(f"Redis connection error: {e}")
        else:
            logger.warning(f"No channels were parsed for secret_str: {secret_str[:8]}...")
        
        # Fetch and store EPG data if available
        self._fetch_and_store_epg(secret_str, user_data, all_channels_list)
        
        if errors:
            logger.warning(f"Encountered {len(errors)} errors during M3U fetch for secret_str: {secret_str[:8]}...")
    
    def _fetch_and_store_epg(self, secret_str: str, user_data: UserData, channels_list: list[dict]) -> None:
        """
        Fetch EPG data from M3U sources and store in Redis.
        
        Extracts EPG URLs from M3U files and parses XMLTV EPG data.
        Maps EPG programs to channels using tvg-id matching.
        
        Args:
            secret_str: User's unique secret string
            user_data: UserData containing M3U sources
            channels_list: List of parsed channels (for tvg-id mapping)
        """
        epg_urls = set()
        
        # Collect EPG URLs from all M3U sources
        for source in user_data.m3u_sources:
            try:
                m3u_parser = M3UParser(source)
                # Extract EPG URLs from M3U header
                header_epg_urls = m3u_parser.extract_epg_urls()
                epg_urls.update(header_epg_urls)
                
                # Also collect per-channel url_tvg values
                for channel in channels_list:
                    url_tvg = channel.get("url_tvg", "")
                    if url_tvg:
                        epg_urls.add(url_tvg)
            except Exception as e:
                logger.debug(f"Could not extract EPG URLs from {source}: {e}")
                continue
        
        if not epg_urls:
            logger.debug(f"No EPG URLs found for secret_str: {secret_str[:8]}...")
            return
        
        # Create mapping of tvg-id to channel for matching
        tvg_id_map = {ch.get("tvg_id"): ch for ch in channels_list}
        
        # Parse EPG data from all URLs and merge
        all_epg_data = {}
        
        for epg_url in epg_urls:
            try:
                logger.info(f"Fetching EPG from {epg_url} for secret_str: {secret_str[:8]}...")
                epg_parser = EPGParser(epg_url)
                epg_data = epg_parser.parse()
                
                # Map EPG channel IDs to M3U tvg-ids
                # Try multiple matching strategies:
                # 1. Exact match with tvg-id
                # 2. Match by tvg-name (case-insensitive, partial match)
                # 3. Match EPG channel ID to tvg-id (normalized comparison)
                for epg_channel_id, programs in epg_data.items():
                    # Try to find matching channel
                    matched_tvg_id = None
                    
                    # Strategy 1: Exact match with tvg-id
                    if epg_channel_id in tvg_id_map:
                        matched_tvg_id = epg_channel_id
                        logger.debug(f"Matched EPG channel '{epg_channel_id}' to M3U tvg-id '{matched_tvg_id}' (exact match)")
                    else:
                        # Strategy 2: Try matching by channel name (case-insensitive)
                        epg_channel_name = epg_channel_id.lower().replace('.', ' ').replace('_', ' ')
                        for tvg_id, channel in tvg_id_map.items():
                            channel_name = channel.get("tvg_name", "").lower()
                            tvg_id_normalized = tvg_id.lower().replace('.', ' ').replace('_', ' ')
                            
                            # Check if EPG channel name matches tvg-name
                            if epg_channel_name == channel_name or epg_channel_name in channel_name or channel_name in epg_channel_name:
                                matched_tvg_id = tvg_id
                                logger.debug(f"Matched EPG channel '{epg_channel_id}' to M3U tvg-id '{matched_tvg_id}' (by name: '{channel.get('tvg_name')}')")
                                break
                            
                            # Strategy 3: Normalized comparison of EPG channel ID to tvg-id
                            if epg_channel_name == tvg_id_normalized or epg_channel_name in tvg_id_normalized or tvg_id_normalized in epg_channel_name:
                                matched_tvg_id = tvg_id
                                logger.debug(f"Matched EPG channel '{epg_channel_id}' to M3U tvg-id '{matched_tvg_id}' (normalized match)")
                                break
                    
                    if matched_tvg_id:
                        # Merge programs for this channel
                        if matched_tvg_id not in all_epg_data:
                            all_epg_data[matched_tvg_id] = []
                        all_epg_data[matched_tvg_id].extend(programs)
                        # Sort by start time
                        all_epg_data[matched_tvg_id].sort(key=lambda x: x["start"])
                        logger.debug(f"Added {len(programs)} programs for channel '{matched_tvg_id}'")
                    else:
                        logger.warning(f"Could not match EPG channel '{epg_channel_id}' to any M3U channel. Available tvg-ids: {list(tvg_id_map.keys())[:10]}...")
                
                logger.info(f"Parsed EPG from {epg_url}: {len(epg_data)} channels, {sum(len(progs) for progs in epg_data.values())} programs")
                
            except Exception as e:
                logger.warning(f"Error fetching/parsing EPG from {epg_url}: {e}")
                continue
        
        # Store merged EPG data
        if all_epg_data:
            try:
                self.redis_store.store_epg_data(secret_str, all_epg_data)
                logger.info(f"Stored EPG data for {len(all_epg_data)} channels for secret_str: {secret_str[:8]}...")
            except RedisConnectionError as e:
                logger.error(f"Failed to store EPG data for {secret_str[:8]}...: {e}")

    def _scheduled_fetch_wrapper(self, secret_str: str) -> None:
        """
        Wrapper function for scheduled jobs that retrieves user_data from Redis.
        
        This is called by APScheduler. It fetches the current user_data from Redis
        and then triggers the M3U fetch. This ensures we always use the latest
        configuration even if it was updated after scheduling.
        
        Args:
            secret_str: User's unique secret string
        """
        user_data = self.redis_store.get_user_data(secret_str)
        if not user_data:
            logger.error(f"User data not found for secret_str: {secret_str[:8]}.... Skipping scheduled fetch.")
            return
        self._fetch_and_store_m3u(secret_str, user_data)

    def trigger_m3u_fetch_for_user(self, secret_str: str, user_data: UserData) -> None:
        """
        Immediately trigger an M3U fetch for a user.
        
        Used during initial configuration to fetch channels right away,
        rather than waiting for the next scheduled run.
        
        Args:
            secret_str: User's unique secret string
            user_data: UserData containing M3U sources and configuration
        """
        self._fetch_and_store_m3u(secret_str, user_data)

    def _parse_cron_expression(self, cron_str: str) -> CronTrigger:
        """
        Parse a cron expression string into a CronTrigger object.
        
        Validates the cron expression and converts it to an APScheduler
        CronTrigger for scheduling jobs.
        
        Args:
            cron_str: Cron expression in format "minute hour day month day-of-week"
            
        Returns:
            CronTrigger object for use with APScheduler
            
        Raises:
            ValueError: If the cron expression is invalid
            
        Examples:
            >>> scheduler._parse_cron_expression("0 */6 * * *")
            <CronTrigger ...>
        """
        # Validate the cron expression first (raises ValueError if invalid)
        validated_cron = validate_cron_expression(cron_str)
        
        # Parse into CronTrigger
        # Cron format: "minute hour day month day-of-week"
        # Example: "0 */6 * * *" means every 6 hours
        parts = validated_cron.split()
        minute, hour, day, month, day_of_week = parts
        return CronTrigger(minute=minute, hour=hour, day=day, month=month, day_of_week=day_of_week)

    def start_scheduler(self) -> None:
        """
        Start the scheduler and add jobs for all configured users.
        
        Removes all existing jobs, starts the scheduler if not running,
        and creates scheduled jobs for each user based on their cron expression.
        Logs warnings for users with invalid configurations but continues
        processing other users.
        """
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
                logger.warning(f"User data not found for secret_str: {secret_str[:8]}.... Skipping scheduling.")
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

    def stop_scheduler(self) -> None:
        """
        Stop the scheduler gracefully.
        
        Shuts down the background scheduler, allowing running jobs to complete.
        Safe to call even if scheduler is not running.
        """
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
