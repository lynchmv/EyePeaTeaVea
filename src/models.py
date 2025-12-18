from pydantic import BaseModel, Field, HttpUrl, field_validator
from typing import List, Optional
from .utils import validate_cron_expression, validate_url

class ConfigureRequest(BaseModel):
    m3u_sources: List[str] = Field(..., min_length=1, max_length=50)
    parser_schedule_crontab: str = "0 */6 * * *"
    host_url: HttpUrl
    addon_password: Optional[str] = None
    
    @field_validator('m3u_sources')
    @classmethod
    def validate_m3u_sources(cls, v: List[str]) -> List[str]:
        """Validate that all M3U sources are valid URLs."""
        if not v:
            raise ValueError("At least one M3U source is required")
        if len(v) > 50:
            raise ValueError("Maximum 50 M3U sources allowed")
        
        validated_sources = []
        for i, source in enumerate(v):
            source = source.strip()
            if not source:
                raise ValueError(f"M3U source at index {i} cannot be empty")
            validated_url = validate_url(source)
            validated_sources.append(validated_url)
        
        return validated_sources
    
    @field_validator('parser_schedule_crontab')
    @classmethod
    def validate_cron(cls, v: str) -> str:
        """Validate that the cron expression is valid."""
        return validate_cron_expression(v)

class UpdateConfigureRequest(BaseModel):
    """Request model for updating existing configuration. All fields are optional."""
    m3u_sources: Optional[List[str]] = Field(None, min_length=1, max_length=50)
    parser_schedule_crontab: Optional[str] = None
    host_url: Optional[HttpUrl] = None
    addon_password: Optional[str] = None
    
    @field_validator('m3u_sources')
    @classmethod
    def validate_m3u_sources(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        """Validate that all M3U sources are valid URLs if provided."""
        if v is None:
            return v
        
        if len(v) > 50:
            raise ValueError("Maximum 50 M3U sources allowed")
        
        validated_sources = []
        for i, source in enumerate(v):
            source = source.strip()
            if not source:
                raise ValueError(f"M3U source at index {i} cannot be empty")
            validated_url = validate_url(source)
            validated_sources.append(validated_url)
        
        return validated_sources
    
    @field_validator('parser_schedule_crontab')
    @classmethod
    def validate_cron(cls, v: Optional[str]) -> Optional[str]:
        """Validate that the cron expression is valid if provided."""
        if v is not None:
            return validate_cron_expression(v)
        return v

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