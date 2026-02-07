#!/usr/bin/env python
"""
Clear Redis hopper cache to force refresh with new dial settings
"""
import redis

# Connect to Redis
r = redis.Redis(host='127.0.0.1', port=6379, db=0, decode_responses=True)

# Clear all campaign hoppers
keys_to_delete = []
for key in r.scan_iter("campaign:*"):
    keys_to_delete.append(key)

if keys_to_delete:
    deleted = r.delete(*keys_to_delete)
    print(f"✅ Cleared {deleted} Redis keys")
    print("Cleared keys:")
    for key in keys_to_delete[:10]:  # Show first 10
        print(f"  - {key}")
    if len(keys_to_delete) > 10:
        print(f"  ... and {len(keys_to_delete) - 10} more")
else:
    print("No campaign keys found in Redis")

print("\n✅ Redis hopper cache cleared. Restart autodialer to refill with correct numbers.")
