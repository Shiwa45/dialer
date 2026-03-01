from django.core.management.base import BaseCommand
from telephony.models import Phone

class Command(BaseCommand):
    help = 'Enable WebRTC and Opus codec for all extensions'

    def handle(self, *args, **kwargs):
        phones = Phone.objects.all()
        count = 0
        updated_count = 0
        
        self.stdout.write(f"Found {phones.count()} phones. Starting update...")

        for phone in phones:
            changed = False
            # Enable WebRTC
            if not phone.webrtc_enabled:
                phone.webrtc_enabled = True
                changed = True
                self.stdout.write(f"  - Enabling WebRTC for {phone.extension}")
            
            # Add Opus codec if missing
            current_codecs = [c.strip() for c in phone.codec.split(',')]
            if 'opus' not in current_codecs:
                # Add opus to the beginning of the list
                current_codecs.insert(0, 'opus')
                phone.codec = ','.join(current_codecs)
                changed = True
                self.stdout.write(f"  - Adding Opus codec for {phone.extension}")
            
            # Force save to trigger sync_to_asterisk even if no model fields changed
            # This ensures the asterisk realtime tables are updated with new generation logic
            try:
                phone.save()
                if changed:
                    updated_count += 1
                count += 1
                self.stdout.write(self.style.SUCCESS(f"  ✓ Synced {phone.extension}"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  ✗ Failed to sync {phone.extension}: {e}"))

        self.stdout.write(self.style.SUCCESS(f'Successfully processed {count} extensions. Updated {updated_count} records.'))
