from datetime import datetime
from typing import Optional, List
from beanie import Document
from pydantic import Field, BaseModel

class TVStreams(BaseModel):
    """A Pydantic model for a single video stream."""
    meta_id: str
    name: str
    url: str
    source: str
    is_working: bool = True

class MediaFusionMetaData(Document):
    """A base model for all media types, containing common fields."""
    id: str = Field(..., alias="_id")
    title: str
    poster: Optional[str] = None
    logo: Optional[str] = None

    class Settings:
        is_root = True

class MediaFusionTVMetaData(MediaFusionMetaData):
    """The model for a regular, 24/7 TV channel."""
    streams: List[TVStreams]
    genres: Optional[List[str]] = Field(default_factory=list) # Added genres to store group-title

    class Settings:
        name = "tv_channels" # The name of the MongoDB collection

class MediaFusionEventsMetaData(MediaFusionMetaData):
    """The model for a time-sensitive live event."""
    event_start_timestamp: int
    genres: Optional[List[str]] = Field(default_factory=list)
    streams: List[TVStreams]

    class Settings:
        name = "live_events" # The name of the MongoDB collection

