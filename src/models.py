from pydantic import BaseModel, Field, HttpUrl, field_validator
from typing import List, Optional
from .utils import validate_cron_expression

class ConfigureRequest(BaseModel):
    m3u_sources: List[str] = Field(..., min_length=1)
    parser_schedule_crontab: str = "0 */6 * * *"
    host_url: HttpUrl
    addon_password: Optional[str] = None
    
    @field_validator('parser_schedule_crontab')
    @classmethod
    def validate_cron(cls, v: str) -> str:
        """Validate that the cron expression is valid."""
        return validate_cron_expression(v)

class UserData(BaseModel):
    m3u_sources: list[str]
    parser_schedule_crontab: str = "0 */6 * * *"
    host_url: HttpUrl
    addon_password: Optional[str] = None

class Event(BaseModel):
    date: str
    time: str
    timezone: str
    team1: str
    team2: str

class Channel(BaseModel):
    group_title: str
    tvg_id: str
    tvg_name: str
    tvg_logo: str
    url_tvg: str
    stream_url: str
    events: List[Event] = Field(default_factory=list)