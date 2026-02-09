import os
import django
import sys
from django.db.models import Count

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'autodialer.settings')
django.setup()

from leads.models import LeadList

def check_leads(name_filter=None):
    if name_filter:
        lists = LeadList.objects.filter(name__icontains=name_filter)
        print(f"Found {lists.count()} lists matching '{name_filter}':")
    else:
        lists = LeadList.objects.all()
        print(f"Found {lists.count()} total lists:")

    print("")

    for l in lists:
        print(f"ID: {l.id} | Name: {l.name}")
        print("-" * 30)
        
        stats = l.leads.values('status').annotate(count=Count('id'))
        total = 0
        for s in stats:
            print(f"  {s['status']}: {s['count']}")
            total += s['count']
            
        print(f"  Total: {total}")
        print("")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Join arguments in case list name has spaces
        filter_val = " ".join(sys.argv[1:])
        check_leads(filter_val)
    else:
        check_leads()
