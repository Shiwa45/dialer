import os
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'autodialer.settings')
django.setup()

from telephony.models import Phone

def disable_all_webrtc():
    print("Disabling WebRTC for all phones...")
    phones = Phone.objects.filter(webrtc_enabled=True)
    count = phones.count()
    
    if count == 0:
        print("No phones have WebRTC enabled.")
        return

    print(f"Found {count} phones with WebRTC enabled. Updating...")
    
    # Update loop to trigger save() signal if needed for Asterisk sync
    # Although bulk update is faster, save() ensures sync logic in model runs
    updated = 0
    for phone in phones:
        phone.webrtc_enabled = False
        phone.save()
        print(f"  Disabled WebRTC for extension {phone.extension}")
        updated += 1
        
    print(f"Successfully disabled WebRTC for {updated} phones.")

if __name__ == '__main__':
    disable_all_webrtc()
