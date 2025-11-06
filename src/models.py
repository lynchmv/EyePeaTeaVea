from pydantic import BaseModel, Field
from typing import List, Optional

class ConfigureRequest(BaseModel):
    m3u_sources: List[str] = Field(default_factory=list)
    parser_schedule_crontab: str = "0 */6 * * *"
    host_url: str
    addon_password: Optional[str] = None

class UserData(BaseModel):
    m3u_sources: list[str]
    parser_schedule_crontab: str = "0 */6 * * *"
    host_url: str
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