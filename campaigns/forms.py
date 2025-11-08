# campaigns/forms.py

from django import forms
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.forms import inlineformset_factory
from datetime import datetime, time

from .models import (
    Campaign, CampaignAgent, Disposition, CampaignDisposition, 
    Script, CampaignHours
)
from leads.models import LeadList


class CampaignCreateForm(forms.ModelForm):
    """
    Form for creating new campaigns
    """
    lead_lists = forms.ModelMultipleChoiceField(
        queryset=LeadList.objects.filter(is_active=True),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        help_text="Select lead lists to associate with this campaign"
    )
    
    class Meta:
        model = Campaign
        fields = [
            'name', 'description', 'campaign_type', 'dial_method',
            'start_date', 'end_date', 'daily_start_time', 'daily_end_time',
            'timezone', 'max_attempts', 'call_timeout', 'retry_delay',
            'dial_ratio', 'max_lines', 'abandon_rate', 'enable_recording',
            'recording_delay', 'monitor_agents', 'lead_order',
            'use_internal_dnc', 'use_campaign_dnc', 'amd_enabled',
            # Dialing speed and routing
            'dial_speed', 'custom_dials_per_agent',
            'outbound_carrier', 'dial_prefix'
        ]
        
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter campaign name'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Enter campaign description'
            }),
            'campaign_type': forms.Select(attrs={'class': 'form-select'}),
            'dial_method': forms.Select(attrs={'class': 'form-select'}),
            'start_date': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local'
            }),
            'end_date': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local'
            }),
            'daily_start_time': forms.TimeInput(attrs={
                'class': 'form-control',
                'type': 'time'
            }),
            'daily_end_time': forms.TimeInput(attrs={
                'class': 'form-control',
                'type': 'time'
            }),
            'timezone': forms.Select(attrs={'class': 'form-select'}),
            'max_attempts': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
                'max': 10
            }),
            'call_timeout': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 10,
                'max': 300
            }),
            'retry_delay': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 300,
                'step': 300
            }),
            'dial_ratio': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0.1,
                'max': 10.0,
                'step': 0.1
            }),
            'max_lines': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
                'max': 100
            }),
            'abandon_rate': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0.0,
                'max': 25.0,
                'step': 0.1
            }),
            'recording_delay': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0,
                'max': 10
            }),
            'lead_order': forms.Select(attrs={'class': 'form-select'}),
            'enable_recording': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'monitor_agents': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'use_internal_dnc': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'use_campaign_dnc': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'amd_enabled': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            # New dialing speed & routing widgets
            'dial_speed': forms.Select(attrs={'class': 'form-select'}),
            'custom_dials_per_agent': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
                'max': 20,
                'step': 1,
            }),
            'dial_prefix': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. 0, 91, 001'
            }),
            'outbound_carrier': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set default values
        self.fields['start_date'].initial = timezone.now().replace(
            hour=9, minute=0, second=0, microsecond=0
        )
        self.fields['daily_start_time'].initial = time(9, 0)
        self.fields['daily_end_time'].initial = time(17, 0)
        
        # Set default timezone to India Standard Time
        self.fields['timezone'].initial = 'Asia/Kolkata'

        # Set default lead_order to 'down'
        self.fields['lead_order'].initial = 'down'

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        daily_start_time = cleaned_data.get('daily_start_time')
        daily_end_time = cleaned_data.get('daily_end_time')
        
        # Validate date range
        if start_date and end_date:
            if start_date >= end_date:
                raise ValidationError('End date must be after start date.')
        
        # Validate daily time range
        if daily_start_time and daily_end_time:
            if daily_start_time >= daily_end_time:
                raise ValidationError('Daily end time must be after start time.')
        
        return cleaned_data


class CampaignUpdateForm(CampaignCreateForm):
    """
    Form for updating existing campaigns
    """
    class Meta(CampaignCreateForm.Meta):
        # Remove fields that shouldn't be changed after creation
        fields = [f for f in CampaignCreateForm.Meta.fields if f not in ['campaign_type']]


class CampaignSearchForm(forms.Form):
    """
    Form for searching and filtering campaigns
    """
    search = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search campaigns...'
        })
    )
    
    status = forms.ChoiceField(
        choices=[('', 'All Status')] + Campaign.STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    created_by = forms.ModelChoiceField(
        queryset=User.objects.filter(is_staff=True),
        required=False,
        empty_label="All Creators",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    date_range = forms.ChoiceField(
        choices=[
            ('', 'All Time'),
            ('today', 'Today'),
            ('week', 'This Week'),
            ('month', 'This Month'),
            ('quarter', 'This Quarter'),
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )


class CampaignAgentForm(forms.ModelForm):
    """
    Form for assigning agents to campaigns
    """
    class Meta:
        model = CampaignAgent
        fields = ['max_calls_per_day', 'priority']
        
        widgets = {
            'max_calls_per_day': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
                'max': 1000,
                'placeholder': 'Max calls per day (optional)'
            }),
            'priority': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
                'max': 10,
                'value': 1
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['max_calls_per_day'].required = False
        self.fields['max_calls_per_day'].help_text = "Leave empty for no limit"


class ScriptForm(forms.ModelForm):
    """
    Form for creating and editing scripts
    """
    class Meta:
        model = Script
        fields = ['name', 'script_type', 'content']
        
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter script name'
            }),
            'script_type': forms.Select(attrs={'class': 'form-select'}),
            'content': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 10,
                'placeholder': 'Enter script content...'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['content'].help_text = (
            "You can use variables like {lead_name}, {lead_phone}, "
            "{agent_name}, etc. in your script."
        )


class CampaignHoursForm(forms.ModelForm):
    """
    Form for campaign operating hours
    """
    class Meta:
        model = CampaignHours
        fields = ['day_of_week', 'start_time', 'end_time', 'is_active']
        
        widgets = {
            'day_of_week': forms.Select(attrs={'class': 'form-select'}),
            'start_time': forms.TimeInput(attrs={
                'class': 'form-control',
                'type': 'time'
            }),
            'end_time': forms.TimeInput(attrs={
                'class': 'form-control',
                'type': 'time'
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        start_time = cleaned_data.get('start_time')
        end_time = cleaned_data.get('end_time')
        
        if start_time and end_time:
            if start_time >= end_time:
                raise ValidationError('End time must be after start time.')
        
        return cleaned_data


# Create formset for managing multiple campaign hours
CampaignHoursFormSet = inlineformset_factory(
    Campaign,
    CampaignHours,
    form=CampaignHoursForm,
    fields=['day_of_week', 'start_time', 'end_time', 'is_active'],
    extra=0,
    can_delete=True,
    widgets={
        'day_of_week': forms.Select(attrs={'class': 'form-select form-select-sm'}),
        'start_time': forms.TimeInput(attrs={'class': 'form-control form-control-sm', 'type': 'time'}),
        'end_time': forms.TimeInput(attrs={'class': 'form-control form-control-sm', 'type': 'time'}),
        'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    }
)


class DispositionForm(forms.ModelForm):
    """
    Form for creating and editing dispositions
    """
    class Meta:
        model = Disposition
        fields = [
            'name', 'code', 'category', 'description', 'is_sale',
            'requires_callback', 'callback_delay', 'removes_from_campaign',
            'adds_to_dnc', 'color', 'hotkey'
        ]
        
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter disposition name'
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter unique code'
            }),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Enter description'
            }),
            'callback_delay': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 300,
                'step': 300
            }),
            'color': forms.TextInput(attrs={
                'class': 'form-control',
                'type': 'color'
            }),
            'hotkey': forms.TextInput(attrs={
                'class': 'form-control',
                'maxlength': 1,
                'placeholder': 'Single key'
            }),
            'is_sale': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'requires_callback': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'removes_from_campaign': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'adds_to_dnc': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['callback_delay'].help_text = "Callback delay in seconds"
        self.fields['hotkey'].help_text = "Single character for keyboard shortcuts"

    def clean_code(self):
        code = self.cleaned_data['code'].upper()
        
        # Check for duplicate codes
        existing = Disposition.objects.filter(code=code)
        if self.instance.pk:
            existing = existing.exclude(pk=self.instance.pk)
        
        if existing.exists():
            raise ValidationError('This code is already in use.')
        
        return code

    def clean_hotkey(self):
        hotkey = self.cleaned_data['hotkey']
        
        if hotkey:
            hotkey = hotkey.upper()
            
            # Check for duplicate hotkeys
            existing = Disposition.objects.filter(hotkey=hotkey)
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            
            if existing.exists():
                raise ValidationError('This hotkey is already in use.')
        
        return hotkey


class BulkCampaignActionForm(forms.Form):
    """
    Form for bulk actions on campaigns
    """
    ACTION_CHOICES = [
        ('', 'Select Action'),
        ('activate', 'Activate Selected'),
        ('deactivate', 'Deactivate Selected'),
        ('pause', 'Pause Selected'),
        ('archive', 'Archive Selected'),
        ('delete', 'Delete Selected'),
    ]
    
    action = forms.ChoiceField(
        choices=ACTION_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    campaign_ids = forms.CharField(
        widget=forms.HiddenInput()
    )
    
    confirm = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )

    def clean(self):
        cleaned_data = super().clean()
        action = cleaned_data.get('action')
        confirm = cleaned_data.get('confirm')
        
        if action in ['archive', 'delete'] and not confirm:
            raise ValidationError('You must confirm this action.')
        
        return cleaned_data


class CampaignCloneForm(forms.Form):
    """
    Form for cloning campaigns
    """
    name = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter name for cloned campaign'
        })
    )
    
    description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Enter description (optional)'
        })
    )
    
    clone_agents = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text="Copy agent assignments from original campaign"
    )
    
    clone_scripts = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text="Copy scripts from original campaign"
    )
    
    clone_dispositions = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text="Copy dispositions from original campaign"
    )
    
    clone_hours = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text="Copy operating hours from original campaign"
    )


class CampaignQuickCreateForm(forms.ModelForm):
    """
    Simplified form for quick campaign creation
    """
    class Meta:
        model = Campaign
        fields = ['name', 'description', 'campaign_type', 'dial_method', 'start_date']
        
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Campaign name'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Brief description'
            }),
            'campaign_type': forms.Select(attrs={'class': 'form-select'}),
            'dial_method': forms.Select(attrs={'class': 'form-select'}),
            'start_date': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set sensible defaults
        self.fields['start_date'].initial = timezone.now().replace(
            hour=9, minute=0, second=0, microsecond=0
        )


class CampaignImportForm(forms.Form):
    """
    Form for importing campaigns from CSV/Excel
    """
    file = forms.FileField(
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.csv,.xlsx,.xls'
        }),
        help_text="Upload CSV or Excel file with campaign data"
    )
    
    has_headers = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text="First row contains column headers"
    )
    
    update_existing = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text="Update existing campaigns with matching names"
    )

    def clean_file(self):
        file = self.cleaned_data['file']
        
        # Check file size (max 5MB)
        if file.size > 5 * 1024 * 1024:
            raise ValidationError('File size cannot exceed 5MB.')
        
        # Check file extension
        allowed_extensions = ['.csv', '.xlsx', '.xls']
        file_extension = None
        for ext in allowed_extensions:
            if file.name.lower().endswith(ext):
                file_extension = ext
                break
        
        if not file_extension:
            raise ValidationError(
                f'Invalid file type. Allowed types: {", ".join(allowed_extensions)}'
            )
        
        return file
