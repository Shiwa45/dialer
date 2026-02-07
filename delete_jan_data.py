#!/usr/bin/env python
"""
Delete the Jan_data lead list and all associated leads
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'autodialer.settings')
django.setup()

from leads.models import Lead, LeadList

def delete_jan_data():
    try:
        # Find the Jan_data lead list
        lead_list = LeadList.objects.get(name='Jan_data')
        
        # Count leads before deletion
        lead_count = Lead.objects.filter(lead_list=lead_list).count()
        
        print(f"Found lead list: {lead_list.name} (ID: {lead_list.id})")
        print(f"Total leads in this list: {lead_count}")
        
        # Delete all leads in this list
        deleted_leads = Lead.objects.filter(lead_list=lead_list).delete()[0]
        print(f"Deleted {deleted_leads} leads")
        
        # Delete the lead list itself
        lead_list.delete()
        print(f"✅ Successfully deleted lead list 'Jan_data'")
        
    except LeadList.DoesNotExist:
        print("❌ Lead list 'Jan_data' not found")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == '__main__':
    delete_jan_data()
