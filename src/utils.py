"""
Utility functions for secret generation, hashing, and validation.

This module provides helper functions for:
- Generating secure random strings for user identification
- Hashing secrets for secure storage
- Validating cron expressions
- Validating URLs
"""
import secrets
import hashlib
from urllib.parse import urlparse
from apscheduler.triggers.cron import CronTrigger

def generate_secret_str(length: int = 32) -> str:
    """Generates a secure random string to be used as a secret_str."""
    return secrets.token_urlsafe(length)

def hash_secret_str(secret_str: str) -> str:
    """Hashes the secret_str for secure storage or comparison."""
    return hashlib.sha256(secret_str.encode()).hexdigest()

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
