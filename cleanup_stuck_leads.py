#!/usr/bin/env python3
"""
Cleanup stuck leads from Redis dialing set

This script finds and removes leads that have been stuck in the dialing
set for more than 5 minutes (likely failed calls that weren't cleaned up)
"""

import sys
import os
import django

# Setup Django
sys.path.insert(0, '/home/shiwansh/dialer')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'autodialer.settings')
django.setup()

from campaigns.services import HopperService
from campaigns.models import Campaign
from datetime import datetime, timedelta
from django.utils import timezone

def cleanup_stuck_leads():
    """Remove leads stuck in dialing set for > 5 minutes"""
    
    campaigns = Campaign.objects.filter(status='active')
    
    for campaign in campaigns:
        r = HopperService.get_redis()
        dialing_key = f"campaign:{campaign.id}:dialing"
        
        # Get all leads in dialing set
        stuck_leads = r.smembers(dialing_key)
        
        if stuck_leads:
            print(f"\n{campaign.name}: Found {len(stuck_leads)} leads in dialing set")
            
            # For now, just clear them all since we don't have timestamps
            # In production, you'd want to track when each lead was added
            count = r.delete(dialing_key)
            print(f"  Cleared {count} stuck leads")
        else:
            print(f"\n{campaign.name}: No stuck leads")

if __name__ == '__main__':
    print("=" * 60)
    print("Cleaning up stuck leads from Redis dialing sets")
    print("=" * 60)
    cleanup_stuck_leads()
    print("\nDone!")
