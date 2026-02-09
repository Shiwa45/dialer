import os
import django
from django.db.models import Count

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'autodialer.settings')
django.setup()

from campaigns.models import Disposition
from leads.models import Lead, LeadList
from calls.models import CallLog

import sys

def fix_dispositions():
    print("Fixing Dispositions...", flush=True)
    updates = {
        'BUSY': 'busy',
        'NO_ANSWER': 'no_answer',
        'CALLBACK': 'callback',
        'SALE': 'sale',
        'DNC': 'dnc',
        'NOT_INTERESTED': 'not_interested',
        'WRONG_NUMBER': 'wrong_number',
        'ANSWERING_MACHINE': 'answering_machine'
    }
    
    for code, category in updates.items():
        count = Disposition.objects.filter(code=code).update(category=category)
        if count:
            print(f"  Updated {code} -> {category}")

def restore_lead_statuses(list_name_fragment=None):
    if list_name_fragment:
        print(f"\nRestoring lead statuses for lists matching '{list_name_fragment}'...")
        lists = LeadList.objects.filter(name__icontains=list_name_fragment)
    else:
        print(f"\nRestoring lead statuses for ALL lists...")
        lists = LeadList.objects.all()
    
    for l in lists:
        print(f"Processing list: {l.name} (ID: {l.id})")
        
        # Get contacted leads that might be mislabeled
        leads = l.leads.filter(status='contacted')
        total = leads.count()
        if total == 0:
            print(f"  No 'contacted' leads found in list {l.name}")
            continue

        print(f"  Found {total} 'contacted' leads. Checking call history...")
        
        updated_count = 0
        batch_size = 1000
        
        # Process in batches to avoid memory issues
        for start in range(0, total, batch_size):
            end = start + batch_size
            batch = leads[start:end]
            
            print(f"  Processing batch {start} to {end}...")

            for lead in batch:
                last_call = CallLog.objects.filter(lead=lead).order_by('-start_time').first()
                
                if last_call:
                    if last_call.disposition:
                        category = last_call.disposition.category
                        # print(f"    Lead {lead.id}: Last call disposition category: {category}")
                        
                        if category in ['busy', 'no_answer', 'callback', 'sale', 'dnc', 'not_interested', 'wrong_number', 'answering_machine']:
                            if lead.status != category:
                                print(f"    Updating lead {lead.id} status: {lead.status} -> {category}")
                                lead.status = category
                                lead.save(update_fields=['status'])
                                updated_count += 1
                    else:
                        pass
                        # print(f"    Lead {lead.id}: Last call has no disposition")
                else:
                    pass
                    # print(f"    Lead {lead.id}: No call logs found")
            
            print(f"  Processed {min(end, total)}/{total} leads...")
            
        print(f"  Updated {updated_count} leads in list {l.name}")

if __name__ == '__main__':
    fix_dispositions()
    restore_lead_statuses()
