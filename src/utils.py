import secrets
import hashlib

def generate_secret_str(length: int = 32) -> str:
    """Generates a secure random string to be used as a secret_str."""
    return secrets.token_urlsafe(length)

def hash_secret_str(secret_str: str) -> str:
    """Hashes the secret_str for secure storage or comparison."""
    return hashlib.sha256(secret_str.encode()).hexdigest()
