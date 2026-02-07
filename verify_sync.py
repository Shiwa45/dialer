import os
import django
import sys
import logging

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "autodialer.settings")
django.setup()

from telephony.recording_service import RecordingService
from calls.models import CallLog
from telephony.models import Recording

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def verify_recordings():
    print("Checking recording permissions...")
    path = '/var/spool/asterisk/monitor'
    if os.access(path, os.R_OK):
        print(f"✅ Can read {path}")
    else:
        print(f"❌ Cannot read {path}")

    print("\nSyncing recordings...")
    service = RecordingService()
    count = service.sync_recordings()
    print(f"Synced {count} recordings")

    print("\nChecking recent calls for recordings:")
    recent_calls = CallLog.objects.order_by('-start_time')[:5]
    for call in recent_calls:
        print(f"Call {call.id} ({call.start_time}): Filename={call.recording_filename}")
        rec = Recording.objects.filter(call_log=call).first()
        if rec:
            print(f"  -> Found Recording entry: {rec.filename} (Path: {rec.file_path}, Size: {rec.file_size})")
        else:
            print(f"  -> NO Recording entry found")

if __name__ == "__main__":
    verify_recordings()
