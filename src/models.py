from pydantic import BaseModel, Field
from typing import List, Optional

class ConfigureRequest(BaseModel):
    m3u_sources: List[str] = Field(default_factory=list)
    epg_sources: List[str] = Field(default_factory=list)
    parser_schedule_crontab: str = "0 */6 * * *"
    host_url: str
    addon_password: Optional[str] = None

class UserData(BaseModel):
    m3u_sources: list[str]
    epg_sources: list[str]
    parser_schedule_crontab: str = "0 */6 * * *"
    host_url: str
    addon_password: Optional[str] = None
