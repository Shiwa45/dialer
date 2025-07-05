# telephony/models.py

from django.db import models
from django.contrib.auth.models import User
from django.core.validators import RegexValidator
from core.models import TimeStampedModel
import uuid

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
    
    # Basic Information
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    carrier_id = models.CharField(max_length=50, unique=True, default=uuid.uuid4)
    
    # Connection Settings
    protocol = models.CharField(max_length=10, choices=PROTOCOL_CHOICES, default='sip')
    server_ip = models.CharField(max_length=200)
    port = models.PositiveIntegerField(default=5060)
    
    # Authentication
    username = models.CharField(max_length=100)
    password = models.CharField(max_length=100)
    auth_username = models.CharField(max_length=100, blank=True)
    
    # Settings
    codec = models.CharField(max_length=100, default='ulaw,alaw,gsm')
    dtmf_mode = models.CharField(max_length=20, default='rfc2833')
    qualify = models.CharField(max_length=20, default='yes')
    nat = models.CharField(max_length=20, default='force_rport,comedia')
    
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

from django.core.validators import RegexValidator
from django.db import models

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
    carrier = models.ForeignKey(Carrier, on_delete=models.SET_NULL, null=True, blank=True)

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
    
class Phone(TimeStampedModel):
    """
    Phone/extension configuration for agents
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
    secret = models.CharField(max_length=100)
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

# telephony/apps.py
from django.apps import AppConfig

class TelephonyConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'telephony'
    verbose_name = 'Telephony Management'

# telephony/__init__.py
default_app_config = 'telephony.apps.TelephonyConfig'