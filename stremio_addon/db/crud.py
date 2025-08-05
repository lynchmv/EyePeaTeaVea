import logging
from typing import List
from beanie.odm.operators.update.general import Set
from beanie import BulkWriter

from stremio_addon.db import models

async def save_tv_channels(channels: List[models.MediaFusionTVMetaData]):
    """
    Saves a list of TV channels to the database.
    This function will clear all existing channels and then insert the new,
    de-duplicated list to ensure it is always up-to-date.
    """
    if not channels:
        logging.warning("No TV channels provided to save.")
        return

    try:
        # --- Start of Change: De-duplicate the channel list ---
        unique_channels = {channel.id: channel for channel in channels}.values()
        logging.info(f"De-duplicated channel list. Original: {len(channels)}, Unique: {len(unique_channels)}")
        # --- End of Change ---

        logging.info(f"Clearing existing {await models.MediaFusionTVMetaData.count()} TV channels from the database.")
        await models.MediaFusionTVMetaData.delete_all()

        logging.info(f"Inserting {len(unique_channels)} new TV channels into the database.")
        # Insert the de-duplicated list of channels
        await models.MediaFusionTVMetaData.insert_many(list(unique_channels))

        logging.info("Successfully saved all new TV channels.")
    except Exception as e:
        logging.exception(f"An error occurred while saving TV channels: {e}")

async def save_live_events(events: List[models.MediaFusionEventsMetaData]):
    """
    Saves a list of live events to the database using an "upsert" operation.
    If an event with the same ID already exists, it will be updated.
    Otherwise, a new event will be created.
    """
    if not events:
        logging.warning("No live events provided to save.")
        return

    try:
        # Use a BulkWriter for efficient upsert operations
        async with BulkWriter() as writer:
            for event in events:
                await models.MediaFusionEventsMetaData.find_one({"_id": event.id}).update(
                    Set(event.model_dump(exclude_none=True)), upsert=True, bulk_writer=writer
                )

        logging.info(f"Successfully saved/updated {len(events)} live events.")
    except Exception as e:
        logging.exception(f"An error occurred while saving live events: {e}")

