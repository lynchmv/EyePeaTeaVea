import secrets
import hashlib
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
