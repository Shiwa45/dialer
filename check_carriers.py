import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'autodialer.settings')
django.setup()

from telephony.models import Carrier, DialplanExtension, DialplanContext

def check_carriers():
    print("Carriers:")
    for c in Carrier.objects.all():
        print(f"  ID: {c.id} | Name: {c.name} | Prefix: {c.dial_prefix} | Active: {c.is_active}")

    print("\nDialplan Extensions for 'from-campaign':")
    try:
        ctx = DialplanContext.objects.get(name='from-campaign')
        for ext in ctx.extensions.all().order_by('extension', 'priority'):
            print(f"  Ext: {ext.extension} | Prio: {ext.priority} | App: {ext.application} | Data: {ext.arguments}")
    except DialplanContext.DoesNotExist:
        print("  Context 'from-campaign' not found.")

if __name__ == "__main__":
    check_carriers()
