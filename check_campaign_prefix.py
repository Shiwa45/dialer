#!/usr/bin/env python
"""
Check and fix campaign dial prefix
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'autodialer.settings')
django.setup()

from campaigns.models import Campaign

# Check all campaigns
campaigns = Campaign.objects.all()
print("Current Campaign Settings:")
print("-" * 50)
for c in campaigns:
    print(f"Campaign: {c.name}")
    print(f"  ID: {c.id}")
    print(f"  Dial Prefix: [{c.dial_prefix}]")
    print(f"  Status: {c.status}")
    print()

# Fix Demo Campaign
demo = Campaign.objects.filter(name__icontains='demo').first()
if demo:
    if demo.dial_prefix:
        print(f"⚠️  Demo Campaign STILL has prefix: '{demo.dial_prefix}'")
        print("Removing it now...")
        demo.dial_prefix = ''
        demo.save()
        print("✅ Prefix removed!")
    else:
        print("✅ Demo Campaign has no prefix (correct)")
