"""telephony/forms.py (reconstructed clean version)
Ensures CarrierForm credentials are only required for registration-based,
and fixes earlier corruption.
"""

from django import forms
from django.contrib.auth.models import User
from .models import (
    AsteriskServer, Carrier, DID, Phone, IVR, IVROption,
    CallQueue, QueueMember, DialplanContext, DialplanExtension,
)
from campaigns.models import Campaign


class AsteriskServerForm(forms.ModelForm):
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
            'description': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'ami_password': forms.PasswordInput(attrs={'class': 'form-control'}),
            'ami_secret': forms.PasswordInput(attrs={'class': 'form-control'}),
            'ari_password': forms.PasswordInput(attrs={'class': 'form-control'}),
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
    """Carrier form with conditional credentials for registration-based carriers."""

    class Meta:
        model = Carrier
        fields = [
            'name', 'description', 'protocol', 'server_ip', 'port',
            'registration_type', 'username', 'password', 'auth_username',
            'codec', 'dtmf_mode', 'qualify', 'nat',
            'dial_prefix', 'dial_timeout',
            'max_channels', 'cost_per_minute', 'priority',
            'is_active', 'asterisk_server'
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'protocol': forms.Select(attrs={'class': 'form-control'}),
            'server_ip': forms.TextInput(attrs={'class': 'form-control'}),
            'port': forms.NumberInput(attrs={'class': 'form-control'}),
            'registration_type': forms.Select(attrs={'class': 'form-control'}),
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'password': forms.PasswordInput(attrs={'class': 'form-control'}),
            'auth_username': forms.TextInput(attrs={'class': 'form-control'}),
            'codec': forms.TextInput(attrs={'class': 'form-control'}),
            'dtmf_mode': forms.TextInput(attrs={'class': 'form-control'}),
            'qualify': forms.TextInput(attrs={'class': 'form-control'}),
            'nat': forms.TextInput(attrs={'class': 'form-control'}),
            'dial_prefix': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., 9 or 91'}),
            'dial_timeout': forms.NumberInput(attrs={'class': 'form-control'}),
            'max_channels': forms.NumberInput(attrs={'class': 'form-control'}),
            'cost_per_minute': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.0001'}),
            'priority': forms.NumberInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'asterisk_server': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].required = False
        self.fields['password'].required = False
        self.fields['auth_username'].required = False

    def clean(self):
        cleaned = super().clean()
        reg_type = cleaned.get('registration_type')
        username = (cleaned.get('username') or '').strip()
        password = (cleaned.get('password') or '').strip()
        if reg_type == 'registration':
            if not username:
                self.add_error('username', 'Username is required for registration-based carriers')
            if not password:
                self.add_error('password', 'Password is required for registration-based carriers')
        pref = (cleaned.get('dial_prefix') or '').strip()
        if pref and not pref.isdigit():
            self.add_error('dial_prefix', 'Dial prefix must be digits')
        return cleaned


class DIDForm(forms.ModelForm):
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
        import re
        phone_number = self.cleaned_data['phone_number']
        cleaned = re.sub(r'[^\d+]', '', phone_number)
        if not re.match(r'^\+?\d{9,15}$', cleaned):
            raise forms.ValidationError('Enter a valid phone number')
        return cleaned


class PhoneForm(forms.ModelForm):
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
        self.fields['secret'].required = False

    def clean_extension(self):
        import re
        extension = self.cleaned_data['extension']
        if not re.match(r'^\d{3,10}$', extension):
            raise forms.ValidationError('Extension must be 3-10 digits')
        return extension

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get('secret'):
            import secrets, string
            cleaned['secret'] = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(12))
        return cleaned


class BulkPhoneCreateForm(forms.Form):
    extension_start = forms.CharField(max_length=10)
    extension_count = forms.IntegerField(min_value=1, max_value=100)
    name_prefix = forms.CharField(max_length=50)
    phone_type = forms.ChoiceField(choices=Phone.PHONE_TYPES)
    asterisk_server = forms.ModelChoiceField(queryset=AsteriskServer.objects.filter(is_active=True))
    webrtc_enabled = forms.BooleanField(required=False)
    auto_generate_secrets = forms.BooleanField(initial=True, required=False)

    def clean_extension_start(self):
        import re
        extension = self.cleaned_data['extension_start']
        if not re.match(r'^\d{3,10}$', extension):
            raise forms.ValidationError('Extension must be 3-10 digits')
        return extension


class IVRForm(forms.ModelForm):
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
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['asterisk_server'].queryset = AsteriskServer.objects.filter(is_active=True)


class IVROptionForm(forms.ModelForm):
    class Meta:
        model = IVROption
        fields = ['digit', 'description', 'action_type', 'action_value', 'is_active']

    def clean_digit(self):
        digit = self.cleaned_data['digit']
        if digit not in '0123456789*#':
            raise forms.ValidationError('Digit must be 0-9, *, or #')
        return digit


class CallQueueForm(forms.ModelForm):
    class Meta:
        model = CallQueue
        fields = [
            'name', 'extension', 'description', 'strategy', 'timeout',
            'max_waiting', 'music_on_hold', 'join_announcement',
            'periodic_announcement', 'announce_position', 'announce_holdtime',
            'retry_interval', 'is_active', 'asterisk_server'
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['asterisk_server'].queryset = AsteriskServer.objects.filter(is_active=True)


class QueueMemberForm(forms.ModelForm):
    class Meta:
        model = QueueMember
        fields = ['phone', 'penalty', 'is_active', 'paused']

    def __init__(self, *args, **kwargs):
        queue = kwargs.pop('queue', None)
        super().__init__(*args, **kwargs)
        if queue:
            self.fields['phone'].queryset = Phone.objects.filter(
                asterisk_server=queue.asterisk_server,
                is_active=True
            )


class DialplanContextForm(forms.ModelForm):
    class Meta:
        model = DialplanContext
        fields = ['name', 'description', 'is_active', 'asterisk_server']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['asterisk_server'].queryset = AsteriskServer.objects.filter(is_active=True)

    def clean_name(self):
        import re
        name = self.cleaned_data['name']
        if not re.match(r'^[a-zA-Z0-9_-]+$', name):
            raise forms.ValidationError('Context name can only contain letters, numbers, underscore, and dash')
        return name


class DialplanExtensionForm(forms.ModelForm):
    generate_outbound = forms.BooleanField(required=False, initial=False)
    carrier = forms.ModelChoiceField(queryset=Carrier.objects.filter(is_active=True), required=False)
    dial_prefix = forms.CharField(max_length=10, required=False)
    timeout = forms.IntegerField(required=False, initial=60, min_value=1)

    class Meta:
        model = DialplanExtension
        fields = ['extension', 'priority', 'application', 'arguments', 'is_active']

    def clean_extension(self):
        import re
        extension = self.cleaned_data['extension']
        if not re.match(r'^[a-zA-Z0-9_.-]+$', extension):
            raise forms.ValidationError('Extension can contain letters, numbers, underscore, dot, and dash')
        return extension


class OutboundDialplanWizardForm(forms.Form):
    asterisk_server = forms.ModelChoiceField(queryset=AsteriskServer.objects.filter(is_active=True))
    context_name = forms.CharField(max_length=100, initial='from-campaign')
    carrier = forms.ModelChoiceField(queryset=Carrier.objects.filter(is_active=True))
    dial_prefix = forms.CharField(max_length=10)
    timeout = forms.IntegerField(initial=60, min_value=1)
    activate = forms.BooleanField(required=False, initial=True)

    def clean_dial_prefix(self):
        p = self.cleaned_data['dial_prefix']
        if not p.isdigit():
            raise forms.ValidationError('Dial prefix must be digits only')
        if len(p) > 6:
            raise forms.ValidationError('Dial prefix is too long')
        return p

    def clean_context_name(self):
        import re
        name = self.cleaned_data['context_name']
        if not re.match(r'^[A-Za-z0-9_-]+$', name):
            raise forms.ValidationError('Context name can contain letters, numbers, underscore, dash')
        return name


class BulkDIDImportForm(forms.Form):
    csv_file = forms.FileField()
    asterisk_server = forms.ModelChoiceField(queryset=AsteriskServer.objects.filter(is_active=True))
    overwrite_existing = forms.BooleanField(required=False)

    def clean_csv_file(self):
        file = self.cleaned_data['csv_file']
        if not file.name.endswith('.csv'):
            raise forms.ValidationError('File must be a CSV file')
        if file.size > 5 * 1024 * 1024:
            raise forms.ValidationError('File size must be less than 5MB')
        return file


class WebRTCConfigForm(forms.Form):
    stun_server = forms.CharField(max_length=200, initial='stun:stun.l.google.com:19302')
    turn_server = forms.CharField(max_length=200, required=False)
    turn_username = forms.CharField(max_length=100, required=False)
    turn_password = forms.CharField(max_length=100, required=False)
    enable_audio = forms.BooleanField(initial=True, required=False)
    enable_video = forms.BooleanField(initial=False, required=False)


class AsteriskSyncForm(forms.Form):
    SYNC_OPTIONS = [
        ('sync_all', 'Sync All Active Phones to Asterisk'),
        ('cleanup_orphans', 'Remove Orphaned Asterisk Records'),
        ('reset_all_secrets', 'Reset All Phone Secrets'),
        ('verify_sync', 'Verify Asterisk Sync Status'),
    ]
    operation = forms.ChoiceField(choices=SYNC_OPTIONS)
    confirm_operation = forms.BooleanField(required=True)


class PhoneTestForm(forms.Form):
    extension = forms.CharField(max_length=20)
    test_type = forms.ChoiceField(choices=[
        ('registration', 'Check Registration Status'),
        ('ping', 'Ping Phone'),
        ('call_test', 'Initiate Test Call'),
    ])


class AsteriskConfigExportForm(forms.Form):
    CONFIG_TYPES = [
        ('pjsip_endpoints', 'PJSIP Endpoints Only'),
        ('pjsip_complete', 'Complete PJSIP Configuration'),
        ('dialplan', 'Dialplan Extensions'),
        ('complete', 'Complete Configuration'),
    ]
    config_type = forms.ChoiceField(choices=CONFIG_TYPES)
    asterisk_server = forms.ModelChoiceField(queryset=AsteriskServer.objects.filter(is_active=True))
    include_secrets = forms.BooleanField(required=False)

