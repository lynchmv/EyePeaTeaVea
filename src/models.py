"""
Pydantic models for API request/response validation and data structures.

This module defines all data models used throughout the application:
- API request models (ConfigureRequest, UpdateConfigureRequest)
- Internal data models (UserData, Channel, Event)
- All models include validation logic for data integrity
"""
from pydantic import BaseModel, Field, HttpUrl, field_validator
from typing import Optional
import pytz
from .utils import validate_cron_expression, validate_url, validate_timezone

class ConfigureRequest(BaseModel):
    """
    Request model for initial addon configuration.
    
    All fields are required except addon_password and timezone. Includes validation
    for M3U sources (URLs), cron expressions, and timezone.
    """
    m3u_sources: list[str] = Field(..., min_length=1, max_length=50)
    parser_schedule_crontab: str = "0 */6 * * *"
    host_url: HttpUrl
    addon_password: str | None = None
    timezone: str | None = None
    
    @field_validator('host_url', mode='before')
    @classmethod
    def normalize_host_url(cls, v):
        """Normalize host_url by removing trailing slashes."""
        if isinstance(v, str):
            return v.rstrip('/')
        return v
    
    @field_validator('m3u_sources')
    @classmethod
    def validate_m3u_sources(cls, v: list[str]) -> list[str]:
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
    
    @field_validator('timezone')
    @classmethod
    def validate_timezone(cls, v: str | None) -> str | None:
        """Validate that the timezone is valid if provided."""
        if v is not None:
            return validate_timezone(v)
        return v

class UpdateConfigureRequest(BaseModel):
    """Request model for updating existing configuration. All fields are optional."""
    m3u_sources: list[str] | None = Field(None, min_length=1, max_length=50)
    parser_schedule_crontab: str | None = None
    host_url: HttpUrl | None = None
    addon_password: str | None = None
    timezone: str | None = None
    
    @field_validator('host_url', mode='before')
    @classmethod
    def normalize_host_url(cls, v):
        """Normalize host_url by removing trailing slashes."""
        if isinstance(v, str):
            return v.rstrip('/')
        return v
    
    @field_validator('m3u_sources')
    @classmethod
    def validate_m3u_sources(cls, v: list[str] | None) -> list[str] | None:
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
    def validate_cron(cls, v: str | None) -> str | None:
        """Validate that the cron expression is valid if provided."""
        if v is not None:
            return validate_cron_expression(v)
        return v
    
    @field_validator('timezone')
    @classmethod
    def validate_timezone(cls, v: str | None) -> str | None:
        """Validate that the timezone is valid if provided."""
        if v is not None:
            return validate_timezone(v)
        return v

class UserData(BaseModel):
    m3u_sources: list[str]
    parser_schedule_crontab: str = "0 */6 * * *"
    host_url: HttpUrl
    addon_password: str | None = None
    timezone: str | None = None  # IANA timezone name (e.g., "America/New_York", "Europe/London")

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
    events: list[Event] = Field(default_factory=list)

# Admin models
class AdminUser(BaseModel):
    """Admin user model for authentication and authorization."""
    username: str
    password_hash: str
    role: str = "admin"  # admin, super_admin, viewer
    created_at: str
    last_login: str | None = None
    is_active: bool = True

class AdminLoginRequest(BaseModel):
    """Request model for admin login."""
    username: str
    password: str

class AdminSession(BaseModel):
    """Admin session model."""
    session_id: str
    username: str
    role: str
    created_at: str
    expires_at: str
    ip_address: str | None = None

class UserSummary(BaseModel):
    """Summary model for user listing."""
    secret_str: str
    created_at: str | None = None
    channel_count: int = 0
    event_count: int = 0
    last_sync: str | None = None
    status: str = "unknown"  # active, warning, error
    m3u_source_count: int = 0

class SystemStats(BaseModel):
    """System statistics model."""
    total_users: int
    total_channels: int
    total_events: int
    active_scheduler_jobs: int
    redis_memory_used: int | None = None
    redis_memory_max: int | None = None
    cache_hit_rate: float | None = None
    users_last_24h: int = 0
    users_last_7d: int = 0
    users_last_30d: int = 0
    failed_parses_24h: int = 0
    average_response_time: float | None = None

class ChangePasswordRequest(BaseModel):
    """Request model for changing admin password."""
    old_password: str
    new_password: str

class LogoOverrideRequest(BaseModel):
    """Request model for creating/updating logo override."""
    tvg_id: str
    logo_url: str
    is_regex: bool = False
    
    @field_validator('logo_url')
    @classmethod
    def validate_logo_url(cls, v: str) -> str:
        """Validate logo URL."""
        if not v or not v.strip():
            raise ValueError("Logo URL cannot be empty")
        return validate_url(v.strip())