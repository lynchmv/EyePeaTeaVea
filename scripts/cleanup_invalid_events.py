#!/usr/bin/env python3
"""
Cleanup script to remove invalid events from Redis.

This specifically targets events with expiration dates
set absurdly far in the future (e.g.,> 30 days) which were
introduced by aggressive dateparser settings.
"""

import sys
import os
import json
from datetime import datetime

# Adjust path so we can import src modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.redis_store import RedisStore
from dotenv import load_dotenv

load_dotenv()
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

def cleanup():
    store = RedisStore(REDIS_URL)
    
    if not store.is_connected():
        print(f"Failed to connect to Redis at {REDIS_URL}")
        return
        
    client = store.redis_client
    
    count_scanned = 0
    count_deleted = 0
    
    # 30 days in seconds (threshold for absurd TTL on events)
    MAX_TTL_SECONDS = 30 * 24 * 60 * 60
    
    print("Scanning events in Redis...")
    for key_bytes in client.scan_iter(match="channel:*"):
        count_scanned += 1
        key = key_bytes.decode('utf-8')
        
        # Valid channels that never expire have a TTL of -1.
        # Legitimate events have an expiration of ~4 hours.
        # Any event with an expiration > 30 days is extremely likely a bug.
        ttl = client.ttl(key)
        
        if ttl > MAX_TTL_SECONDS:
            client.delete(key)
            count_deleted += 1
            
    print(f"Cleanup complete.")
    print(f"Scanned {count_scanned} channel entries.")
    print(f"Deleted {count_deleted} invalid future entries.")

if __name__ == "__main__":
    cleanup()
