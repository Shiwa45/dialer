# telephony/forms.py

from django import forms
from django.contrib.auth.models import User
from django.core.validators import RegexValidator
from .models import (
    AsteriskServer, Carrier, DID, Phone, IVR, IVROption,
    CallQueue, QueueMember, Recording, DialplanContext, DialplanExtension
)
from campaigns.models import Campaign

class AsteriskServerForm(forms.ModelForm):
    """
    Form for creating/editing Asterisk servers
    """
    class Meta:
        model = AsteriskServer
        fields = [
            'name', 'description', 'server_type', 'server_ip',
            'asterisk_version', 'ami_host', 'ami_port', 'ami_username',
            'ami_password', 'ami_secret', 'ari_host', 'ari_port',
            'ari_username', 'ari_password', 'ari_application',
            'max_calls', 'is_active', 'is_recording_server'
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'ami_password': forms.PasswordInput(),
            'ami_secret': forms.PasswordInput(),
            'ari_password': forms.PasswordInput(),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'server_ip': forms.TextInput(attrs={'class': 'form-control'}),
            'asterisk_version': forms.TextInput(attrs={'class': 'form-control'}),
            'ami_host': forms.TextInput(attrs={'class': 'form-control'}),
            'ami_port': forms.NumberInput(attrs={'class': 'form-control'}),
            'ami_username': forms.TextInput(attrs={'class': 'form-control'}),
            'ari_host': forms.TextInput(attrs={'class': 'form-control'}),
            'ari_port': forms.NumberInput(attrs={'class': 'form-control'}),
            'ari_username': forms.TextInput(attrs={'class': 'form-control'}),
            'ari_application': forms.TextInput(attrs={'class': 'form-control'}),
            'max_calls': forms.NumberInput(attrs={'class': 'form-control'}),
            'server_type': forms.Select(attrs={'class': 'form-control'}),
        }

    def clean_server_ip(self):
        server_ip = self.cleaned_data['server_ip']
        # Additional IP validation if needed
        return server_ip

    def clean_ami_port(self):
        port = self.cleaned_data['ami_port']
        if port < 1 or port > 65535:
            raise forms.ValidationError("Port must be between 1 and 65535")
        return port

    def clean_ari_port(self):
        port = self.cleaned_data['ari_port']
        if port < 1 or port > 65535:
            raise forms.ValidationError("Port must be between 1 and 65535")
        return port


class CarrierForm(forms.ModelForm):
    """
    Form for creating/editing carriers
    """
    class Meta:
        model = Carrier
        fields = [
            'name', 'description', 'protocol', 'server_ip', 'port',
            'username', 'password', 'auth_username', 'codec', 'dtmf_mode', 
            'qualify', 'nat', 'max_channels', 'cost_per_minute', 'priority',
            'is_active', 'asterisk_server'
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'password': forms.PasswordInput(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'server_ip': forms.TextInput(attrs={'class': 'form-control'}),
            'port': forms.NumberInput(attrs={'class': 'form-control'}),
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'auth_username': forms.TextInput(attrs={'class': 'form-control'}),
            'codec': forms.TextInput(attrs={'class': 'form-control'}),
            'dtmf_mode': forms.TextInput(attrs={'class': 'form-control'}),
            'qualify': forms.TextInput(attrs={'class': 'form-control'}),
            'nat': forms.TextInput(attrs={'class': 'form-control'}),
            'max_channels': forms.NumberInput(attrs={'class': 'form-control'}),
            'cost_per_minute': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.0001'}),
            'priority': forms.NumberInput(attrs={'class': 'form-control'}),
            'protocol': forms.Select(attrs={'class': 'form-control'}),
            'asterisk_server': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['asterisk_server'].queryset = AsteriskServer.objects.filter(is_active=True)


class DIDForm(forms.ModelForm):
    """
    Form for creating/editing DIDs
    """
    class Meta:
        model = DID
        fields = [
            'phone_number', 'name', 'description', 'did_type',
            'is_active', 'asterisk_server', 'carrier', 'context',
            'extension', 'assigned_campaign'
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+1234567890'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'context': forms.TextInput(attrs={'class': 'form-control'}),
            'extension': forms.TextInput(attrs={'class': 'form-control'}),
            'did_type': forms.Select(attrs={'class': 'form-control'}),
            'asterisk_server': forms.Select(attrs={'class': 'form-control'}),
            'carrier': forms.Select(attrs={'class': 'form-control'}),
            'assigned_campaign': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['asterisk_server'].queryset = AsteriskServer.objects.filter(is_active=True)
        self.fields['carrier'].queryset = Carrier.objects.filter(is_active=True)
        self.fields['assigned_campaign'].queryset = Campaign.objects.filter(is_active=True)
        self.fields['carrier'].required = False
        self.fields['assigned_campaign'].required = False

    def clean_phone_number(self):
        phone_number = self.cleaned_data['phone_number']
        # Remove any non-digit characters except +
        import re
        cleaned = re.sub(r'[^\d+]', '', phone_number)
        
        # Validate format
        if not re.match(r'^\+?1?\d{9,15}$', cleaned):
            raise forms.ValidationError("Enter a valid phone number")
        
        return cleaned


class PhoneForm(forms.ModelForm):
    """
    Form for creating/editing phones/extensions
    """
    class Meta:
        model = Phone
        fields = [
            'extension', 'name', 'phone_type', 'user', 'secret',
            'host', 'context', 'codec', 'qualify', 'nat',
            'call_waiting', 'call_transfer', 'three_way_calling',
            'voicemail', 'is_active', 'asterisk_server',
            'webrtc_enabled', 'ice_host'
        ]
        widgets = {
            'secret': forms.PasswordInput(attrs={'class': 'form-control'}),
            'extension': forms.TextInput(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'host': forms.TextInput(attrs={'class': 'form-control'}),
            'context': forms.TextInput(attrs={'class': 'form-control'}),
            'codec': forms.TextInput(attrs={'class': 'form-control'}),
            'qualify': forms.TextInput(attrs={'class': 'form-control'}),
            'nat': forms.TextInput(attrs={'class': 'form-control'}),
            'ice_host': forms.TextInput(attrs={'class': 'form-control'}),
            'phone_type': forms.Select(attrs={'class': 'form-control'}),
            'user': forms.Select(attrs={'class': 'form-control'}),
            'asterisk_server': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['asterisk_server'].queryset = AsteriskServer.objects.filter(is_active=True)
        self.fields['user'].queryset = User.objects.filter(is_active=True).order_by('username')
        self.fields['user'].required = False

    def clean_extension(self):
        extension = self.cleaned_data['extension']
        # Validate extension format
        import re
        if not re.match(r'^\d{3,10}$', extension):
            raise forms.ValidationError("Extension must be 3-10 digits")
        return extension


class IVRForm(forms.ModelForm):
    """
    Form for creating/editing IVRs
    """
    class Meta:
        model = IVR
        fields = [
            'name', 'description', 'welcome_message', 'invalid_message',
            'timeout_message', 'digit_timeout', 'response_timeout',
            'max_retries', 'allow_direct_dial', 'play_exit_sound',
            'is_active', 'asterisk_server'
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'welcome_message': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
            'invalid_message': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
            'timeout_message': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'digit_timeout': forms.NumberInput(attrs={'class': 'form-control'}),
            'response_timeout': forms.NumberInput(attrs={'class': 'form-control'}),
            'max_retries': forms.NumberInput(attrs={'class': 'form-control'}),
            'asterisk_server': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['asterisk_server'].queryset = AsteriskServer.objects.filter(is_active=True)


class IVROptionForm(forms.ModelForm):
    """
    Form for creating/editing IVR options
    """
    class Meta:
        model = IVROption
        fields = [
            'digit', 'description', 'action_type', 'action_value',
            'is_active'
        ]
        widgets = {
            'description': forms.TextInput(attrs={'class': 'form-control'}),
            'digit': forms.TextInput(attrs={'class': 'form-control', 'maxlength': '1'}),
            'action_value': forms.TextInput(attrs={'class': 'form-control'}),
            'action_type': forms.Select(attrs={'class': 'form-control'}),
        }

    def clean_digit(self):
        digit = self.cleaned_data['digit']
        if digit not in '0123456789*#':
            raise forms.ValidationError("Digit must be 0-9, *, or #")
        return digit


class CallQueueForm(forms.ModelForm):
    """
    Form for creating/editing call queues
    """
    class Meta:
        model = CallQueue
        fields = [
            'name', 'extension', 'description', 'strategy', 'timeout',
            'max_waiting', 'music_on_hold', 'join_announcement',
            'periodic_announcement', 'announce_position', 'announce_holdtime',
            'retry_interval', 'is_active', 'asterisk_server'
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'join_announcement': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
            'periodic_announcement': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'extension': forms.TextInput(attrs={'class': 'form-control'}),
            'timeout': forms.NumberInput(attrs={'class': 'form-control'}),
            'max_waiting': forms.NumberInput(attrs={'class': 'form-control'}),
            'music_on_hold': forms.TextInput(attrs={'class': 'form-control'}),
            'retry_interval': forms.NumberInput(attrs={'class': 'form-control'}),
            'strategy': forms.Select(attrs={'class': 'form-control'}),
            'asterisk_server': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['asterisk_server'].queryset = AsteriskServer.objects.filter(is_active=True)


class QueueMemberForm(forms.ModelForm):
    """
    Form for adding/editing queue members
    """
    class Meta:
        model = QueueMember
        fields = ['phone', 'penalty', 'is_active', 'paused']
        widgets = {
            'penalty': forms.NumberInput(attrs={'class': 'form-control'}),
            'phone': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        queue = kwargs.pop('queue', None)
        super().__init__(*args, **kwargs)
        if queue:
            # Only show phones from the same server
            self.fields['phone'].queryset = Phone.objects.filter(
                asterisk_server=queue.asterisk_server,
                is_active=True
            )


class DialplanContextForm(forms.ModelForm):
    """
    Form for creating/editing dialplan contexts
    """
    class Meta:
        model = DialplanContext
        fields = ['name', 'description', 'is_active', 'asterisk_server']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'asterisk_server': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['asterisk_server'].queryset = AsteriskServer.objects.filter(is_active=True)

    def clean_name(self):
        name = self.cleaned_data['name']
        # Validate context name format
        import re
        if not re.match(r'^[a-zA-Z0-9_-]+$', name):
            raise forms.ValidationError("Context name can only contain letters, numbers, underscore, and dash")
        return name


class DialplanExtensionForm(forms.ModelForm):
    """
    Form for creating/editing dialplan extensions
    """
    class Meta:
        model = DialplanExtension
        fields = [
            'extension', 'priority', 'application', 'arguments', 'is_active'
        ]
        widgets = {
            'arguments': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
            'extension': forms.TextInput(attrs={'class': 'form-control'}),
            'priority': forms.NumberInput(attrs={'class': 'form-control'}),
            'application': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def clean_extension(self):
        extension = self.cleaned_data['extension']
        # Allow various extension patterns
        import re
        if not re.match(r'^[a-zA-Z0-9_.-]+$', extension):
            raise forms.ValidationError("Extension can contain letters, numbers, underscore, dot, and dash")
        return extension


class BulkDIDImportForm(forms.Form):
    """
    Form for bulk importing DIDs from CSV
    """
    csv_file = forms.FileField(
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.csv'}),
        help_text="Upload a CSV file with columns: phone_number, name, did_type, carrier_id"
    )
    asterisk_server = forms.ModelChoiceField(
        queryset=AsteriskServer.objects.filter(is_active=True),
        widget=forms.Select(attrs={'class': 'form-control'}),
        help_text="Default server for imported DIDs"
    )
    overwrite_existing = forms.BooleanField(
        required=False,
        help_text="Overwrite existing DIDs with same phone number"
    )

    def clean_csv_file(self):
        file = self.cleaned_data['csv_file']
        if not file.name.endswith('.csv'):
            raise forms.ValidationError("File must be a CSV file")
        
        # Check file size (limit to 5MB)
        if file.size > 5 * 1024 * 1024:
            raise forms.ValidationError("File size must be less than 5MB")
        
        return file


class BulkPhoneCreateForm(forms.Form):
    """
    Form for creating multiple phone extensions
    """
    extension_start = forms.CharField(
        max_length=10,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '1000'}),
        help_text="Starting extension number"
    )
    extension_count = forms.IntegerField(
        min_value=1,
        max_value=100,
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
        help_text="Number of extensions to create (max 100)"
    )
    name_prefix = forms.CharField(
        max_length=50,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Agent'}),
        help_text="Name prefix for extensions (e.g., 'Agent' will create 'Agent 1001', 'Agent 1002', etc.)"
    )
    phone_type = forms.ChoiceField(
        choices=Phone.PHONE_TYPES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    asterisk_server = forms.ModelChoiceField(
        queryset=AsteriskServer.objects.filter(is_active=True),
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    webrtc_enabled = forms.BooleanField(
        required=False,
        help_text="Enable WebRTC for all created extensions"
    )

    def clean_extension_start(self):
        extension = self.cleaned_data['extension_start']
        import re
        if not re.match(r'^\d{3,10}$', extension):
            raise forms.ValidationError("Extension must be 3-10 digits")
        return extension

    def clean(self):
        cleaned_data = super().clean()
        extension_start = cleaned_data.get('extension_start')
        extension_count = cleaned_data.get('extension_count')
        
        if extension_start and extension_count:
            start_num = int(extension_start)
            end_num = start_num + extension_count - 1
            
            # Check for existing extensions in range
            existing = Phone.objects.filter(
                extension__gte=str(start_num),
                extension__lte=str(end_num)
            ).exists()
            
            if existing:
                raise forms.ValidationError("Some extensions in this range already exist")
        
        return cleaned_data


class RecordingForm(forms.ModelForm):
    """
    Form for managing recordings
    """
    class Meta:
        model = Recording
        fields = [
            'filename', 'file_path', 'file_size', 'duration', 'call_id',
            'channel', 'format', 'call_log', 'asterisk_server', 'is_available',
            'recording_start', 'recording_end'
        ]
        widgets = {
            'filename': forms.TextInput(attrs={'class': 'form-control'}),
            'file_path': forms.TextInput(attrs={'class': 'form-control'}),
            'file_size': forms.NumberInput(attrs={'class': 'form-control'}),
            'duration': forms.NumberInput(attrs={'class': 'form-control'}),
            'call_id': forms.TextInput(attrs={'class': 'form-control'}),
            'channel': forms.TextInput(attrs={'class': 'form-control'}),
            'format': forms.TextInput(attrs={'class': 'form-control'}),
            'recording_start': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'recording_end': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'asterisk_server': forms.Select(attrs={'class': 'form-control'}),
            'call_log': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['asterisk_server'].queryset = AsteriskServer.objects.filter(is_active=True)
        self.fields['call_log'].required = False
        self.fields['recording_end'].required = False


class WebRTCConfigForm(forms.Form):
    """
    Form for WebRTC phone configuration
    """
    stun_server = forms.CharField(
        max_length=200,
        initial='stun:stun.l.google.com:19302',
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        help_text="STUN server for NAT traversal"
    )
    turn_server = forms.CharField(
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        help_text="TURN server for firewall traversal (optional)"
    )
    turn_username = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    turn_password = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.PasswordInput(attrs={'class': 'form-control'})
    )
    enable_audio = forms.BooleanField(
        initial=True,
        required=False,
        help_text="Enable audio for WebRTC calls"
    )
    enable_video = forms.BooleanField(
        initial=False,
        required=False,
        help_text="Enable video for WebRTC calls"
    )
    """
    Form for WebRTC phone configuration
    """
    stun_server = forms.CharField(
        max_length=200,
        initial='stun:stun.l.google.com:19302',
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        help_text="STUN server for NAT traversal"
    )
    turn_server = forms.CharField(
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        help_text="TURN server for firewall traversal (optional)"
    )
    turn_username = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    turn_password = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.PasswordInput(attrs={'class': 'form-control'})
    )
    enable_audio = forms.BooleanField(
        initial=True,
        required=False,
        help_text="Enable audio for WebRTC calls"
    )
    enable_video = forms.BooleanField(
        initial=False,
        required=False,
        help_text="Enable video for WebRTC calls"
    )