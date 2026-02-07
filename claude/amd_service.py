"""
Answering Machine Detection (AMD) - Phase 4.1

This module provides AMD integration with Asterisk for detecting:
1. Human answers vs answering machines/voicemail
2. Fax machines
3. SIT tones (Special Information Tones)

Supports both Asterisk native AMD and external AMD services.
"""

import logging
from enum import Enum
from dataclasses import dataclass
from typing import Optional, Callable
from django.conf import settings

logger = logging.getLogger(__name__)


class AMDResult(Enum):
    """AMD detection results"""
    HUMAN = 'human'
    MACHINE = 'machine'
    UNSURE = 'unsure'
    FAX = 'fax'
    SIT = 'sit'
    NOTSURE = 'notsure'
    HANGUP = 'hangup'
    TIMEOUT = 'timeout'


@dataclass
class AMDConfig:
    """AMD Configuration"""
    # Enable/disable AMD
    enabled: bool = True
    
    # Initial silence threshold (ms) - silence before greeting
    initial_silence: int = 2500
    
    # Greeting length threshold (ms) - human greetings are usually shorter
    greeting: int = 1500
    
    # After greeting silence (ms)
    after_greeting_silence: int = 800
    
    # Total analysis time (ms)
    total_analysis_time: int = 5000
    
    # Minimum word length (ms)
    min_word_length: int = 100
    
    # Time between words (ms)
    between_words_silence: int = 50
    
    # Maximum number of words
    maximum_number_of_words: int = 3
    
    # Maximum word length (ms) - machines have longer greetings
    maximum_word_length: int = 5000
    
    # Silence threshold (dB)
    silence_threshold: int = 256
    
    # Action on machine detection
    machine_action: str = 'hangup'  # hangup, voicemail, transfer
    
    # Extension to transfer machine calls to (for voicemail drop)
    voicemail_extension: str = ''
    
    # Wait for beep before voicemail drop
    wait_for_beep: bool = True


class AMDService:
    """
    Answering Machine Detection Service
    
    Phase 4.1: AMD integration with Asterisk
    
    Usage:
        amd = AMDService()
        result = amd.detect(channel_id)
        
        # Or async with callback
        amd.detect_async(channel_id, on_result=handle_amd_result)
    """
    
    def __init__(self, config: AMDConfig = None):
        self.config = config or self._get_default_config()
    
    def _get_default_config(self) -> AMDConfig:
        """Get AMD config from Django settings or defaults"""
        amd_settings = getattr(settings, 'AMD_CONFIG', {})
        return AMDConfig(**amd_settings)
    
    def get_asterisk_amd_options(self) -> str:
        """
        Generate AMD application options string for Asterisk
        
        Format: AMD([initialSilence,[greeting,[afterGreetingSilence,
                    [totalAnalysisTime,[minWordLength,[betweenWordsSilence,
                    [maximumNumberOfWords,[silenceThreshold,[maximumWordLength]]]]]]]]])
        
        Returns:
            str: AMD options string
        """
        if not self.config.enabled:
            return ''
        
        options = [
            str(self.config.initial_silence),
            str(self.config.greeting),
            str(self.config.after_greeting_silence),
            str(self.config.total_analysis_time),
            str(self.config.min_word_length),
            str(self.config.between_words_silence),
            str(self.config.maximum_number_of_words),
            str(self.config.silence_threshold),
            str(self.config.maximum_word_length),
        ]
        
        return ','.join(options)
    
    def get_ari_amd_variables(self) -> dict:
        """
        Get channel variables for ARI-based AMD
        
        Returns:
            dict: Channel variables to set
        """
        return {
            'AMD_ENABLED': '1' if self.config.enabled else '0',
            'AMD_INITIAL_SILENCE': str(self.config.initial_silence),
            'AMD_GREETING': str(self.config.greeting),
            'AMD_TOTAL_TIME': str(self.config.total_analysis_time),
            'AMD_MACHINE_ACTION': self.config.machine_action,
            'AMD_VOICEMAIL_EXT': self.config.voicemail_extension,
        }
    
    def parse_amd_result(self, result_string: str, cause_string: str = '') -> AMDResult:
        """
        Parse AMD result from Asterisk
        
        Args:
            result_string: AMDSTATUS variable value
            cause_string: AMDCAUSE variable value
        
        Returns:
            AMDResult: Parsed result
        """
        result_map = {
            'HUMAN': AMDResult.HUMAN,
            'MACHINE': AMDResult.MACHINE,
            'NOTSURE': AMDResult.NOTSURE,
            'HANGUP': AMDResult.HANGUP,
        }
        
        # Check cause for more specific results
        if 'FAX' in cause_string.upper():
            return AMDResult.FAX
        if 'SIT' in cause_string.upper():
            return AMDResult.SIT
        
        return result_map.get(result_string.upper(), AMDResult.UNSURE)
    
    def should_connect_to_agent(self, result: AMDResult) -> bool:
        """
        Determine if call should be connected to agent
        
        Args:
            result: AMD result
        
        Returns:
            bool: True if should connect to agent
        """
        # Connect human calls and unsure calls to agents
        return result in [AMDResult.HUMAN, AMDResult.UNSURE, AMDResult.NOTSURE]
    
    def get_machine_action(self, result: AMDResult) -> str:
        """
        Get action to take for machine detection
        
        Args:
            result: AMD result
        
        Returns:
            str: Action to take (hangup, voicemail, transfer)
        """
        if result == AMDResult.HUMAN:
            return 'connect'
        elif result == AMDResult.MACHINE:
            return self.config.machine_action
        elif result == AMDResult.FAX:
            return 'hangup'
        elif result == AMDResult.SIT:
            return 'hangup'
        else:
            # Unsure - connect to agent and let them decide
            return 'connect'
    
    def handle_amd_result(
        self, 
        channel_id: str, 
        result: AMDResult,
        call_log_id: int = None
    ) -> dict:
        """
        Handle AMD result and update call log
        
        Args:
            channel_id: Asterisk channel ID
            result: AMD detection result
            call_log_id: Optional call log ID to update
        
        Returns:
            dict: Action details
        """
        from calls.models import CallLog
        
        action = self.get_machine_action(result)
        
        # Update call log if provided
        if call_log_id:
            try:
                call_log = CallLog.objects.get(id=call_log_id)
                call_log.amd_result = result.value
                call_log.amd_action = action
                call_log.save(update_fields=['amd_result', 'amd_action'])
            except CallLog.DoesNotExist:
                logger.warning(f"Call log {call_log_id} not found for AMD update")
        
        logger.info(f"AMD result for {channel_id}: {result.value} -> {action}")
        
        return {
            'channel_id': channel_id,
            'result': result.value,
            'action': action,
            'connect_to_agent': self.should_connect_to_agent(result)
        }


class VoicemailDropService:
    """
    Service for dropping pre-recorded voicemail messages
    
    When AMD detects an answering machine, this service can:
    1. Wait for the beep
    2. Play a pre-recorded message
    3. Hangup
    """
    
    def __init__(self, asterisk_service=None):
        self.asterisk_service = asterisk_service
    
    def drop_voicemail(
        self, 
        channel_id: str, 
        message_file: str,
        wait_for_beep: bool = True,
        beep_timeout: int = 10
    ) -> bool:
        """
        Drop a voicemail message on a channel
        
        Args:
            channel_id: Asterisk channel ID
            message_file: Path to audio file to play
            wait_for_beep: Wait for beep before playing
            beep_timeout: Timeout for beep detection (seconds)
        
        Returns:
            bool: Success status
        """
        if not self.asterisk_service:
            logger.error("No Asterisk service configured for voicemail drop")
            return False
        
        try:
            # If waiting for beep, use WaitForSilence or similar
            if wait_for_beep:
                # Wait for silence (beep followed by silence)
                self.asterisk_service.execute_application(
                    channel_id,
                    'WaitForSilence',
                    f'2000,3,{beep_timeout}'  # 2s silence, 3 iterations, timeout
                )
            
            # Play the message
            self.asterisk_service.play_file(channel_id, message_file)
            
            # Hangup after message
            self.asterisk_service.hangup_channel(channel_id)
            
            logger.info(f"Voicemail dropped on {channel_id}: {message_file}")
            return True
            
        except Exception as e:
            logger.error(f"Error dropping voicemail on {channel_id}: {e}")
            return False
    
    def get_campaign_voicemail_file(self, campaign_id: int) -> Optional[str]:
        """
        Get voicemail file for a campaign
        
        Args:
            campaign_id: Campaign ID
        
        Returns:
            str: Path to voicemail file or None
        """
        from campaigns.models import Campaign
        
        try:
            campaign = Campaign.objects.get(id=campaign_id)
            
            if hasattr(campaign, 'voicemail_file') and campaign.voicemail_file:
                return campaign.voicemail_file.path
            
            # Check for default voicemail file
            default_file = getattr(settings, 'DEFAULT_VOICEMAIL_FILE', None)
            return default_file
            
        except Campaign.DoesNotExist:
            return None


# ============================================================================
# ARI Worker Integration
# ============================================================================

"""
Add to ari_worker.py for AMD integration:

from campaigns.amd_service import AMDService, AMDResult

class ARIEventWorker:
    def __init__(self, ...):
        self.amd_service = AMDService()
        ...
    
    async def _handle_stasis_start(self, event):
        channel = event['channel']
        channel_id = channel['id']
        
        # Check if AMD is enabled for this campaign
        campaign = self._get_campaign_for_channel(channel_id)
        
        if campaign and campaign.amd_enabled:
            # Get AMD result from channel variables
            amd_status = channel.get('channelvars', {}).get('AMDSTATUS', '')
            amd_cause = channel.get('channelvars', {}).get('AMDCAUSE', '')
            
            if amd_status:
                result = self.amd_service.parse_amd_result(amd_status, amd_cause)
                action_info = self.amd_service.handle_amd_result(
                    channel_id, 
                    result,
                    call_log_id=self._get_call_log_id(channel_id)
                )
                
                if not action_info['connect_to_agent']:
                    # Don't connect to agent
                    if action_info['action'] == 'voicemail':
                        await self._handle_voicemail_drop(channel_id, campaign.id)
                    else:
                        await self._hangup_channel(channel_id)
                    return
        
        # Continue with normal call handling
        ...


# Asterisk dialplan for AMD (add to extensions.conf):

[autodialer-amd]
exten => _X.,1,NoOp(Autodialer AMD Call)
 same => n,Answer()
 same => n,AMD(2500,1500,800,5000,100,50,3,256,5000)
 same => n,GotoIf($["${AMDSTATUS}" = "MACHINE"]?machine:human)
 same => n(human),Stasis(autodialer,human,${AMDSTATUS})
 same => n,Hangup()
 same => n(machine),Stasis(autodialer,machine,${AMDSTATUS})
 same => n,Hangup()
"""


# ============================================================================
# Campaign Model Extension
# ============================================================================

"""
Add these fields to your Campaign model:

class Campaign(models.Model):
    # ... existing fields ...
    
    # Phase 4.1: AMD settings
    amd_enabled = models.BooleanField(
        default=False,
        help_text="Enable Answering Machine Detection"
    )
    amd_action = models.CharField(
        max_length=20,
        choices=[
            ('hangup', 'Hangup'),
            ('voicemail', 'Drop Voicemail'),
            ('transfer', 'Transfer'),
        ],
        default='hangup',
        help_text="Action when machine detected"
    )
    voicemail_file = models.FileField(
        upload_to='voicemail/',
        blank=True,
        null=True,
        help_text="Pre-recorded voicemail message"
    )
    
    # Predictive dialer settings
    dial_mode = models.CharField(
        max_length=20,
        choices=[
            ('predictive', 'Predictive'),
            ('progressive', 'Progressive'),
            ('power', 'Power'),
            ('preview', 'Preview'),
        ],
        default='predictive'
    )
    target_abandon_rate = models.FloatField(
        default=3.0,
        help_text="Target maximum abandon rate %"
    )
    max_dial_ratio = models.FloatField(
        default=3.0,
        help_text="Maximum calls per available agent"
    )
    avg_talk_time = models.IntegerField(
        default=180,
        help_text="Average talk time in seconds (for predictions)"
    )
    wrapup_time = models.IntegerField(
        default=30,
        help_text="Default wrapup time in seconds"
    )


# Add to CallLog model:

class CallLog(models.Model):
    # ... existing fields ...
    
    # Phase 4.1: AMD fields
    amd_result = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text="AMD detection result"
    )
    amd_action = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text="Action taken based on AMD"
    )
    ring_duration = models.IntegerField(
        null=True,
        blank=True,
        help_text="Ring time before answer (seconds)"
    )
"""
