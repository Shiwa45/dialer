import os
import django
import sys

sys.path.append('/home/shiwansh/dialer')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'autodialer.settings')
django.setup()

from telephony.models import Phone, PsEndpoint

try:
    phone = Phone.objects.get(extension='1001')
    print(f"Resyncing phone {phone.extension}...")
    
    # Force save to trigger sync_to_asterisk
    phone.save() 
    
    # Verify PsEndpoint update
    ep = PsEndpoint.objects.get(id='1001')
    print(f"✅ Sync Complete")
    print(f"  Transport: {ep.transport}")
    print(f"  Media Encryption: {ep.media_encryption}")
    print(f"  AVPF: {ep.use_avpf}")
    print(f"  ICE Support: {ep.ice_support}")
    print(f"  DTLS Verify: {ep.dtls_verify}")
    print(f"  WebRTC: {ep.webrtc}")
    
except Phone.DoesNotExist:
    print("Phone 1001 not found!")
except Exception as e:
    print(f"Error: {e}")
