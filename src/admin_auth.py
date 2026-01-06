"""
Admin authentication and authorization utilities.

This module provides functions for:
- Admin user authentication
- Session management
- Role-based access control
- Audit logging
"""
import secrets
import logging
from datetime import datetime, timedelta
from typing import Optional
from fastapi import HTTPException, Request, Depends
from .redis_store import RedisStore
from .models import AdminUser, AdminSession
from .utils import hash_password, verify_password

logger = logging.getLogger(__name__)

# Session configuration
SESSION_EXPIRATION_SECONDS = 3600 * 24  # 24 hours
SESSION_ID_LENGTH = 32

def generate_session_id() -> str:
    """Generate a secure random session ID."""
    return secrets.token_urlsafe(SESSION_ID_LENGTH)

def get_client_ip(request: Request) -> str:
    """Extract client IP address from request."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

def authenticate_admin(redis_store: RedisStore, username: str, password: str) -> Optional[AdminUser]:
    """
    Authenticate an admin user.
    
    Args:
        redis_store: RedisStore instance
        username: Admin username
        password: Plain text password
        
    Returns:
        AdminUser if authentication succeeds, None otherwise
    """
    admin_data = redis_store.get_admin_user(username)
    if not admin_data:
        return None
    
    # Check if user is active
    if not admin_data.get("is_active", True):
        logger.warning(f"Login attempt for inactive admin user: {username}")
        return None
    
    # Verify password
    if not verify_password(password, admin_data.get("password_hash", "")):
        logger.warning(f"Invalid password for admin user: {username}")
        return None
    
    # Update last login
    admin_data["last_login"] = datetime.now().isoformat()
    redis_store.store_admin_user(username, admin_data)
    
    return AdminUser(**admin_data)

def create_admin_session(
    redis_store: RedisStore,
    username: str,
    role: str,
    ip_address: Optional[str] = None
) -> str:
    """
    Create a new admin session.
    
    Args:
        redis_store: RedisStore instance
        username: Admin username
        role: Admin role
        ip_address: Optional client IP address
        
    Returns:
        Session ID
    """
    session_id = generate_session_id()
    now = datetime.now()
    expires_at = now + timedelta(seconds=SESSION_EXPIRATION_SECONDS)
    
    session_data = {
        "session_id": session_id,
        "username": username,
        "role": role,
        "created_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
        "ip_address": ip_address
    }
    
    redis_store.store_admin_session(session_id, session_data, SESSION_EXPIRATION_SECONDS)
    logger.info(f"Created admin session for {username} (role: {role})")
    
    return session_id

def get_session(redis_store: RedisStore, session_id: str) -> Optional[AdminSession]:
    """
    Retrieve and validate an admin session.
    
    Args:
        redis_store: RedisStore instance
        session_id: Session ID
        
    Returns:
        AdminSession if valid, None otherwise
    """
    session_data = redis_store.get_admin_session(session_id)
    if not session_data:
        return None
    
    # Check expiration
    expires_at = datetime.fromisoformat(session_data["expires_at"])
    if datetime.now() > expires_at:
        redis_store.delete_admin_session(session_id)
        return None
    
    return AdminSession(**session_data)

def require_role(required_role: str, allowed_roles: Optional[list[str]] = None, get_session_func=None):
    """
    Dependency function to require specific admin role.
    
    Args:
        required_role: Minimum required role (viewer < admin < super_admin)
        allowed_roles: Optional list of allowed roles (overrides hierarchy)
        get_session_func: Function to get the session (will be injected by FastAPI)
        
    Returns:
        Dependency function for FastAPI
    """
    role_hierarchy = {"viewer": 1, "admin": 2, "super_admin": 3}
    
    async def check_role(session: Optional[AdminSession] = Depends(get_session_func) if get_session_func else None):
        if not session:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        if allowed_roles:
            if session.role not in allowed_roles:
                raise HTTPException(status_code=403, detail=f"Role '{session.role}' not authorized")
        else:
            user_level = role_hierarchy.get(session.role, 0)
            required_level = role_hierarchy.get(required_role, 999)
            if user_level < required_level:
                raise HTTPException(
                    status_code=403,
                    detail=f"Role '{session.role}' does not have permission. Required: '{required_role}'"
                )
        
        return session
    
    return check_role

def log_admin_action(
    redis_store: RedisStore,
    username: str,
    action: str,
    resource: Optional[str] = None,
    details: Optional[dict] = None,
    ip_address: Optional[str] = None
) -> None:
    """
    Log an admin action for audit purposes.
    
    Args:
        redis_store: RedisStore instance
        username: Admin username
        action: Action performed (e.g., "user_deleted", "config_updated")
        resource: Resource affected (e.g., "user:abc123")
        details: Optional additional details
        ip_address: Optional client IP address
    """
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "username": username,
        "action": action,
        "resource": resource,
        "details": details or {},
        "ip_address": ip_address
    }
    
    redis_store.store_audit_log(log_entry)
    logger.info(f"Admin action: {username} - {action} - {resource}")

def initialize_default_admin(redis_store: RedisStore, username: str = "admin", password: str = "admin") -> bool:
    """
    Initialize default admin user if no admins exist.
    
    Args:
        redis_store: RedisStore instance
        username: Default admin username
        password: Default admin password
        
    Returns:
        True if admin was created, False if admins already exist
    """
    existing_admins = redis_store.get_all_admin_users()
    if existing_admins:
        logger.info(f"Admin users already exist ({len(existing_admins)}). Skipping default admin creation.")
        return False
    
    admin_user = {
        "username": username,
        "password_hash": hash_password(password),
        "role": "super_admin",
        "created_at": datetime.now().isoformat(),
        "last_login": None,
        "is_active": True
    }
    
    redis_store.store_admin_user(username, admin_user)
    logger.warning(f"Created default admin user: {username} (password: {password})")
    logger.warning("⚠️  IMPORTANT: Change the default admin password immediately!")
    
    return True
