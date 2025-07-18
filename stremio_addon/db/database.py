import logging
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie

from stremio_addon.core.config import settings
from stremio_addon.db import models

async def init_db():
    """
    Initializes the database connection and the Beanie ODM.
    This function should be called once at application startup.
    """
    logging.info("Initializing database connection...")
    try:
        # Create a Motor client for asynchronous MongoDB access
        client = AsyncIOMotorClient(settings.mongo_uri)

        # Initialize Beanie with the database and all the document models
        await init_beanie(
            database=client.get_default_database(),
            document_models=[
                models.MediaFusionTVMetaData,
                models.MediaFusionEventsMetaData,
            ],
        )
        logging.info("Database connection and models initialized successfully.")
    except Exception as e:
        logging.error(f"Failed to initialize database: {e}")
        raise


