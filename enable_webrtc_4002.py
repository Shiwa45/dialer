import os
import django
import sys

sys.path.append('/home/shiwansh/dialer')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'autodialer.settings')
django.setup()

from telephony.models import Phone, PsEndpoint

try:
    phone = Phone.objects.get(extension='4002')
    print(f"Current WebRTC status: {phone.webrtc_enabled}")
    
    phone.webrtc_enabled = True
    phone.save() # This triggers sync_to_asterisk
    
    print(f"New WebRTC status: {phone.webrtc_enabled}")
    
    # Verify PsEndpoint update
    ep = PsEndpoint.objects.get(id='4002')
    print(f"PsEndpoint Transport: {ep.transport}")
    
except Phone.DoesNotExist:
    print("Phone 4002 not found!")
except Exception as e:
    print(f"Error: {e}")
