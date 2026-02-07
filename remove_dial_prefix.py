#!/usr/bin/env python
"""
Remove dial prefix from Demo Campaign for local testing
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'autodialer.settings')
django.setup()

from campaigns.models import Campaign

def remove_dial_prefix():
    try:
        # Find Demo Campaign
        campaign = Campaign.objects.filter(name__icontains='demo').first()
        
        if not campaign:
            print("❌ Demo Campaign not found")
            print("Available campaigns:")
            for c in Campaign.objects.all():
                print(f"  - {c.name} (ID: {c.id}, Prefix: '{c.dial_prefix}')")
            return
        
        print(f"Found campaign: {campaign.name} (ID: {campaign.id})")
        print(f"Current dial prefix: '{campaign.dial_prefix}'")
        
        # Remove dial prefix
        campaign.dial_prefix = ''
        campaign.save(update_fields=['dial_prefix'])
        
        print(f"✅ Successfully removed dial prefix from {campaign.name}")
        print(f"Campaign will now dial numbers directly (e.g., 1002 instead of 91191002)")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == '__main__':
    remove_dial_prefix()
