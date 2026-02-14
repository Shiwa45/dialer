import os
import django
import sys

sys.path.append('/home/shiwansh/dialer')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'autodialer.settings')
django.setup()

from telephony.models import Phone, PsAuth, PsEndpoint

ext = '1001'
print(f"--- Inspecting Extension {ext} ---")

try:
    phone = Phone.objects.get(extension=ext)
    print(f"Phone Model:")
    print(f"  User: {phone.user.username if phone.user else 'None'}")
    print(f"  Secret: {phone.secret}")
    print(f"  WebRTC Enabled: {phone.webrtc_enabled}")
    
    # Check PsAuth
    try:
        auth = PsAuth.objects.get(id=ext)
        print(f"PsAuth Table:")
        print(f"  Username: {auth.username}")
        print(f"  Password: {auth.password}")
        
        if auth.password != phone.secret:
            print("  ❌ MISMATCH: Phone secret != PsAuth password")
        else:
            print("  ✅ Passwords match")
            
        if auth.username != ext:
            print(f"  ❌ Username mismatch: PsAuth has {auth.username}")
            
    except PsAuth.DoesNotExist:
        print("  ❌ PsAuth record MISSING")

    # Check PsEndpoint
    try:
        ep = PsEndpoint.objects.get(id=ext)
        print(f"PsEndpoint Table:")
        print(f"  Transport: {ep.transport}")
        
        expected_transport = 'transport-wss' if phone.webrtc_enabled else 'transport-udp'
        if ep.transport != expected_transport:
            print(f"  ❌ Transport mismatch: Expected {expected_transport}, got {ep.transport}")
        else:
            print("  ✅ Transport correct")
            
    except PsEndpoint.DoesNotExist:
        print("  ❌ PsEndpoint record MISSING")

except Phone.DoesNotExist:
    print(f"❌ Phone {ext} does not exist in Django DB")
