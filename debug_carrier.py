import os
import sys
import django
from django.conf import settings

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'autodialer.settings')
django.setup()

from telephony.models import PsEndpoint, Phone, Carrier

print("Checking configurations for 'openvox'...")

carrier_exists = Carrier.objects.filter(name='openvox').exists()
print(f"Carrier 'openvox' exists: {carrier_exists}")

phone_exists = Phone.objects.filter(extension='openvox').exists()
print(f"Phone 'openvox' exists: {phone_exists}")

endpoints = list(PsEndpoint.objects.filter(id='openvox').values())
if endpoints:
    print(f"PsEndpoint 'openvox' configuration:")
    ep = endpoints[0]
    for key, value in ep.items():
        print(f"  {key}: {value}")
else:
    print("PsEndpoint 'openvox' does NOT exist.")
