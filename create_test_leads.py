#!/usr/bin/env python
"""
Create test leads for local testing with extension 1002
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'autodialer.settings')
django.setup()

from leads.models import Lead, LeadList
from django.contrib.auth.models import User

def create_test_leads():
    # Get or create a test lead list
    lead_list, created = LeadList.objects.get_or_create(
        name='Test Leads - Extension 1002',
        defaults={
            'description': 'Test leads for local predictive dialer testing',
            'created_by': User.objects.filter(is_superuser=True).first()
        }
    )
    
    if created:
        print(f"Created new lead list: {lead_list.name}")
    else:
        print(f"Using existing lead list: {lead_list.name}")
        # Clear existing leads in this list
        deleted_count = Lead.objects.filter(lead_list=lead_list).delete()[0]
        print(f"Deleted {deleted_count} existing leads")
    
    # Create 500 test leads
    print("Creating 500 test leads with phone number 1002...")
    
    leads_to_create = []
    for i in range(1, 501):
        lead = Lead(
            lead_list=lead_list,
            phone_number='1002',
            first_name=f'Test',
            last_name=f'Customer {i}',
            status='new',
            call_count=0
        )
        leads_to_create.append(lead)
    
    # Bulk create for efficiency
    Lead.objects.bulk_create(leads_to_create)
    
    print(f"✅ Successfully created 500 test leads!")
    print(f"Lead List ID: {lead_list.id}")
    print(f"Lead List Name: {lead_list.name}")
    print(f"\nNext steps:")
    print(f"1. Assign this lead list (ID: {lead_list.id}) to your campaign")
    print(f"2. Make sure your campaign is active")
    print(f"3. Register softphone on extension 1002")
    print(f"4. Login as agent with extension 100 and set status to 'Available'")
    print(f"5. The dialer will start calling 1002!")

if __name__ == '__main__':
    create_test_leads()
