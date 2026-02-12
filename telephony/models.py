# telephony/models.py

from django.db import models
from django.contrib.auth.models import User
from django.core.validators import RegexValidator
from core.models import TimeStampedModel
import uuid
import secrets
import string

class AsteriskServer(TimeStampedModel):
    """
    Asterisk server configuration
    """
    SERVER_TYPES = [
        ('single', 'Single Server'),
        ('master', 'Master Server'),
        ('slave', 'Slave Server'),
    ]
    
    # Basic Information
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    server_id = models.CharField(max_length=50, unique=True, default=uuid.uuid4)
    server_type = models.CharField(max_length=20, choices=SERVER_TYPES, default='single')
    
    # Connection Settings
    server_ip = models.GenericIPAddressField()
    asterisk_version = models.CharField(max_length=20, blank=True)
    
    # AMI (Asterisk Manager Interface) Settings
    ami_host = models.CharField(max_length=200, default='localhost')
    ami_port = models.PositiveIntegerField(default=5038)
    ami_username = models.CharField(max_length=100)
    ami_password = models.CharField(max_length=100)
    ami_secret = models.CharField(max_length=100, blank=True)
    
    # ARI (Asterisk REST Interface) Settings
    ari_host = models.CharField(max_length=200, default='localhost')
    ari_port = models.PositiveIntegerField(default=8088)
    ari_username = models.CharField(max_length=100)
    ari_password = models.CharField(max_length=100)
    ari_application = models.CharField(max_length=100, default='autodialer')
    
    # Settings
    max_calls = models.PositiveIntegerField(default=100)
    is_active = models.BooleanField(default=True)
    is_recording_server = models.BooleanField(default=False)
    
    # Status
    last_connected = models.DateTimeField(null=True, blank=True)
    connection_status = models.CharField(
        max_length=20,
        choices=[
            ('connected', 'Connected'),
            ('disconnected', 'Disconnected'),
            ('error', 'Error'),
            ('unknown', 'Unknown'),
        ],
        default='unknown'
    )
    
    class Meta:
        verbose_name = "Asterisk Server"
        verbose_name_plural = "Asterisk Servers"
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} ({self.server_ip})"

class Carrier(TimeStampedModel):
    """
    SIP/IAX carriers for outbound calls
    """
    PROTOCOL_CHOICES = [
        ('sip', 'SIP'),
        ('iax2', 'IAX2'),
        ('dahdi', 'DAHDI'),
        ('pjsip', 'PJSIP'),
    ]
    REGISTRATION_CHOICES = [
        ('ip', 'IP Based'),
        ('registration', 'Registration Based'),
    ]
    
    # Basic Information
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    carrier_id = models.CharField(max_length=50, unique=True, default=uuid.uuid4)
    
    # Connection Settings
    protocol = models.CharField(max_length=10, choices=PROTOCOL_CHOICES, default='sip')
    server_ip = models.CharField(max_length=200)
    port = models.PositiveIntegerField(default=5060)
    registration_type = models.CharField(max_length=20, choices=REGISTRATION_CHOICES, default='ip')
    
    # Authentication
    username = models.CharField(max_length=100, blank=True)
    password = models.CharField(max_length=100, blank=True)
    auth_username = models.CharField(max_length=100, blank=True)
    
    # Settings
    codec = models.CharField(max_length=100, default='ulaw,alaw,gsm')
    dtmf_mode = models.CharField(max_length=20, default='rfc2833')
    qualify = models.CharField(max_length=20, default='yes')
    nat = models.CharField(max_length=20, default='force_rport,comedia')
    # Outbound routing helpers
    dial_prefix = models.CharField(max_length=10, blank=True)
    dial_timeout = models.PositiveIntegerField(default=60)
    
    # Capacity and Routing
    max_channels = models.PositiveIntegerField(default=30)
    cost_per_minute = models.DecimalField(max_digits=10, decimal_places=4, default=0.0)
    priority = models.PositiveIntegerField(default=1)
    
    # Status and Management
    is_active = models.BooleanField(default=True)
    asterisk_server = models.ForeignKey(AsteriskServer, on_delete=models.CASCADE, related_name='carriers')
    
    class Meta:
        verbose_name = "Carrier"
        verbose_name_plural = "Carriers"
        ordering = ['priority', 'name']
    
    def __str__(self):
        return f"{self.name} ({self.protocol.upper()})"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Auto-sync only for PJSIP carriers
        try:
            if self.protocol.lower() == 'pjsip' and self.is_active:
                from .models import PsEndpoint, PsAuth, PsAor
                endpoint_id = self.name
                # Endpoint
                PsEndpoint.objects.update_or_create(
                    id=endpoint_id,
                    defaults={
                        'aors': endpoint_id,
                        'auth': endpoint_id,
                        'context': 'from-campaign',
                        'allow': self.codec.replace(' ', ''),
                        'disallow': 'all',
                        'direct_media': 'no',
                        'force_rport': 'yes',
                        'rewrite_contact': 'yes',
                    }
                )
                # Auth
                PsAuth.objects.update_or_create(
                    id=endpoint_id,
                    defaults={
                        'auth_type': 'userpass',
                        'username': self.auth_username or self.username,
                        'password': self.password,
                        'realm': ''
                    }
                )
                # AOR and registration
                contact_uri = f"sip:{self.server_ip}:{self.port}"
                if self.registration_type == 'ip':
                    PsAor.objects.update_or_create(
                        id=endpoint_id,
                        defaults={'max_contacts': 1, 'remove_existing': 'yes', 'qualify_frequency': 60, 'contact': contact_uri}
                    )
                    try:
                        PsRegistration.objects.filter(id=endpoint_id).delete()
                    except Exception:
                        pass
                else:
                    PsAor.objects.update_or_create(
                        id=endpoint_id,
                        defaults={'max_contacts': 1, 'remove_existing': 'yes', 'qualify_frequency': 60, 'contact': ''}
                    )
                    # Upsert registration row
                    try:
                        PsRegistration.objects.update_or_create(
                            id=endpoint_id,
                            defaults={
                                'server_uri': contact_uri,
                                'client_uri': f"sip:{self.username}@{self.server_ip}",
                                'outbound_auth': endpoint_id,
                                'transport': 'transport-udp',
                            }
                        )
                    except Exception:
                        pass
                # Dialplan generation is now handled by DialplanService
                # to support multi-carrier randomization/failover
                from .dialplan_service import DialplanService
                DialplanService.regenerate_dialplan()
                
        except Exception as e:
            # Don't block save on sync issues
            print(f"Error syncing carrier {self.name}: {e}")
            pass

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        try:
            from .dialplan_service import DialplanService
            DialplanService.regenerate_dialplan()
        except Exception:
            pass
            if self.protocol.lower() == 'pjsip':
                from .models import PsEndpoint, PsAuth, PsAor
                PsEndpoint.objects.filter(id=self.name).delete()
                PsAuth.objects.filter(id=self.name).delete()
                PsAor.objects.filter(id=self.name).delete()
        except Exception:
            pass
        return super().delete(*args, **kwargs)

class DID(TimeStampedModel):
    """
    Direct Inward Dialing numbers
    """
    DID_TYPES = [
        ('inbound', 'Inbound Only'),
        ('outbound', 'Outbound Only'),
        ('bidirectional', 'Bidirectional'),
    ]

    # Basic Information
    phone_number = models.CharField(
        max_length=20,
        unique=True,
        validators=[
            RegexValidator(
                regex=r'^\+?1?\d{9,15}$',
                message="Enter a valid phone number"
            )
        ]
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    # Type and Usage
    did_type = models.CharField(max_length=20, choices=DID_TYPES, default='bidirectional')
    is_active = models.BooleanField(default=True)

    # Routing
    asterisk_server = models.ForeignKey(AsteriskServer, on_delete=models.CASCADE, related_name='dids')
    carrier = models.ForeignKey(Carrier, on_delete=models.SET_NULL, null=True, blank=True, related_name='dids')

    # Inbound Settings
    context = models.CharField(max_length=100, default='from-trunk')
    extension = models.CharField(max_length=20, blank=True)

    # Campaign Assignment
    assigned_campaign = models.ForeignKey(
        'campaigns.Campaign',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_dids'
    )

    class Meta:
        verbose_name = "DID"
        verbose_name_plural = "DIDs"
        ordering = ['phone_number']

    def __str__(self):
        return f"{self.phone_number} - {self.name}"

# ============================================================================
# ASTERISK REALTIME TABLES (For direct Asterisk integration)
# ============================================================================

class PsEndpoint(models.Model):
    """PJSIP Endpoints - Asterisk Realtime Table"""
    id = models.CharField(max_length=40, primary_key=True)  # Extension number
    transport = models.CharField(max_length=40, default='transport-udp', blank=True)
    aors = models.CharField(max_length=200)
    auth = models.CharField(max_length=40)
    context = models.CharField(max_length=40, default='agents')
    disallow = models.CharField(max_length=200, default='all')
    allow = models.CharField(max_length=200, default='ulaw,alaw,gsm')
    direct_media = models.CharField(max_length=3, default='no')
    dtls_auto_generate_cert = models.CharField(max_length=3, default='yes', blank=True)
    force_rport = models.CharField(max_length=3, default='yes', blank=True)
    rewrite_contact = models.CharField(max_length=3, default='yes', blank=True)
    mailboxes = models.CharField(max_length=80, blank=True, default='')
    
    class Meta:
        db_table = 'ps_endpoints'
        managed = True  # Allow Django to manage this table

class PsAuth(models.Model):
    """PJSIP Authentication - Asterisk Realtime Table"""
    id = models.CharField(max_length=40, primary_key=True)  # Extension number
    auth_type = models.CharField(max_length=20, default='userpass')
    password = models.CharField(max_length=80)
    username = models.CharField(max_length=40)
    realm = models.CharField(max_length=40, blank=True)
    
    class Meta:
        db_table = 'ps_auths'
        managed = True

class PsAor(models.Model):
    """PJSIP Address of Record - Asterisk Realtime Table"""
    id = models.CharField(max_length=40, primary_key=True)  # Extension number
    max_contacts = models.IntegerField(default=1)
    remove_existing = models.CharField(max_length=3, default='yes')
    qualify_frequency = models.IntegerField(default=0, blank=True)
    contact = models.CharField(max_length=256, blank=True, default='')
    
    class Meta:
        db_table = 'ps_aors'
        managed = True


class PsRegistration(models.Model):
    """PJSIP outbound registrations - Asterisk Realtime Table"""
    id = models.CharField(max_length=40, primary_key=True)
    transport = models.CharField(max_length=40, default='transport-udp', blank=True)
    server_uri = models.CharField(max_length=256)
    client_uri = models.CharField(max_length=256)
    contact_user = models.CharField(max_length=80, blank=True)
    outbound_auth = models.CharField(max_length=40)

    class Meta:
        db_table = 'ps_registrations'
        managed = True

class ExtensionsTable(models.Model):
    """Dialplan Extensions - Asterisk Realtime Table"""
    id = models.AutoField(primary_key=True)
    context = models.CharField(max_length=40)
    exten = models.CharField(max_length=40)
    priority = models.IntegerField()
    app = models.CharField(max_length=40)
    appdata = models.CharField(max_length=256)
    
    class Meta:
        db_table = 'extensions_table'
        managed = True

# ============================================================================
# UPDATED PHONE MODEL WITH AUTO-SYNC (CORRECTED INDENTATION)
# ============================================================================
    
class Phone(TimeStampedModel):
    """
    Phone/extension configuration for agents with Asterisk auto-sync
    """
    PHONE_TYPES = [
        ('sip', 'SIP Phone'),
        ('iax2', 'IAX2 Phone'),
        ('webrtc', 'WebRTC'),
        ('dahdi', 'DAHDI'),
        ('virtual', 'Virtual Phone'),
    ]
    
    # Basic Information
    extension = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=200)
    phone_type = models.CharField(max_length=20, choices=PHONE_TYPES, default='sip')
    
    # User Assignment
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='phones')
    
    # SIP/IAX Settings
    secret = models.CharField(max_length=100, blank=True)
    host = models.CharField(max_length=100, default='dynamic')
    context = models.CharField(max_length=100, default='agents')
    
    # Codec and Quality
    codec = models.CharField(max_length=100, default='ulaw,alaw')
    qualify = models.CharField(max_length=20, default='yes')
    nat = models.CharField(max_length=20, default='force_rport,comedia')
    
    # Features
    call_waiting = models.BooleanField(default=True)
    call_transfer = models.BooleanField(default=True)
    three_way_calling = models.BooleanField(default=True)
    voicemail = models.BooleanField(default=False)
    
    # Status and Management
    is_active = models.BooleanField(default=True)
    asterisk_server = models.ForeignKey(AsteriskServer, on_delete=models.CASCADE, related_name='phones')
    
    # WebRTC Specific
    webrtc_enabled = models.BooleanField(default=False)
    ice_host = models.CharField(max_length=200, blank=True)
    
    class Meta:
        verbose_name = "Phone"
        verbose_name_plural = "Phones"
        ordering = ['extension']
    
    def __str__(self):
        return f"{self.extension} - {self.name}"
    
    def save(self, *args, **kwargs):
        # Generate secret if not provided
        if not self.secret:
            self.secret = self.generate_secret()
        
        # Save the Django model first
        super().save(*args, **kwargs)
        
        # Auto-sync to Asterisk realtime tables
        self.sync_to_asterisk()
    
    def delete(self, *args, **kwargs):
        # Remove from Asterisk first
        self.remove_from_asterisk()
        
        # Then delete Django record
        super().delete(*args, **kwargs)
    
    def generate_secret(self):
        """Generate a random secret for the phone"""
        return ''.join(secrets.choice(string.ascii_letters + string.digits) for i in range(12))
    
    def sync_to_asterisk(self):
        """Enhanced sync with proper PJSIP realtime configuration"""
        try:
            # Determine transport and WebRTC setting
            transport = 'transport-wss' if self.webrtc_enabled else 'transport-udp'
            webrtc_val = 'yes' if self.webrtc_enabled else 'no'

            # Create/Update PJSIP Endpoint with explicit transport
            PsEndpoint.objects.update_or_create(
                id=self.extension,
                defaults={
                    'transport': transport,  # Dynamic transport
                    'aors': self.extension,
                    'auth': self.extension,
                    'context': self.context,
                    'allow': self.codec.replace(' ', ''),
                    'disallow': 'all',
                    'direct_media': 'no',
                    'force_rport': 'yes',
                    'rewrite_contact': 'yes',
                    'dtls_auto_generate_cert': 'yes',
                    'webrtc': webrtc_val,
                }
            )
            
            # Create/Update Authentication with realm
            PsAuth.objects.update_or_create(
                id=self.extension,
                defaults={
                    'auth_type': 'userpass',
                    'username': self.extension,
                    'password': self.secret,
                    'realm': ''  # Empty realm allows any
                }
            )
            
            # Create/Update AOR with contact management
            PsAor.objects.update_or_create(
                id=self.extension,
                defaults={
                    'max_contacts': 1,
                    'remove_existing': 'yes',
                    'qualify_frequency': 60 if self.qualify == 'yes' else 0
                }
            )
            
            print(f"✅ Phone {self.extension} synced to Asterisk PJSIP realtime")
            return True
            
        except Exception as e:
            print(f"❌ Failed to sync phone {self.extension}: {e}")
            return False
            
    def remove_from_asterisk(self):
        """Remove this phone from Asterisk realtime tables"""
        try:
            PsEndpoint.objects.filter(id=self.extension).delete()
            PsAuth.objects.filter(id=self.extension).delete()
            PsAor.objects.filter(id=self.extension).delete()
            ExtensionsTable.objects.filter(
                context=self.context,
                exten=self.extension
            ).delete()
            
            print(f"✅ Phone {self.extension} removed from Asterisk")
            return True
            
        except Exception as e:
            print(f"❌ Failed to remove phone {self.extension} from Asterisk: {e}")
            return False
    
    def get_asterisk_status(self):
        """Check if phone is registered in Asterisk"""
        try:
            # This would normally query Asterisk AMI/ARI
            # For now, return based on active status
            return {
                'registered': self.is_active,
                'status': 'OK' if self.is_active else 'UNAVAILABLE',
                'ip_address': '192.168.1.100',  # Placeholder
                'last_seen': self.updated_at.strftime('%Y-%m-%d %H:%M:%S')
            }
        except Exception:
            return {
                'registered': False,
                'status': 'ERROR',
                'ip_address': None,
                'last_seen': None
            }

# ============================================================================
# REST OF MODELS (Unchanged)
# ============================================================================

class IVR(TimeStampedModel):
    """
    Interactive Voice Response menus
    """
    # Basic Information
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    ivr_id = models.CharField(max_length=50, unique=True, default=uuid.uuid4)
    
    # Audio Settings
    welcome_message = models.CharField(max_length=500, blank=True)
    invalid_message = models.CharField(max_length=500, blank=True)
    timeout_message = models.CharField(max_length=500, blank=True)
    
    # Timing
    digit_timeout = models.PositiveIntegerField(default=3000, help_text="Timeout in milliseconds")
    response_timeout = models.PositiveIntegerField(default=10000, help_text="Timeout in milliseconds")
    max_retries = models.PositiveIntegerField(default=3)
    
    # Behavior
    allow_direct_dial = models.BooleanField(default=False)
    play_exit_sound = models.BooleanField(default=True)
    
    # Management
    is_active = models.BooleanField(default=True)
    asterisk_server = models.ForeignKey(AsteriskServer, on_delete=models.CASCADE, related_name='ivrs')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    
    class Meta:
        verbose_name = "IVR"
        verbose_name_plural = "IVRs"
        ordering = ['name']
    
    def __str__(self):
        return self.name

class IVROption(TimeStampedModel):
    """
    IVR menu options
    """
    ACTION_TYPES = [
        ('extension', 'Transfer to Extension'),
        ('queue', 'Transfer to Queue'),
        ('voicemail', 'Send to Voicemail'),
        ('hangup', 'Hang Up'),
        ('repeat', 'Repeat Menu'),
        ('sub_menu', 'Go to Sub Menu'),
        ('campaign', 'Route to Campaign'),
    ]
    
    ivr = models.ForeignKey(IVR, on_delete=models.CASCADE, related_name='options')
    digit = models.CharField(max_length=1)
    description = models.CharField(max_length=200)
    
    # Action Configuration
    action_type = models.CharField(max_length=20, choices=ACTION_TYPES)
    action_value = models.CharField(max_length=200)
    
    # Audio
    option_message = models.CharField(max_length=500, blank=True)
    
    # Order and Status
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        unique_together = ['ivr', 'digit']
        ordering = ['sort_order', 'digit']
        verbose_name = "IVR Option"
        verbose_name_plural = "IVR Options"
    
    def __str__(self):
        return f"{self.ivr.name} - {self.digit}: {self.description}"

class CallQueue(TimeStampedModel):
    """
    Call queues for inbound calls
    """
    STRATEGY_CHOICES = [
        ('ringall', 'Ring All'),
        ('leastrecent', 'Least Recent'),
        ('fewestcalls', 'Fewest Calls'),
        ('random', 'Random'),
        ('rrmemory', 'Round Robin Memory'),
        ('linear', 'Linear'),
    ]
    
    # Basic Information
    name = models.CharField(max_length=200)
    extension = models.CharField(max_length=20, unique=True)
    description = models.TextField(blank=True)
    
    # Queue Strategy
    strategy = models.CharField(max_length=20, choices=STRATEGY_CHOICES, default='ringall')
    timeout = models.PositiveIntegerField(default=300, help_text="Timeout in seconds")
    max_waiting = models.PositiveIntegerField(default=0, help_text="0 = unlimited")
    
    # Audio Messages
    music_on_hold = models.CharField(max_length=100, default='default')
    join_announcement = models.CharField(max_length=500, blank=True)
    periodic_announcement = models.CharField(max_length=500, blank=True)
    
    # Behavior
    announce_position = models.BooleanField(default=True)
    announce_holdtime = models.BooleanField(default=True)
    retry_interval = models.PositiveIntegerField(default=30)
    
    # Management
    is_active = models.BooleanField(default=True)
    asterisk_server = models.ForeignKey(AsteriskServer, on_delete=models.CASCADE, related_name='queues')
    
    # Queue Members
    members = models.ManyToManyField(Phone, through='QueueMember', related_name='queues')
    
    class Meta:
        verbose_name = "Call Queue"
        verbose_name_plural = "Call Queues"
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} ({self.extension})"

class QueueMember(TimeStampedModel):
    """
    Queue membership for phones/agents
    """
    queue = models.ForeignKey(CallQueue, on_delete=models.CASCADE)
    phone = models.ForeignKey(Phone, on_delete=models.CASCADE)
    
    # Membership Settings
    penalty = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    paused = models.BooleanField(default=False)
    
    class Meta:
        unique_together = ['queue', 'phone']
        verbose_name = "Queue Member"
        verbose_name_plural = "Queue Members"
    
    def __str__(self):
        return f"{self.queue.name} - {self.phone.extension}"

class Recording(TimeStampedModel):
    """
    Call recording files and metadata
    """
    # Basic Information
    filename = models.CharField(max_length=500)
    file_path = models.CharField(max_length=1000)
    file_size = models.PositiveIntegerField(default=0)
    duration = models.PositiveIntegerField(default=0, help_text="Duration in seconds")
    
    # Recording Details
    call_id = models.CharField(max_length=100)
    channel = models.CharField(max_length=200, blank=True)
    format = models.CharField(max_length=10, default='wav')
    
    # Associated Records
    call_log = models.ForeignKey(
        'calls.CallLog',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='recordings'
    )
    
    # Management
    asterisk_server = models.ForeignKey(AsteriskServer, on_delete=models.CASCADE, related_name='recordings')
    is_available = models.BooleanField(default=True)
    
    # Metadata
    recording_start = models.DateTimeField()
    recording_end = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        verbose_name = "Recording"
        verbose_name_plural = "Recordings"
        ordering = ['-recording_start']
        indexes = [
            models.Index(fields=['call_id']),
            models.Index(fields=['recording_start']),
        ]
    
    def __str__(self):
        return f"Recording {self.filename}"

class DialplanContext(TimeStampedModel):
    """
    Asterisk dialplan contexts
    """
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    asterisk_server = models.ForeignKey(AsteriskServer, on_delete=models.CASCADE, related_name='contexts')
    
    class Meta:
        verbose_name = "Dialplan Context"
        verbose_name_plural = "Dialplan Contexts"
        ordering = ['name']
    
    def __str__(self):
        return self.name

class DialplanExtension(TimeStampedModel):
    """
    Dialplan extensions within contexts
    """
    context = models.ForeignKey(DialplanContext, on_delete=models.CASCADE, related_name='extensions')
    extension = models.CharField(max_length=100)
    priority = models.PositiveIntegerField(default=1)
    application = models.CharField(max_length=100)
    arguments = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        unique_together = ['context', 'extension', 'priority']
        ordering = ['extension', 'priority']
        verbose_name = "Dialplan Extension"
        verbose_name_plural = "Dialplan Extensions"
    
    def __str__(self):
        return f"{self.context.name},{self.extension},{self.priority}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Mirror into Asterisk Realtime extensions table
        try:
            ExtensionsTable.objects.update_or_create(
                context=self.context.name,
                exten=self.extension,
                priority=self.priority,
                defaults={
                    'app': self.application,
                    'appdata': self.arguments or ''
                }
            )
        except Exception:
            pass

    def delete(self, *args, **kwargs):
        try:
            ExtensionsTable.objects.filter(
                context=self.context.name,
                exten=self.extension,
                priority=self.priority,
            ).delete()
        except Exception:
            pass
        return super().delete(*args, **kwargs)
    




# Add this model to your Django telephony/models.py

class SipBuddy(models.Model):
    """SIP Buddies table for chan_sip realtime"""
    name = models.CharField(max_length=40, primary_key=True)  # Extension
    username = models.CharField(max_length=40)
    secret = models.CharField(max_length=40)
    host = models.CharField(max_length=31, default='dynamic')
    context = models.CharField(max_length=40, default='agents')
    type = models.CharField(max_length=6, default='friend')
    nat = models.CharField(max_length=20, default='force_rport,comedia')
    qualify = models.CharField(max_length=7, default='yes')
    canreinvite = models.CharField(max_length=3, default='no')
    disallow = models.CharField(max_length=200, default='all')
    allow = models.CharField(max_length=200, default='ulaw,alaw')
    
    class Meta:
        db_table = 'sip_buddies'
        managed = True

# Update your Phone model to also sync to SIP
def sync_to_sip(self):
    """Sync phone to chan_sip realtime table"""
    try:
        SipBuddy.objects.update_or_create(
            name=self.extension,
            defaults={
                'username': self.extension,
                'secret': self.secret,
                'host': 'dynamic',
                'context': self.context,
                'type': 'friend',
                'nat': 'force_rport,comedia',
                'qualify': 'yes',
                'disallow': 'all',
                'allow': self.codec.replace(' ', ''),
            }
        )
        print(f"✅ Phone {self.extension} synced to chan_sip")
        return True
    except Exception as e:
        print(f"❌ Failed to sync phone {self.extension} to SIP: {e}")
        return False

# Add this to your Phone.save() method
def save(self, *args, **kwargs):
    if not self.secret:
        self.secret = self.generate_secret()
    super().save(*args, **kwargs)
    # Sync to both PJSIP and chan_sip
    self.sync_to_asterisk()  # Your existing PJSIP sync
    self.sync_to_sip()       # New chan_sip sync

