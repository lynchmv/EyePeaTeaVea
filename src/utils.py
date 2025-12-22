"""
Utility functions for secret generation, hashing, and validation.

This module provides helper functions for:
- Generating secure random strings for user identification
- Hashing secrets for secure storage
- Password hashing and verification
- Validating cron expressions
- Validating URLs
- Validating secret_str format
- Validating timezone names
"""
import secrets
import hashlib
import re
import bcrypt
import pytz
from urllib.parse import urlparse
from apscheduler.triggers.cron import CronTrigger

def generate_secret_str(length: int = 32) -> str:
    """Generates a secure random string to be used as a secret_str."""
    return secrets.token_urlsafe(length)

def hash_secret_str(secret_str: str) -> str:
    """Hashes the secret_str for secure storage or comparison."""
    return hashlib.sha256(secret_str.encode()).hexdigest()

def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt.
    
    Uses bcrypt with automatic salt generation for secure password storage.
    The returned hash includes the salt and can be verified using verify_password().
    
    Args:
        password: Plain text password to hash
        
    Returns:
        Bcrypt hash string (includes salt)
        
    Examples:
        >>> hash = hash_password("mypassword")
        >>> verify_password("mypassword", hash)
        True
        >>> verify_password("wrongpassword", hash)
        False
    """
    if not password:
        raise ValueError("Password cannot be empty")
    # Generate salt and hash password (bcrypt handles salt automatically)
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, password_hash: str) -> bool:
    """
    Verify a password against a bcrypt hash.
    
    Args:
        password: Plain text password to verify
        password_hash: Bcrypt hash string (from hash_password)
        
    Returns:
        True if password matches, False otherwise
        
    Examples:
        >>> hash = hash_password("mypassword")
        >>> verify_password("mypassword", hash)
        True
        >>> verify_password("wrongpassword", hash)
        False
    """
    if not password or not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))
    except (ValueError, TypeError):
        # Handle invalid hash format gracefully
        return False

def validate_cron_expression(cron_str: str) -> str:
    """
    Validates a cron expression string.
    
    Args:
        cron_str: Cron expression in format "minute hour day month day-of-week"
        
    Returns:
        The validated cron expression string
        
    Raises:
        ValueError: If the cron expression is invalid
        
    Examples:
        Valid: "0 */6 * * *" (every 6 hours)
        Valid: "0 0 * * *" (daily at midnight)
        Invalid: "0 0" (too few fields)
        Invalid: "0 0 * * * *" (too many fields)
    """
    if not cron_str or not cron_str.strip():
        raise ValueError("Cron expression cannot be empty")
    
    cron_str = cron_str.strip()
    parts = cron_str.split()
    
    if len(parts) != 5:
        raise ValueError(
            f"Invalid cron expression format. Expected 5 fields (minute hour day month day-of-week), "
            f"got {len(parts)}. Example: '0 */6 * * *' (every 6 hours)"
        )
    
    minute, hour, day, month, day_of_week = parts
    
    # Try to create a CronTrigger to validate the expression
    # This will raise ValueError if any field is invalid
    try:
        CronTrigger(minute=minute, hour=hour, day=day, month=month, day_of_week=day_of_week)
    except ValueError as e:
        raise ValueError(f"Invalid cron expression '{cron_str}': {e}")
    
    return cron_str

def validate_url(url: str) -> str:
    """
    Validates that a string is a valid URL.
    
    Args:
        url: URL string to validate
        
    Returns:
        The validated URL string (normalized)
        
    Raises:
        ValueError: If the URL is invalid
        
    Examples:
        Valid: "http://example.com/playlist.m3u"
        Valid: "https://example.com/playlist.m3u"
        Valid: "file:///path/to/playlist.m3u" (for local files)
        Invalid: "not-a-url"
        Invalid: "ftp://example.com" (unsupported protocol)
    """
    if not url or not url.strip():
        raise ValueError("URL cannot be empty")
    
    url = url.strip()
    
    # Parse the URL
    parsed = urlparse(url)
    
    # Check if it's a valid URL structure
    if not parsed.scheme:
        raise ValueError(f"Invalid URL '{url}': missing scheme (http://, https://, or file://)")
    
    # Allow http, https, and file protocols
    allowed_schemes = ['http', 'https', 'file']
    if parsed.scheme.lower() not in allowed_schemes:
        raise ValueError(
            f"Invalid URL '{url}': unsupported scheme '{parsed.scheme}'. "
            f"Supported schemes: {', '.join(allowed_schemes)}"
        )
    
    # For http/https, require netloc (domain)
    if parsed.scheme.lower() in ['http', 'https']:
        if not parsed.netloc:
            raise ValueError(f"Invalid URL '{url}': missing domain")
    
    # For file://, require a path
    if parsed.scheme.lower() == 'file':
        if not parsed.path:
            raise ValueError(f"Invalid URL '{url}': missing file path")
    
    return url

def validate_timezone(timezone_str: str) -> str:
    """
    Validates an IANA timezone name.
    
    Args:
        timezone_str: IANA timezone name (e.g., "America/New_York", "Europe/London", "UTC")
        
    Returns:
        The validated timezone string
        
    Raises:
        ValueError: If the timezone is invalid
        
    Examples:
        Valid: "America/New_York"
        Valid: "Europe/London"
        Valid: "UTC"
        Invalid: "Invalid/Timezone"
    """
    if not timezone_str or not timezone_str.strip():
        raise ValueError("Timezone cannot be empty")
    
    timezone_str = timezone_str.strip()
    
    # Check if it's a valid IANA timezone
    try:
        pytz.timezone(timezone_str)
        return timezone_str
    except pytz.exceptions.UnknownTimeZoneError:
        raise ValueError(f"Invalid timezone: {timezone_str}. Must be a valid IANA timezone name (e.g., 'America/New_York', 'Europe/London', 'UTC')")

def validate_secret_str(secret_str: str) -> str:
    """
    Validates a secret_str parameter.
    
    Validates that the secret_str has reasonable length and contains only
    safe characters (alphanumeric, hyphens, underscores).
    
    Args:
        secret_str: Secret string to validate
        
    Returns:
        The validated secret_str (stripped)
        
    Raises:
        ValueError: If the secret_str is invalid
        
    Examples:
        Valid: "abc123xyz"
        Valid: "a1b2c3-d4e5_f6"
        Invalid: "" (empty)
        Invalid: "a" (too short)
        Invalid: "a" * 200 (too long)
        Invalid: "abc!@#" (invalid characters)
    """
    if not secret_str:
        raise ValueError("secret_str cannot be empty")
    
    secret_str = secret_str.strip()
    
    # Validate length (reasonable bounds)
    MIN_LENGTH = 8
    MAX_LENGTH = 256
    
    if len(secret_str) < MIN_LENGTH:
        raise ValueError(f"secret_str must be at least {MIN_LENGTH} characters long")
    
    if len(secret_str) > MAX_LENGTH:
        raise ValueError(f"secret_str must be at most {MAX_LENGTH} characters long")
    
    # Validate characters (alphanumeric, hyphens, underscores, dots)
    # This matches the format generated by secrets.token_urlsafe()
    if not re.match(r'^[A-Za-z0-9._-]+$', secret_str):
        raise ValueError("secret_str contains invalid characters. Only alphanumeric, dots, hyphens, and underscores are allowed")
    
    return secret_str
