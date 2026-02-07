#!/usr/bin/env python
"""
Force remove dial prefix from ALL campaigns and verify
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'autodialer.settings')
django.setup()

from campaigns.models import Campaign
from django.db import connection

# Check current state
print("=" * 60)
print("BEFORE FIX:")
print("=" * 60)
campaigns = Campaign.objects.all()
for c in campaigns:
    print(f"Campaign: {c.name} (ID: {c.id})")
    print(f"  dial_prefix: '{c.dial_prefix}'")
    print()

# Force update ALL campaigns to remove dial prefix
print("=" * 60)
print("FIXING ALL CAMPAIGNS:")
print("=" * 60)
updated = Campaign.objects.all().update(dial_prefix='')
print(f"Updated {updated} campaigns")
print()

# Verify with raw SQL
print("=" * 60)
print("VERIFICATION (Raw SQL):")
print("=" * 60)
with connection.cursor() as cursor:
    cursor.execute("SELECT id, name, dial_prefix FROM campaigns_campaign")
    rows = cursor.fetchall()
    for row in rows:
        print(f"ID: {row[0]}, Name: {row[1]}, Prefix: '{row[2]}'")

print()
print("✅ All campaigns updated. Dial prefix removed from database.")
