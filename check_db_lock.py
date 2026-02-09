import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'autodialer.settings')
django.setup()

from telephony.models import Carrier, DialplanExtension

def check_db_read():
    print("Reading Carriers...")
    print(f"Count: {Carrier.objects.count()}")
    
    print("Reading DialplanExtensions...")
    print(f"Count: {DialplanExtension.objects.count()}")

if __name__ == "__main__":
    check_db_read()
