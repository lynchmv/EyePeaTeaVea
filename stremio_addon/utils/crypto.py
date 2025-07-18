import hashlib

def get_text_hash(text: str) -> str:
    """
    Generates a SHA256 hash for the given text and returns the first 10 characters.
    """
    if not text:
        return ""
    sha256_hash = hashlib.sha256(text.encode('utf-8')).hexdigest()
    return sha256_hash[:10]

