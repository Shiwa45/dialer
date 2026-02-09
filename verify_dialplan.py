import os
import django
from django.db.models import Count

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'autodialer.settings')
django.setup()

from telephony.models import Carrier, DialplanContext, DialplanExtension

def verify_dialplan():
    print("Triggering dialplan regeneration by saving a carrier...")
    c = Carrier.objects.first()
    if c:
        c.save()
        print(f"Saved carrier: {c.name}")
    else:
        print("No carriers found!")
        return

    print("\nChecking generated dialplan extensions for 'from-campaign':")
    try:
        ctx = DialplanContext.objects.get(name='from-campaign')
        exts = ctx.extensions.all().order_by('extension', 'priority')
        
        if not exts.exists():
             print("No extensions found!")
        
        current_ext = ""
        for ext in exts:
            if ext.extension != current_ext:
                print(f"\nExtension: {ext.extension}")
                current_ext = ext.extension
            
            print(f"  {ext.priority}: {ext.application}({ext.arguments})")
            
    except DialplanContext.DoesNotExist:
        print("Context 'from-campaign' not found.")

if __name__ == "__main__":
    verify_dialplan()
