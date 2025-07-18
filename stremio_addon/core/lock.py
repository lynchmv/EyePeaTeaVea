import asyncio
import logging
import uuid
from typing import Tuple, Optional

from stremio_addon.db.redis_database import REDIS_ASYNC_CLIENT

SCHEDULER_LOCK_KEY = "scheduler_lock"
LOCK_TTL_SECONDS = 60  # Lock expires after 60 seconds

async def acquire_scheduler_lock() -> Tuple[bool, Optional[str]]:
    """Tries to acquire a lock for the scheduler."""
    lock_id = str(uuid.uuid4())
    # Try to set the key if it doesn't exist, with an expiration.
    if await REDIS_ASYNC_CLIENT.set(SCHEDULER_LOCK_KEY, lock_id, ex=LOCK_TTL_SECONDS, nx=True):
        logging.info(f"Scheduler lock acquired with ID: {lock_id}")
        return True, lock_id
    return False, None

async def release_scheduler_lock(lock_id: str):
    """Releases the lock if this process still holds it."""
    if await REDIS_ASYNC_CLIENT.get(SCHEDULER_LOCK_KEY) == lock_id:
        await REDIS_ASYNC_CLIENT.delete(SCHEDULER_LOCK_KEY)
        logging.info(f"Scheduler lock released for ID: {lock_id}")

async def maintain_heartbeat(lock_id: str):
    """Periodically refreshes the lock's TTL to keep it alive."""
    while True:
        await asyncio.sleep(LOCK_TTL_SECONDS / 2)
        if await REDIS_ASYNC_CLIENT.get(SCHEDULER_LOCK_KEY) == lock_id:
            await REDIS_ASYNC_CLIENT.expire(SCHEDULER_LOCK_KEY, LOCK_TTL_SECONDS)
            logging.debug(f"Scheduler lock heartbeat refreshed for ID: {lock_id}")
        else:
            logging.warning("Lost scheduler lock. Another instance may have taken over.")
            break
