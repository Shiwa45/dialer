import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'autodialer.settings')
django.setup()

from telephony.dialplan_service import DialplanService
from telephony.models import DialplanContext, DialplanExtension

def verify_direct():
    print("Calling DialplanService.regenerate_dialplan() directly...")
    try:
        DialplanService.regenerate_dialplan()
        print("Regeneration complete.")
    except Exception as e:
        print(f"Error during regeneration: {e}")
        return

    print("\nChecking generated dialplan extensions for 'from-campaign':")
    try:
        ctx = DialplanContext.objects.get(name='from-campaign')
        exts = ctx.extensions.all().order_by('extension', 'priority')
        
        current_ext = ""
        for ext in exts:
            if ext.extension != current_ext:
                print(f"\nExtension: {ext.extension}")
                current_ext = ext.extension
            
            print(f"  {ext.priority}: {ext.application}({ext.arguments})")
            
    except DialplanContext.DoesNotExist:
        print("Context 'from-campaign' not found.")

if __name__ == "__main__":
    verify_direct()
