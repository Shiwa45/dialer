import os
import django
import sys

sys.path.append('/home/shiwansh/dialer')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'autodialer.settings')
django.setup()

from django.contrib.auth.models import User
from telephony.models import Phone, PsAuth, PsEndpoint

print("--- Inspecting Phone & SIP Auth ---")

# Get first user/agent
user = User.objects.first() # Or specific user if known
print(f"User: {user.username}")

phones = Phone.objects.filter(user=user)
if not phones.exists():
    print("No phone assigned to this user.")
    # check all phones
    phones = Phone.objects.all()
    print(f"Showing all {phones.count()} phones:")

for phone in phones:
    print(f"\nPhone Extension: {phone.extension}")
    print(f"  Secret: {phone.secret}")
    print(f"  WebRTC Enabled: {phone.webrtc_enabled}")
    
    # Check PsAuth (PJSIP)
    try:
        auth = PsAuth.objects.get(id=phone.extension)
        print(f"  PsAuth Password: {auth.password}")
        print(f"  PsAuth Username: {auth.username}")
        if auth.password != phone.secret:
            print("  ⚠️ MISMATCH: Phone secret != PsAuth password")
    except PsAuth.DoesNotExist:
        print("  ⚠️ PsAuth record MISSING")

    # Check PsEndpoint
    try:
        endpoint = PsEndpoint.objects.get(id=phone.extension)
        print(f"  PsEndpoint Transport: {endpoint.transport}")
        print(f"  PsEndpoint WebRTC: {getattr(endpoint, 'webrtc', 'N/A')}") # 'webrtc' field might not exist in Django model if not defined? 
        # In models.py PsEndpoint does NOT have 'webrtc' field defined in Django class!
        # checking models.py content again...
    except PsEndpoint.DoesNotExist:
        print("  ⚠️ PsEndpoint record MISSING")
