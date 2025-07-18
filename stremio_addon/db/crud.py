import logging
from typing import List
from beanie.odm.operators.update.general import Set

from stremio_addon.db import models

async def save_tv_channels(channels: List[models.MediaFusionTVMetaData]):
    """
    Saves a list of TV channels to the database.
    This function will clear all existing channels before inserting the new ones
    to ensure the list is always up-to-date.
    """
    if not channels:
        logging.warning("No TV channels provided to save.")
        return

    try:
        logging.info(f"Clearing existing {await models.MediaFusionTVMetaData.count()} TV channels from the database.")
        # Delete all existing documents in the collection
        await models.MediaFusionTVMetaData.delete_all()

        logging.info(f"Inserting {len(channels)} new TV channels into the database.")
        # Insert the new list of channels
        await models.MediaFusionTVMetaData.insert_many(channels)

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
        update_operations = []
        for event in events:
            # Prepare an "update one" operation with upsert=True
            op = models.MediaFusionEventsMetaData.find_one({"_id": event.id}).update(
                Set(event.model_dump(exclude_none=True)), upsert=True
            )
            update_operations.append(op)

        logging.info(f"Upserting {len(events)} live events into the database.")
        # Execute all the upsert operations concurrently
        await models.MediaFusionEventsMetaData.bulk_write(update_operations)

        logging.info("Successfully saved all live events.")
    except Exception as e:
        logging.exception(f"An error occurred while saving live events: {e}")


