"""
Admin API endpoints for managing users, monitoring system, and configuration.

This module provides admin-only endpoints for:
- User management (list, view, edit, delete)
- System monitoring (stats, health, logs)
- Scheduler management
- Configuration management
"""
import os
import json
import logging
import re
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Request, Cookie
from fastapi.responses import JSONResponse
from .redis_store import RedisStore, RedisConnectionError
from .models import (
    AdminLoginRequest, AdminUser, AdminSession, UserSummary, SystemStats,
    UserData, UpdateConfigureRequest, ChangePasswordRequest, LogoOverrideRequest
)
from .admin_auth import (
    authenticate_admin, create_admin_session, get_session,
    log_admin_action, get_client_ip, initialize_default_admin,
    SESSION_EXPIRATION_SECONDS
)
from .scheduler import Scheduler
from .utils import hash_password

logger = logging.getLogger(__name__)

# Initialize admin router
admin_router = APIRouter(prefix="/admin", tags=["admin"])

# Initialize dependencies
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_store = RedisStore(REDIS_URL)

# Note: scheduler will be imported from main.py to use the same instance
# This avoids creating a duplicate scheduler that isn't started
scheduler = None

def set_scheduler(scheduler_instance):
    """Set the scheduler instance from main.py"""
    global scheduler
    scheduler = scheduler_instance

# Initialize default admin on module load
initialize_default_admin(redis_store)

# Helper function to get current admin session
async def get_admin_session(
    request: Request,
    session_id: Optional[str] = Cookie(None)
) -> Optional[AdminSession]:
    """Get current admin session from cookie."""
    # Fallback: try to extract from cookie header if Cookie() dependency didn't work
    if not session_id:
        cookie_header = request.headers.get("cookie", "")
        if cookie_header:
            # Parse cookies manually
            for cookie in cookie_header.split(";"):
                cookie = cookie.strip()
                if cookie.startswith("session_id="):
                    session_id = cookie.split("=", 1)[1]
                    break
    
    if not session_id:
        logger.debug("No session_id cookie found in request")
        return None
    
    logger.debug(f"Found session_id cookie: {session_id[:16]}...")
    session = get_session(redis_store, session_id)
    if not session:
        logger.debug(f"Session {session_id[:16]}... not found in Redis or expired")
    return session

# Create role-specific dependencies
def require_viewer():
    """Dependency that requires viewer role or higher."""
    async def check_role(session: Optional[AdminSession] = Depends(get_admin_session)):
        if not session:
            raise HTTPException(status_code=401, detail="Authentication required")
        role_hierarchy = {"viewer": 1, "admin": 2, "super_admin": 3}
        user_level = role_hierarchy.get(session.role, 0)
        if user_level < 1:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return session
    return check_role

def require_admin():
    """Dependency that requires admin role or higher."""
    async def check_role(session: Optional[AdminSession] = Depends(get_admin_session)):
        if not session:
            raise HTTPException(status_code=401, detail="Authentication required")
        role_hierarchy = {"viewer": 1, "admin": 2, "super_admin": 3}
        user_level = role_hierarchy.get(session.role, 0)
        if user_level < 2:
            raise HTTPException(status_code=403, detail="Admin role required")
        return session
    return check_role

# Authentication endpoints
@admin_router.post("/login")
async def admin_login(
    request: Request,
    login_data: AdminLoginRequest
):
    """
    Admin login endpoint.
    
    Authenticates admin user and creates a session.
    Returns session ID as cookie.
    """
    admin = authenticate_admin(redis_store, login_data.username, login_data.password)
    if not admin:
        log_admin_action(
            redis_store,
            login_data.username,
            "login_failed",
            ip_address=get_client_ip(request)
        )
        raise HTTPException(status_code=401, detail="Invalid username or password")
    
    session_id = create_admin_session(
        redis_store,
        admin.username,
        admin.role,
        get_client_ip(request)
    )
    
    log_admin_action(
        redis_store,
        admin.username,
        "login_success",
        ip_address=get_client_ip(request)
    )
    
    response = JSONResponse({"message": "Login successful", "username": admin.username, "role": admin.role})
    response.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,
        secure=True,  # Set to True in production with HTTPS
        samesite="lax",
        max_age=SESSION_EXPIRATION_SECONDS
    )
    logger.info(f"Set session cookie for admin user: {admin.username}, session_id: {session_id[:16]}...")
    return response

@admin_router.post("/logout")
async def admin_logout(
    session: AdminSession = Depends(require_viewer())
):
    """Admin logout endpoint."""
    redis_store.delete_admin_session(session.session_id)
    log_admin_action(redis_store, session.username, "logout")
    
    response = JSONResponse({"message": "Logout successful"})
    response.delete_cookie(key="session_id")
    return response

@admin_router.get("/me")
async def get_current_admin(
    session: AdminSession = Depends(require_viewer())
):
    """Get current admin user info."""
    admin_data = redis_store.get_admin_user(session.username)
    if not admin_data:
        raise HTTPException(status_code=404, detail="Admin user not found")
    
    # Don't return password hash
    admin_data.pop("password_hash", None)
    return admin_data

@admin_router.post("/change-password")
async def change_password(
    request: Request,
    password_data: ChangePasswordRequest,
    session: AdminSession = Depends(require_viewer())
):
    """Change the current admin user's password."""
    if not password_data.new_password or len(password_data.new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters long")
    
    # Get admin user and verify old password
    admin_data = redis_store.get_admin_user(session.username)
    if not admin_data:
        raise HTTPException(status_code=404, detail="Admin user not found")
    
    from .utils import verify_password, hash_password
    
    # Verify old password
    if not verify_password(password_data.old_password, admin_data.get("password_hash", "")):
        log_admin_action(
            redis_store,
            session.username,
            "password_change_failed",
            details={"reason": "invalid_old_password"},
            ip_address=get_client_ip(request)
        )
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    
    # Update password
    admin_data["password_hash"] = hash_password(password_data.new_password)
    redis_store.store_admin_user(session.username, admin_data)
    
    log_admin_action(
        redis_store,
        session.username,
        "password_changed",
        ip_address=get_client_ip(request)
    )
    
    return {"message": "Password changed successfully"}

# User management endpoints
@admin_router.get("/users")
async def list_users(
    page: int = 1,
    per_page: int = 50,
    search: Optional[str] = None,
    session: AdminSession = Depends(require_viewer())
):
    """
    List all users with pagination and search.
    
    Requires viewer role or higher.
    """
    all_secret_strs = redis_store.get_all_secret_strs()
    
    # Filter by search if provided
    if search:
        all_secret_strs = [s for s in all_secret_strs if search.lower() in s.lower()]
    
    # Calculate pagination
    total = len(all_secret_strs)
    start = (page - 1) * per_page
    end = start + per_page
    paginated_strs = all_secret_strs[start:end]
    
    # Build user summaries
    users = []
    for secret_str in paginated_strs:
        user_data = redis_store.get_user_data(secret_str)
        if not user_data:
            continue
        
        channels = redis_store.get_all_channels(secret_str)
        channel_count = len(channels)
        event_count = sum(1 for c in channels.values() if json.loads(c).get("is_event", False))
        
        # Determine status (simplified - could be enhanced)
        status = "active"
        if channel_count == 0:
            status = "error"
        elif channel_count < 10:
            status = "warning"
        
        # Get creation time from Redis key TTL or estimate
        # Note: Redis doesn't store creation time, so we'll use a placeholder
        created_at = None
        
        users.append(UserSummary(
            secret_str=secret_str,
            created_at=created_at,
            channel_count=channel_count,
            event_count=event_count,
            last_sync=None,  # Could be tracked separately
            status=status,
            m3u_source_count=len(user_data.m3u_sources)
        ))
    
    log_admin_action(redis_store, session.username, "users_listed", details={"page": page})
    
    return {
        "users": [u.model_dump() for u in users],
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": (total + per_page - 1) // per_page
        }
    }

@admin_router.get("/users/{secret_str}")
async def get_user(
    secret_str: str,
    session: AdminSession = Depends(require_viewer())
):
    """Get detailed user information."""
    user_data = redis_store.get_user_data(secret_str)
    if not user_data:
        raise HTTPException(status_code=404, detail="User not found")
    
    channels = redis_store.get_all_channels(secret_str)
    channel_count = len(channels)
    event_count = sum(1 for c in channels.values() if json.loads(c).get("is_event", False))
    
    epg_data = redis_store.get_epg_data(secret_str)
    epg_channel_count = len(epg_data) if epg_data else 0
    
    # Get parse history
    parse_history = redis_store.get_parse_history(secret_str, limit=20)
    
    # Get recent errors
    recent_errors = redis_store.get_user_errors(secret_str, limit=20)
    
    log_admin_action(redis_store, session.username, "user_viewed", resource=f"user:{secret_str}")
    
    return {
        "secret_str": secret_str,
        "configuration": {
            "m3u_sources": user_data.m3u_sources,
            "parser_schedule_crontab": user_data.parser_schedule_crontab,
            "host_url": str(user_data.host_url),
            "has_password": user_data.addon_password is not None,
            "timezone": user_data.timezone
        },
        "statistics": {
            "channel_count": channel_count,
            "event_count": event_count,
            "epg_channel_count": epg_channel_count,
            "m3u_source_count": len(user_data.m3u_sources)
        },
        "parse_history": parse_history,
        "recent_errors": recent_errors
    }

@admin_router.put("/users/{secret_str}")
async def update_user(
    secret_str: str,
    update_data: UpdateConfigureRequest,
    session: AdminSession = Depends(require_admin())
):
    """Update user configuration (admin override)."""
    user_data = redis_store.get_user_data(secret_str)
    if not user_data:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Merge updates
    updated_m3u_sources = update_data.m3u_sources if update_data.m3u_sources is not None else user_data.m3u_sources
    updated_crontab = update_data.parser_schedule_crontab if update_data.parser_schedule_crontab is not None else user_data.parser_schedule_crontab
    updated_host_url = update_data.host_url if update_data.host_url is not None else user_data.host_url
    updated_timezone = update_data.timezone if update_data.timezone is not None else user_data.timezone
    
    if update_data.addon_password is not None:
        updated_password = None if update_data.addon_password == "" else hash_password(update_data.addon_password)
    else:
        updated_password = user_data.addon_password
    
    # Normalize host_url
    if updated_host_url:
        updated_host_url_str = str(updated_host_url).rstrip('/')
        from .models import HttpUrl
        updated_host_url = HttpUrl(updated_host_url_str)
    
    updated_user_data = UserData(
        m3u_sources=updated_m3u_sources,
        parser_schedule_crontab=updated_crontab,
        host_url=updated_host_url,
        addon_password=updated_password,
        timezone=updated_timezone
    )
    
    redis_store.store_user_data(secret_str, updated_user_data)
    redis_store.redis_client.delete(f"manifest:{secret_str}")
    
    # Trigger immediate fetch
    if scheduler:
        scheduler.trigger_m3u_fetch_for_user(secret_str, updated_user_data)
        scheduler.start_scheduler()
    
    log_admin_action(
        redis_store,
        session.username,
        "user_updated",
        resource=f"user:{secret_str}",
        details={"updated_fields": update_data.model_dump(exclude_none=True)}
    )
    
    return {"message": "User updated successfully", "secret_str": secret_str}

@admin_router.delete("/users/{secret_str}")
async def delete_user(
    secret_str: str,
    session: AdminSession = Depends(require_admin())
):
    """Delete a user and all their data."""
    user_data = redis_store.get_user_data(secret_str)
    if not user_data:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Delete user data
    redis_store.redis_client.delete(f"user_data:{secret_str}")
    
    # Delete channels
    redis_store.clear_user_channels(secret_str)
    
    # Delete EPG data
    redis_store.redis_client.delete(f"epg:{secret_str}")
    
    # Delete manifest cache
    redis_store.redis_client.delete(f"manifest:{secret_str}")
    
    log_admin_action(
        redis_store,
        session.username,
        "user_deleted",
        resource=f"user:{secret_str}"
    )
    
    return {"message": "User deleted successfully"}

@admin_router.post("/users/{secret_str}/parse")
async def trigger_user_parse(
    secret_str: str,
    session: AdminSession = Depends(require_admin())
):
    """Manually trigger M3U parse for a user."""
    user_data = redis_store.get_user_data(secret_str)
    if not user_data:
        raise HTTPException(status_code=404, detail="User not found")
    
    if scheduler:
        scheduler.trigger_m3u_fetch_for_user(secret_str, user_data)
    else:
        raise HTTPException(status_code=503, detail="Scheduler not available")
    
    log_admin_action(
        redis_store,
        session.username,
        "user_parse_triggered",
        resource=f"user:{secret_str}"
    )
    
    return {"message": "Parse triggered successfully"}

@admin_router.post("/users/{secret_str}/cache/clear")
async def clear_user_cache(
    secret_str: str,
    session: AdminSession = Depends(require_admin())
):
    """Clear cache for a user (channels, manifest, EPG, and images)."""
    user_data = redis_store.get_user_data(secret_str)
    if not user_data:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Clear channel data, manifest, and EPG
    redis_store.clear_user_channels(secret_str)
    redis_store.redis_client.delete(f"manifest:{secret_str}")
    redis_store.redis_client.delete(f"epg:{secret_str}")
    
    # Also clear image cache
    try:
        all_channels = redis_store.get_all_channels(secret_str)
        image_types = ["poster", "background", "logo", "icon"]
        deleted_image_count = 0
        
        for tvg_id, channel_json in all_channels.items():
            for image_type in image_types:
                cache_key = f"{tvg_id}_{image_type}"
                redis_key = f"processed_image:{cache_key}"
                result = redis_store.redis_client.delete(redis_key)
                if result > 0:
                    deleted_image_count += result
                
                # Delete placeholder cache keys
                pattern = f"processed_image:{cache_key}_placeholder_*"
                placeholder_keys = list(redis_store.redis_client.scan_iter(match=pattern))
                if placeholder_keys:
                    result = redis_store.redis_client.delete(*placeholder_keys)
                    deleted_image_count += result
        
        logger.info(f"Cleared {deleted_image_count} cached image(s) for user {secret_str[:8]}...")
    except Exception as e:
        logger.warning(f"Could not clear image cache for user {secret_str[:8]}...: {e}")
    
    log_admin_action(
        redis_store,
        session.username,
        "user_cache_cleared",
        resource=f"user:{secret_str}"
    )
    
    return {"message": "Cache cleared successfully"}

# Channels and Events endpoints
@admin_router.get("/channels")
async def list_channels(
    page: int = 1,
    per_page: int = 100,
    search: Optional[str] = None,
    user_filter: Optional[str] = None,
    session: AdminSession = Depends(require_viewer())
):
    """List all channels across all users."""
    all_channels = []
    all_secret_strs = redis_store.get_all_secret_strs()
    
    # Filter by user if provided
    if user_filter:
        all_secret_strs = [s for s in all_secret_strs if user_filter.lower() in s.lower()]
    
    # Collect all channels
    for secret_str in all_secret_strs:
        channels = redis_store.get_all_channels(secret_str)
        for tvg_id, channel_json in channels.items():
            try:
                channel = json.loads(channel_json)
                # Skip events
                if channel.get("is_event", False):
                    continue
                
                # Filter by search if provided
                if search:
                    search_lower = search.lower()
                    if (search_lower not in channel.get("tvg_name", "").lower() and
                        search_lower not in channel.get("group_title", "").lower() and
                        search_lower not in tvg_id.lower()):
                        continue
                
                channel["secret_str"] = secret_str
                channel["tvg_id"] = tvg_id
                all_channels.append(channel)
            except json.JSONDecodeError:
                continue
    
    # Sort by name
    all_channels.sort(key=lambda x: x.get("tvg_name", "").lower())
    
    # Paginate
    total = len(all_channels)
    start = (page - 1) * per_page
    end = start + per_page
    paginated_channels = all_channels[start:end]
    
    return {
        "channels": paginated_channels,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": (total + per_page - 1) // per_page
        }
    }

@admin_router.get("/events")
async def list_events(
    page: int = 1,
    per_page: int = 100,
    search: Optional[str] = None,
    user_filter: Optional[str] = None,
    session: AdminSession = Depends(require_viewer())
):
    """List all events across all users."""
    all_events = []
    all_secret_strs = redis_store.get_all_secret_strs()
    
    # Filter by user if provided
    if user_filter:
        all_secret_strs = [s for s in all_secret_strs if user_filter.lower() in s.lower()]
    
    # Collect all events
    for secret_str in all_secret_strs:
        channels = redis_store.get_all_channels(secret_str)
        for tvg_id, channel_json in channels.items():
            try:
                channel = json.loads(channel_json)
                # Only include events
                if not channel.get("is_event", False):
                    continue
                
                # Filter by search if provided
                if search:
                    search_lower = search.lower()
                    event_title = channel.get("event_title", "")
                    event_sport = channel.get("event_sport", "")
                    if (search_lower not in event_title.lower() and
                        search_lower not in event_sport.lower() and
                        search_lower not in tvg_id.lower()):
                        continue
                
                channel["secret_str"] = secret_str
                channel["tvg_id"] = tvg_id
                all_events.append(channel)
            except json.JSONDecodeError:
                continue
    
    # Sort by event title
    all_events.sort(key=lambda x: x.get("event_title", "").lower())
    
    # Paginate
    total = len(all_events)
    start = (page - 1) * per_page
    end = start + per_page
    paginated_events = all_events[start:end]
    
    return {
        "events": paginated_events,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": (total + per_page - 1) // per_page
        }
    }

# System monitoring endpoints
@admin_router.get("/stats")
async def get_system_stats(
    session: AdminSession = Depends(require_viewer())
):
    """Get system statistics."""
    all_secret_strs = redis_store.get_all_secret_strs()
    total_users = len(all_secret_strs)
    
    total_channels = 0
    total_events = 0
    for secret_str in all_secret_strs:
        channels = redis_store.get_all_channels(secret_str)
        total_channels += len(channels)
        total_events += sum(1 for c in channels.values() if json.loads(c).get("is_event", False))
    
    # Get Redis memory info
    redis_memory_used = None
    redis_memory_max = None
    try:
        info = redis_store.redis_client.info("memory")
        redis_memory_used = info.get("used_memory", 0)
        redis_memory_max = info.get("maxmemory", 0)
    except Exception:
        pass
    
    # Get scheduler job count
    active_jobs = 0
    if scheduler and scheduler.scheduler and scheduler.scheduler.running:
        try:
            active_jobs = len(scheduler.scheduler.get_jobs())
        except Exception:
            pass
    
    stats = SystemStats(
        total_users=total_users,
        total_channels=total_channels,
        total_events=total_events,
        active_scheduler_jobs=active_jobs,
        redis_memory_used=redis_memory_used,
        redis_memory_max=redis_memory_max,
        cache_hit_rate=None,  # Could be tracked separately
        users_last_24h=0,  # Could be tracked separately
        users_last_7d=0,
        users_last_30d=0,
        failed_parses_24h=0,  # Could be tracked separately
        average_response_time=None
    )
    
    return stats.model_dump()

@admin_router.get("/health")
async def get_system_health(
    session: AdminSession = Depends(require_viewer())
):
    """Get detailed system health information."""
    health = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "checks": {}
    }
    
    # Redis check
    try:
        is_connected = redis_store.is_connected()
        if is_connected:
            redis_store.redis_client.ping()
            health["checks"]["redis"] = {
                "status": "healthy",
                "connected": True
            }
        else:
            health["checks"]["redis"] = {
                "status": "unhealthy",
                "connected": False
            }
            health["status"] = "degraded"
    except Exception as e:
        health["checks"]["redis"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        health["status"] = "unhealthy"
    
    # Scheduler check
    try:
        if scheduler and scheduler.scheduler and scheduler.scheduler.running:
            try:
                job_count = len(scheduler.scheduler.get_jobs())
                health["checks"]["scheduler"] = {
                    "status": "healthy",
                    "running": True,
                    "job_count": job_count
                }
            except Exception as e:
                health["checks"]["scheduler"] = {
                    "status": "degraded",
                    "running": True,
                    "error": f"Error getting jobs: {str(e)}"
                }
                health["status"] = "degraded"
        else:
            health["checks"]["scheduler"] = {
                "status": "unhealthy",
                "running": False,
                "error": "Scheduler not initialized or not running"
            }
            health["status"] = "degraded"
    except Exception as e:
        health["checks"]["scheduler"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        health["status"] = "degraded"
    
    return health

@admin_router.get("/scheduler/jobs")
async def get_scheduler_jobs(
    session: AdminSession = Depends(require_viewer())
):
    """Get list of scheduled jobs."""
    if not scheduler or not scheduler.scheduler or not scheduler.scheduler.running:
        return {"jobs": [], "status": "stopped"}
    
    jobs = []
    try:
        for job in scheduler.scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                "func": job.func.__name__ if hasattr(job.func, "__name__") else str(job.func)
            })
    except Exception as e:
        logger.error(f"Error getting scheduler jobs: {e}")
    
    return {"jobs": jobs, "status": "running"}

@admin_router.get("/logs")
async def get_audit_logs(
    limit: int = 100,
    session: AdminSession = Depends(require_viewer())
):
    """Get audit logs."""
    # Note: This is a simplified implementation
    # In production, you might want to use Redis Streams or a proper logging system
    logs = []
    
    try:
        # Scan for audit log keys
        pattern = "audit_log:*"
        keys = list(redis_store.redis_client.scan_iter(match=pattern))
        
        # Sort by timestamp (from key) and limit
        keys.sort(reverse=True)
        keys = keys[:limit]
        
        for key in keys:
            log_json = redis_store.redis_client.get(key)
            if log_json:
                logs.append(json.loads(log_json))
    except Exception as e:
        logger.error(f"Error fetching audit logs: {e}")
    
    return {"logs": logs, "count": len(logs)}

# Logo override endpoints
@admin_router.get("/users/{secret_str}/logo-overrides")
async def get_logo_overrides(
    secret_str: str,
    session: AdminSession = Depends(require_viewer())
):
    """Get all logo overrides for a user."""
    user_data = redis_store.get_user_data(secret_str)
    if not user_data:
        raise HTTPException(status_code=404, detail="User not found")
    
    overrides_dict = redis_store.get_all_logo_overrides(secret_str)
    
    # Convert to list format for API response
    overrides = []
    override_tvg_ids = set()  # For quick lookup
    for tvg_id, override_info in overrides_dict.items():
        overrides.append({
            "tvg_id": tvg_id,
            "logo_url": override_info.get("logo_url", ""),
            "is_regex": override_info.get("is_regex", False)
        })
        override_tvg_ids.add(tvg_id)
    
    # Also return available channels for reference
    channels = redis_store.get_all_channels(secret_str)
    available_channels = []
    for tvg_id, channel_json in channels.items():
        try:
            channel = json.loads(channel_json)
            # Check if this channel has an exact override (not regex)
            has_override = tvg_id in override_tvg_ids
            available_channels.append({
                "tvg_id": tvg_id,
                "tvg_name": channel.get("tvg_name", tvg_id),
                "has_override": has_override
            })
        except json.JSONDecodeError:
            continue
    
    # Sort by name
    available_channels.sort(key=lambda x: x["tvg_name"].lower())
    
    log_admin_action(redis_store, session.username, "logo_overrides_viewed", resource=f"user:{secret_str}")
    
    return {
        "overrides": overrides,
        "available_channels": available_channels
    }

@admin_router.post("/users/{secret_str}/logo-overrides")
async def create_logo_override(
    secret_str: str,
    override_data: LogoOverrideRequest,
    session: AdminSession = Depends(require_admin())
):
    """Create or update a logo override for a channel."""
    user_data = redis_store.get_user_data(secret_str)
    if not user_data:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Validate regex pattern if is_regex is True
    if override_data.is_regex:
        try:
            re.compile(override_data.tvg_id)
        except re.error as e:
            raise HTTPException(status_code=400, detail=f"Invalid regex pattern: {e}")
    
    redis_store.store_logo_override(secret_str, override_data.tvg_id, override_data.logo_url, override_data.is_regex)
    
    # Invalidate image cache for affected channels
    try:
        channels_to_invalidate = []
        
        if override_data.is_regex:
            # For regex patterns, find all channels that match
            try:
                regex_pattern = re.compile(override_data.tvg_id)
                all_channels = redis_store.get_all_channels(secret_str)
                for tvg_id, channel_json in all_channels.items():
                    if regex_pattern.match(tvg_id):
                        channels_to_invalidate.append(tvg_id)
                logger.info(f"Found {len(channels_to_invalidate)} channel(s) matching regex pattern '{override_data.tvg_id}'")
            except re.error as e:
                logger.warning(f"Invalid regex pattern for cache invalidation: {override_data.tvg_id}: {e}")
        else:
            # For exact matches, just invalidate this one channel
            channels_to_invalidate = [override_data.tvg_id]
        
        # Invalidate cache for all affected channels
        image_types = ["poster", "background", "logo", "icon"]
        deleted_count = 0
        
        # Sample a few channel names for debugging
        sample_channels = channels_to_invalidate[:3] if len(channels_to_invalidate) > 3 else channels_to_invalidate
        logger.debug(f"Sample channels to invalidate: {sample_channels}")
        
        for tvg_id in channels_to_invalidate:
            for image_type in image_types:
                # Delete regular cache keys
                cache_key = f"{tvg_id}_{image_type}"
                redis_key = f"processed_image:{cache_key}"
                
                # Try to delete - delete returns count of deleted keys
                result = redis_store.redis_client.delete(redis_key)
                if result > 0:
                    deleted_count += result
                    logger.debug(f"Deleted cache key: {redis_key}")
                
                # Delete placeholder cache keys (using pattern matching for version suffix)
                # Pattern matches: processed_image:{tvg_id}_{image_type}_placeholder_*
                pattern = f"processed_image:{cache_key}_placeholder_*"
                placeholder_keys = list(redis_store.redis_client.scan_iter(match=pattern))
                if placeholder_keys:
                    result = redis_store.redis_client.delete(*placeholder_keys)
                    deleted_count += result
                    key_strs = [k.decode('utf-8') if isinstance(k, bytes) else str(k) for k in placeholder_keys[:3]]
                    logger.debug(f"Deleted {len(placeholder_keys)} placeholder cache key(s) for {tvg_id} {image_type}: {key_strs}")
                else:
                    logger.debug(f"No placeholder keys found matching pattern: {pattern}")
        
        if deleted_count > 0:
            logger.info(f"Invalidated {deleted_count} cached image(s) for {len(channels_to_invalidate)} channel(s) matching pattern '{override_data.tvg_id}'")
        else:
            logger.warning(f"No cached images found to invalidate for {len(channels_to_invalidate)} channel(s) matching pattern '{override_data.tvg_id}'. Images may not have been cached yet, or cache keys may use a different format.")
            # Try to find what cache keys actually exist for debugging
            if len(channels_to_invalidate) > 0:
                sample_tvg_id = channels_to_invalidate[0]
                debug_pattern = f"processed_image:{sample_tvg_id}_*"
                existing_keys = list(redis_store.redis_client.scan_iter(match=debug_pattern))[:5]
                if existing_keys:
                    key_strs = [k.decode('utf-8') if isinstance(k, bytes) else str(k) for k in existing_keys]
                    logger.debug(f"Found existing cache keys for sample channel '{sample_tvg_id}': {key_strs}")
                else:
                    logger.debug(f"No cache keys found matching pattern: {debug_pattern}")
    except Exception as e:
        logger.warning(f"Could not invalidate image cache for {override_data.tvg_id}: {e}")
    
    log_admin_action(
        redis_store,
        session.username,
        "logo_override_created",
        resource=f"user:{secret_str}",
        details={"tvg_id": override_data.tvg_id, "logo_url": override_data.logo_url, "is_regex": override_data.is_regex}
    )
    
    return {
        "message": "Logo override created successfully",
        "tvg_id": override_data.tvg_id,
        "logo_url": override_data.logo_url,
        "is_regex": override_data.is_regex
    }

@admin_router.delete("/users/{secret_str}/logo-overrides/{tvg_id}")
async def delete_logo_override(
    secret_str: str,
    tvg_id: str,
    session: AdminSession = Depends(require_admin())
):
    """Delete a logo override for a channel."""
    user_data = redis_store.get_user_data(secret_str)
    if not user_data:
        raise HTTPException(status_code=404, detail="User not found")
    
    override = redis_store.get_logo_override(secret_str, tvg_id)
    if not override:
        raise HTTPException(status_code=404, detail="Logo override not found")
    
    redis_store.delete_logo_override(secret_str, tvg_id)
    
    # Also invalidate cache for this channel
    try:
        image_types = ["poster", "background", "logo", "icon"]
        deleted_count = 0
        
        for image_type in image_types:
            cache_key = f"{tvg_id}_{image_type}"
            redis_key = f"processed_image:{cache_key}"
            result = redis_store.redis_client.delete(redis_key)
            if result > 0:
                deleted_count += result
            
            # Delete placeholder cache keys
            pattern = f"processed_image:{cache_key}_placeholder_*"
            placeholder_keys = list(redis_store.redis_client.scan_iter(match=pattern))
            if placeholder_keys:
                result = redis_store.redis_client.delete(*placeholder_keys)
                deleted_count += result
        
        logger.info(f"Invalidated {deleted_count} cached image(s) for channel '{tvg_id}' after deleting logo override")
    except Exception as e:
        logger.warning(f"Could not invalidate image cache for {tvg_id} after deleting override: {e}")
    
    log_admin_action(
        redis_store,
        session.username,
        "logo_override_deleted",
        resource=f"user:{secret_str}",
        details={"tvg_id": tvg_id}
    )
    
    return {"message": "Logo override deleted successfully", "tvg_id": tvg_id}

@admin_router.post("/users/{secret_str}/clear-image-cache")
async def clear_user_image_cache(
    secret_str: str,
    session: AdminSession = Depends(require_admin())
):
    """Clear all cached images for a user's channels."""
    user_data = redis_store.get_user_data(secret_str)
    if not user_data:
        raise HTTPException(status_code=404, detail="User not found")
    
    try:
        # Get all channels for this user
        all_channels = redis_store.get_all_channels(secret_str)
        image_types = ["poster", "background", "logo", "icon"]
        deleted_count = 0
        
        for tvg_id, channel_json in all_channels.items():
            for image_type in image_types:
                # Delete regular cache keys
                cache_key = f"{tvg_id}_{image_type}"
                redis_key = f"processed_image:{cache_key}"
                result = redis_store.redis_client.delete(redis_key)
                if result > 0:
                    deleted_count += result
                
                # Delete placeholder cache keys
                pattern = f"processed_image:{cache_key}_placeholder_*"
                placeholder_keys = list(redis_store.redis_client.scan_iter(match=pattern))
                if placeholder_keys:
                    result = redis_store.redis_client.delete(*placeholder_keys)
                    deleted_count += result
        
        log_admin_action(
            redis_store,
            session.username,
            "image_cache_cleared",
            resource=f"user:{secret_str}",
            details={"channels": len(all_channels), "deleted_keys": deleted_count}
        )
        
        return {
            "message": "Image cache cleared successfully",
            "channels_processed": len(all_channels),
            "deleted_keys": deleted_count
        }
    except Exception as e:
        logger.error(f"Error clearing image cache for user {secret_str[:8]}...: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to clear cache: {str(e)}")

@admin_router.post("/users/{secret_str}/clear-cache/{tvg_id}")
async def clear_channel_cache(
    secret_str: str,
    tvg_id: str,
    session: AdminSession = Depends(require_admin())
):
    """Clear cached images for a specific channel."""
    user_data = redis_store.get_user_data(secret_str)
    if not user_data:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Verify channel exists for this user
    channel = redis_store.get_channel(secret_str, tvg_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    
    try:
        image_types = ["poster", "background", "logo", "icon"]
        deleted_count = 0
        
        for image_type in image_types:
            # Delete regular cache keys
            cache_key = f"{tvg_id}_{image_type}"
            redis_key = f"processed_image:{cache_key}"
            result = redis_store.redis_client.delete(redis_key)
            if result > 0:
                deleted_count += result
            
            # Delete placeholder cache keys
            pattern = f"processed_image:{cache_key}_placeholder_*"
            placeholder_keys = list(redis_store.redis_client.scan_iter(match=pattern))
            if placeholder_keys:
                result = redis_store.redis_client.delete(*placeholder_keys)
                deleted_count += result
        
        log_admin_action(
            redis_store,
            session.username,
            "channel_cache_cleared",
            resource=f"user:{secret_str}",
            details={"tvg_id": tvg_id, "deleted_keys": deleted_count}
        )
        
        return {
            "message": "Channel cache cleared successfully",
            "tvg_id": tvg_id,
            "deleted_keys": deleted_count
        }
    except Exception as e:
        logger.error(f"Error clearing cache for channel {tvg_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to clear cache: {str(e)}")
    
    # Invalidate image cache for this channel
    try:
        patterns = [
            f"processed_image:{tvg_id}_poster*",
            f"processed_image:{tvg_id}_background*",
            f"processed_image:{tvg_id}_logo*",
            f"processed_image:{tvg_id}_icon*"
        ]
        for pattern in patterns:
            keys = list(redis_store.redis_client.scan_iter(match=pattern))
            if keys:
                redis_store.redis_client.delete(*keys)
    except Exception as e:
        logger.warning(f"Could not invalidate image cache for {tvg_id}: {e}")
    
    log_admin_action(
        redis_store,
        session.username,
        "logo_override_deleted",
        resource=f"user:{secret_str}",
        details={"tvg_id": tvg_id}
    )
    
    return {"message": "Logo override deleted successfully"}
