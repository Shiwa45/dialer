"""
Call Recording Service - Phase 2.5

This module handles:
1. Recording file path management
2. Recording creation during calls
3. Recording playback and download
4. Recording cleanup

Add these to your telephony/services.py or create a new file.
"""

import os
import logging
from datetime import datetime, timedelta
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


class RecordingService:
    """
    Service for managing call recordings
    
    PHASE 2.5: Call recordings integration
    """
    
    # Default recording path (can be overridden in settings)
    DEFAULT_RECORDING_PATH = '/var/spool/asterisk/monitor'
    
    def __init__(self):
        self.recording_path = getattr(
            settings, 
            'CALL_RECORDING_PATH', 
            self.DEFAULT_RECORDING_PATH
        )
    
    def get_recording_filename(self, call_log):
        """
        Generate a unique recording filename
        
        Format: {campaign_id}_{lead_id}_{agent_id}_{timestamp}.wav
        
        Args:
            call_log: CallLog instance
        
        Returns:
            str: Filename without path
        """
        timestamp = timezone.now().strftime('%Y%m%d%H%M%S')
        
        parts = [
            str(call_log.campaign_id) if call_log.campaign_id else '0',
            str(call_log.lead_id) if call_log.lead_id else '0',
            str(call_log.agent_id) if call_log.agent_id else '0',
            timestamp
        ]
        
        return f"{'_'.join(parts)}.wav"
    
    def get_recording_path(self, filename):
        """
        Get full path for a recording file
        
        Args:
            filename: Recording filename
        
        Returns:
            str: Full path to recording
        """
        # Organize by date for easier management
        date_folder = timezone.now().strftime('%Y/%m/%d')
        full_path = os.path.join(self.recording_path, date_folder)
        
        # Create directory if needed
        os.makedirs(full_path, exist_ok=True)
        
        return os.path.join(full_path, filename)
    
    def create_recording_entry(self, call_log, filename=None, file_path=None):
        """
        Create a Recording model entry for a call
        
        Args:
            call_log: CallLog instance
            filename: Optional filename (will generate if not provided)
            file_path: Optional full path (will generate if not provided)
        
        Returns:
            Recording instance or None
        """
        from telephony.models import Recording
        
        try:
            if not filename:
                filename = self.get_recording_filename(call_log)
            
            if not file_path:
                file_path = self.get_recording_path(filename)
            
            # Create recording entry
            # Use call_log.asterisk_server (which is set on CallLog) instead of campaign.asterisk_server
            recording = Recording.objects.create(
                call_id=str(call_log.id),
                filename=filename,
                file_path=file_path,
                format='wav',
                recording_start=call_log.answer_time or call_log.start_time,
                recording_end=call_log.end_time,
                duration=call_log.talk_duration or 0,
                asterisk_server=call_log.asterisk_server,  # Use CallLog's asterisk_server field
                is_available=False  # Will be set to True when file exists
            )
            
            # Update call log
            call_log.recording_filename = filename
            call_log.save(update_fields=['recording_filename'])
            
            logger.info(f"Created recording entry: {filename} for call {call_log.id}")
            
            return recording
            
        except Exception as e:
            logger.error(f"Error creating recording entry: {e}")
            return None
    
    def check_recording_exists(self, recording):
        """
        Check if recording file exists on disk
        
        Args:
            recording: Recording instance
        
        Returns:
            bool: True if file exists
        """
        if not recording.file_path:
            return False
        
        exists = os.path.exists(recording.file_path)
        
        if exists and not recording.is_available:
            # Update recording status and file size
            recording.is_available = True
            recording.file_size = os.path.getsize(recording.file_path)
            recording.save(update_fields=['is_available', 'file_size'])
        
        return exists
    
    def get_recording_for_call(self, call_id):
        """
        Get recording for a call
        
        Args:
            call_id: CallLog ID
        
        Returns:
            Recording instance or None
        """
        from telephony.models import Recording
        from calls.models import CallLog
        
        # Try to find by call_id
        recording = Recording.objects.filter(call_id=str(call_id)).first()
        
        if recording:
            return recording
        
        # Try to find by call log's recording_file
        call_log = CallLog.objects.filter(id=call_id).first()
        if call_log and call_log.recording_filename:
            recording = Recording.objects.filter(
                filename=call_log.recording_filename
            ).first()
        
        return recording
    
    def find_orphan_recordings(self):
        """
        Find recording files on disk without database entries
        
        Args:
            None
        
        Returns:
            list: List of file paths
        """
        from telephony.models import Recording
        
        orphans = []
        
        # Walk through recording directory
        for root, dirs, files in os.walk(self.recording_path):
            for file in files:
                if file.endswith(('.wav', '.mp3', '.gsm')):
                    full_path = os.path.join(root, file)
                    
                    # Check if entry exists
                    if not Recording.objects.filter(file_path=full_path).exists():
                        orphans.append(full_path)
        
        return orphans
    
    def sync_recordings(self, call_log=None):
        """
        Sync recordings from disk to database
        
        Args:
            call_log: Optional specific call to sync
        """
        from telephony.models import Recording
        from calls.models import CallLog
        
        if call_log:
            # Sync specific call
            self._sync_call_recording(call_log)
            return
        
        # Sync all recordings in the last 24 hours
        cutoff = timezone.now() - timedelta(hours=24)
        
        calls = CallLog.objects.filter(
            start_time__gte=cutoff,
            talk_duration__gt=0
        )
        
        synced = 0
        for call in calls:
            if self._sync_call_recording(call):
                synced += 1
        
        logger.info(f"Synced {synced} recordings")
        return synced
    
    def _sync_call_recording(self, call_log):
        """
        Sync recording for a specific call
        """
        from telephony.models import Recording
        
        # Check if recording entry exists
        existing = Recording.objects.filter(call_id=str(call_log.id)).first()
        
        if existing and existing.is_available:
            return False  # Already synced
        
        # Try to find recording file
        filename = call_log.recording_filename
        if not filename:
            filename = self.get_recording_filename(call_log)
        
        # Search for file
        file_path = self._find_recording_file(filename, call_log)
        
        if file_path and os.path.exists(file_path):
            if existing:
                # Update existing entry
                existing.file_path = file_path
                existing.is_available = True
                existing.file_size = os.path.getsize(file_path)
                existing.save()
            else:
                # Create new entry
                self.create_recording_entry(call_log, filename, file_path)
            
            # Update call log
            call_log.recording_filename = filename
            call_log.save(update_fields=['recording_filename'])
            
            return True
        
        return False
    
    def _find_recording_file(self, filename, call_log):
        """
        Search for recording file in common locations
        """
        # Common filename patterns
        patterns = [
            filename,
            f"{call_log.channel}.wav" if call_log.channel else None,
            f"{call_log.uniqueid}.wav" if call_log.uniqueid else None,
        ]
        
        # Add the actual Asterisk filename format from dialplan:
        # out-YYYYMMDD-HHMMSS-CAMPAIGN_ID-LEAD_ID-PHONE
        # Note: Dialplan uses ${EXTEN} which may include carrier prefix (e.g., 9119)
        # Also note: Timestamp may differ due to timezone, so we'll use glob patterns
        if call_log.start_time and call_log.campaign_id and call_log.lead_id:
            phone_number = call_log.lead.phone_number if call_log.lead else 'unknown'
            date_str = call_log.start_time.strftime('%Y%m%d')
            
            # Build glob patterns to match files with any time on the same date
            # Try with various phone number formats (with/without prefix)
            phone_patterns = [
                phone_number,  # As-is
                f"9119{phone_number}",  # With 9119 prefix
                f"91{phone_number}",  # With 91 prefix
                f"011{phone_number}",  # With 011 prefix
            ]
            
            logger.info(f"Looking for recording for CallLog {call_log.id}, Campaign {call_log.campaign_id}, Lead {call_log.lead_id}")
        
        # Search paths
        search_paths = [
            self.recording_path,
            '/var/spool/asterisk/monitor',
            '/var/lib/asterisk/sounds/recordings',
        ]
        
        # Add date-based subdirectories
        date_path = None
        if call_log.start_time:
            date_path = call_log.start_time.strftime('%Y/%m/%d')
            search_paths.append(os.path.join(self.recording_path, date_path))
            search_paths.append(os.path.join('/var/spool/asterisk/monitor', date_path))
        
        # Also check today just in case
        today_path = timezone.now().strftime('%Y/%m/%d')
        if today_path != date_path:
            search_paths.append(os.path.join(self.recording_path, today_path))
        
        # First, try glob patterns for Asterisk format (to handle timezone differences)
        if call_log.start_time and call_log.campaign_id and call_log.lead_id and 'phone_patterns' in locals():
            import glob
            for path in search_paths:
                if not os.path.exists(path):
                    continue
                for phone_pattern in phone_patterns:
                    # Pattern: out-YYYYMMDD-*-CAMPAIGN-LEAD-PHONE.wav
                    glob_pattern = os.path.join(path, f"out-{date_str}-*-{call_log.campaign_id}-{call_log.lead_id}-{phone_pattern}.wav")
                    matches = glob.glob(glob_pattern)
                    if matches:
                        logger.info(f"Found recording via glob: {matches[0]}")
                        return matches[0]  # Return first match
        
        # Fallback to exact pattern matching
        for pattern in patterns:
            if not pattern:
                continue
            
            # Ensure pattern has .wav extension if missing
            if not pattern.endswith(('.wav', '.mp3', '.gsm')):
                pattern += '.wav'
                
            for path in search_paths:
                full_path = os.path.join(path, pattern)
                if os.path.exists(full_path):
                    logger.info(f"Found recording file: {full_path}")
                    return full_path
        
        logger.warning(f"Recording file not found for CallLog {call_log.id}. Tried patterns: {patterns}")
        return None
    
    def cleanup_old_recordings(self, days=90):
        """
        Clean up recordings older than specified days
        
        Args:
            days: Number of days to keep recordings
        
        Returns:
            int: Number of recordings deleted
        """
        from telephony.models import Recording
        
        cutoff = timezone.now() - timedelta(days=days)
        
        old_recordings = Recording.objects.filter(
            created_at__lt=cutoff
        )
        
        deleted = 0
        for recording in old_recordings:
            # Delete file if exists
            if recording.file_path and os.path.exists(recording.file_path):
                try:
                    os.remove(recording.file_path)
                except Exception as e:
                    logger.error(f"Error deleting recording file: {e}")
            
            recording.delete()
            deleted += 1
        
        logger.info(f"Cleaned up {deleted} old recordings")
        return deleted


# ============================================================================
# Asterisk MixMonitor Integration
# ============================================================================

def get_mixmonitor_variables(call_log):
    """
    Get variables to pass to Asterisk for recording
    
    These should be set as channel variables when originating the call.
    
    Returns:
        dict: Channel variables for recording
    """
    service = RecordingService()
    filename = service.get_recording_filename(call_log)
    file_path = service.get_recording_path(filename)
    
    return {
        'RECORDING_FILENAME': filename,
        'RECORDING_PATH': file_path,
        'MIXMON_FORMAT': 'wav',
        'MIXMON_OPTIONS': 'b',  # b = record both sides
    }


# ============================================================================
# Asterisk Dialplan Extension
# ============================================================================
"""
Add this to your Asterisk dialplan (extensions.conf) to enable recording:

[autodialer-outbound]
exten => _X.,1,NoOp(Autodialer Outbound Call)
 same => n,Set(RECORDING_FILE=${CHANNEL(RECORDING_PATH)}/${CHANNEL(RECORDING_FILENAME)})
 same => n,MixMonitor(${RECORDING_FILE},b)
 same => n,Dial(${DIAL_STRING},30,tTwW)
 same => n,StopMixMonitor()
 same => n,Hangup()

[autodialer-inbound]
exten => _X.,1,NoOp(Autodialer Inbound Call)
 same => n,Set(RECORDING_FILE=${CHANNEL(RECORDING_PATH)}/${CHANNEL(RECORDING_FILENAME)})
 same => n,MixMonitor(${RECORDING_FILE},b)
 same => n,Stasis(autodialer)
 same => n,StopMixMonitor()
 same => n,Hangup()
"""


# ============================================================================
# ARI Worker Integration
# ============================================================================
"""
Add this to your ari_worker.py to create recordings on call end:

# In _handle_channel_destroyed method:

from telephony.recording_service import RecordingService

def _handle_channel_destroyed(self, ...):
    # ... existing code ...
    
    # Create recording entry if call had talk time
    if call_log and call_log.talk_duration and call_log.talk_duration > 0:
        recording_service = RecordingService()
        recording_service.create_recording_entry(call_log)
        
        # Try to sync the recording file
        recording_service.sync_recordings(call_log)
"""


# ============================================================================
# Celery Task for Recording Sync
# ============================================================================

def sync_recordings_task():
    """
    Celery task to sync recordings periodically
    
    Add to campaigns/tasks.py or create telephony/tasks.py
    """
    from celery import shared_task
    
    @shared_task
    def sync_call_recordings():
        """Sync recordings from disk to database"""
        service = RecordingService()
        synced = service.sync_recordings()
        return {'synced': synced}
    
    @shared_task
    def cleanup_old_recordings(days=90):
        """Clean up old recordings"""
        service = RecordingService()
        deleted = service.cleanup_old_recordings(days)
        return {'deleted': deleted}
