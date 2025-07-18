import redis.asyncio as redis
from stremio_addon.core.config import settings

# Create a single, reusable asynchronous Redis client instance.
# This client will be imported and used by other parts of the application.
REDIS_ASYNC_CLIENT = redis.from_url(settings.redis_url)

