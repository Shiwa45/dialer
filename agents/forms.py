# agents/forms.py

from django import forms
from django.contrib.auth.models import User
from django.core.validators import RegexValidator
from django.utils import timezone
from django.db.models import Q
from .models import (
    AgentQueue, AgentScript, AgentHotkey, AgentBreakCode,
    AgentSkill, AgentPerformanceGoal, AgentNote, 
    AgentCallbackTask
)
from campaigns.models import Campaign, Disposition
from leads.models import Lead
from users.models import AgentStatus


class AgentStatusForm(forms.Form):
    """
    Form for changing agent status
    """
    STATUS_CHOICES = AgentStatus.STATUS_CHOICES
    
    status = forms.ChoiceField(
        choices=STATUS_CHOICES,
        widget=forms.Select(attrs={
            'class': 'form-select',
            'id': 'agent-status-select'
        })
    )
    
    break_reason = forms.CharField(
        required=False,
        max_length=100,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Break reason (optional)',
            'id': 'break-reason-input'
        })
    )


class CallControlForm(forms.Form):
    """
    Form for call control actions
    """
    ACTION_CHOICES = [
        ('answer', 'Answer'),
        ('hangup', 'Hangup'),
        ('hold', 'Hold'),
        ('unhold', 'Unhold'),
        ('mute', 'Mute'),
        ('unmute', 'Unmute'),
        ('transfer', 'Transfer'),
        ('conference', 'Conference'),
    ]
    
    action = forms.ChoiceField(
        choices=ACTION_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    call_id = forms.CharField(
        widget=forms.HiddenInput()
    )
    
    transfer_to = forms.CharField(
        required=False,
        max_length=20,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Transfer to number/extension'
        })
    )
    
    transfer_type = forms.ChoiceField(
        required=False,
        choices=[
            ('warm', 'Warm Transfer'),
            ('cold', 'Cold Transfer'),
            ('conference', 'Conference Transfer')
        ],
        widget=forms.Select(attrs={'class': 'form-select'})
    )


class DispositionForm(forms.Form):
    """
    Form for setting call disposition
    """
    def __init__(self, *args, **kwargs):
        campaign = kwargs.pop('campaign', None)
        super().__init__(*args, **kwargs)
        
        if campaign:
            self.fields['disposition'].queryset = Disposition.objects.filter(
                campaign=campaign,
                is_active=True
            ).order_by('sort_order')
        else:
            self.fields['disposition'].queryset = Disposition.objects.none()
    
    disposition = forms.ModelChoiceField(
        queryset=Disposition.objects.none(),
        empty_label="Select Disposition",
        widget=forms.Select(attrs={
            'class': 'form-select',
            'required': True
        })
    )
    
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Disposition notes (optional)'
        })
    )
    
    call_id = forms.CharField(
        widget=forms.HiddenInput()
    )


class CallbackScheduleForm(forms.Form):
    """
    Form for scheduling callbacks
    """
    PRIORITY_CHOICES = [
        (1, 'Low'),
        (2, 'Normal'),
        (3, 'High'),
        (4, 'Urgent'),
    ]
    
    callback_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date',
            'min': timezone.now().date().isoformat()
        })
    )
    
    callback_time = forms.TimeField(
        widget=forms.TimeInput(attrs={
            'class': 'form-control',
            'type': 'time'
        })
    )
    
    priority = forms.ChoiceField(
        choices=PRIORITY_CHOICES,
        initial=2,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Callback notes and reason'
        })
    )
    
    lead_id = forms.CharField(
        widget=forms.HiddenInput()
    )
    
    def clean(self):
        cleaned_data = super().clean()
        callback_date = cleaned_data.get('callback_date')
        callback_time = cleaned_data.get('callback_time')
        
        if callback_date and callback_time:
            callback_datetime = timezone.datetime.combine(callback_date, callback_time)
            callback_datetime = timezone.make_aware(callback_datetime)
            
            if callback_datetime <= timezone.now():
                raise forms.ValidationError("Callback time must be in the future.")
            
            cleaned_data['callback_datetime'] = callback_datetime
        
        return cleaned_data


class AgentScriptForm(forms.ModelForm):
    """
    Form for creating/editing agent scripts
    """
    class Meta:
        model = AgentScript
        fields = [
            'name', 'script_type', 'content', 'campaign', 'is_global',
            'is_active', 'display_order', 'auto_display'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'script_type': forms.Select(attrs={'class': 'form-select'}),
            'content': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 8,
                'placeholder': 'Use variables like {first_name}, {last_name}, {company}'
            }),
            'campaign': forms.Select(attrs={'class': 'form-select'}),
            'is_global': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'display_order': forms.NumberInput(attrs={'class': 'form-control'}),
            'auto_display': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['campaign'].queryset = Campaign.objects.filter(is_active=True)
        self.fields['campaign'].empty_label = "All Campaigns (Global)"
        self.fields['campaign'].required = False


class AgentHotkeyForm(forms.ModelForm):
    """
    Form for configuring agent hotkeys
    """
    class Meta:
        model = AgentHotkey
        fields = [
            'key_combination', 'action_type', 'disposition', 
            'transfer_number', 'script', 'description', 'is_active'
        ]
        widgets = {
            'key_combination': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Ctrl+1, Alt+S'
            }),
            'action_type': forms.Select(attrs={'class': 'form-select'}),
            'disposition': forms.Select(attrs={'class': 'form-select'}),
            'transfer_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Extension or phone number'
            }),
            'script': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Hotkey description'
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def __init__(self, *args, **kwargs):
        agent = kwargs.pop('agent', None)
        super().__init__(*args, **kwargs)
        
        if agent:
            # Filter dispositions by agent's assigned campaigns
            assigned_campaigns = Campaign.objects.filter(
                agent_assignments__agent=agent,
                agent_assignments__is_active=True
            )
            self.fields['disposition'].queryset = Disposition.objects.filter(
                campaign__in=assigned_campaigns,
                is_active=True
            )
            
            # Filter scripts by agent's assigned campaigns
            self.fields['script'].queryset = AgentScript.objects.filter(
                Q(campaign__in=assigned_campaigns) | Q(is_global=True),
                is_active=True
            )
        
        self.fields['disposition'].empty_label = "Select Disposition"
        self.fields['script'].empty_label = "Select Script"
        self.fields['disposition'].required = False
        self.fields['transfer_number'].required = False
        self.fields['script'].required = False
    
    def clean(self):
        cleaned_data = super().clean()
        action_type = cleaned_data.get('action_type')
        
        # Validate required fields based on action type
        if action_type == 'disposition' and not cleaned_data.get('disposition'):
            self.add_error('disposition', 'Disposition is required for disposition actions.')
        
        if action_type == 'transfer' and not cleaned_data.get('transfer_number'):
            self.add_error('transfer_number', 'Transfer number is required for transfer actions.')
        
        if action_type == 'script' and not cleaned_data.get('script'):
            self.add_error('script', 'Script is required for script actions.')
        
        return cleaned_data


class AgentQueueForm(forms.ModelForm):
    """
    Form for managing agent queue assignments
    """
    class Meta:
        model = AgentQueue
        fields = [
            'campaign', 'is_active', 'priority', 'max_concurrent_calls',
            'wrap_up_time', 'auto_answer', 'receive_inbound', 'make_outbound'
        ]
        widgets = {
            'campaign': forms.Select(attrs={'class': 'form-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'priority': forms.NumberInput(attrs={'class': 'form-control'}),
            'max_concurrent_calls': forms.NumberInput(attrs={'class': 'form-control'}),
            'wrap_up_time': forms.NumberInput(attrs={'class': 'form-control'}),
            'auto_answer': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'receive_inbound': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'make_outbound': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['campaign'].queryset = Campaign.objects.filter(is_active=True)


class AgentSkillForm(forms.ModelForm):
    """
    Form for managing agent skills
    """
    class Meta:
        model = AgentSkill
        fields = [
            'skill_name', 'proficiency_level', 'certified', 
            'certification_date', 'certification_expires',
            'can_train_others', 'is_active', 'notes'
        ]
        widgets = {
            'skill_name': forms.TextInput(attrs={'class': 'form-control'}),
            'proficiency_level': forms.Select(attrs={'class': 'form-select'}),
            'certified': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'certification_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'certification_expires': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'can_train_others': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3
            }),
        }


class AgentPerformanceGoalForm(forms.ModelForm):
    """
    Form for setting agent performance goals
    """
    class Meta:
        model = AgentPerformanceGoal
        fields = [
            'goal_type', 'period_type', 'target_value', 
            'start_date', 'end_date', 'is_active', 'notes'
        ]
        widgets = {
            'goal_type': forms.Select(attrs={'class': 'form-select'}),
            'period_type': forms.Select(attrs={'class': 'form-select'}),
            'target_value': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01'
            }),
            'start_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'end_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3
            }),
        }


class AgentNoteForm(forms.ModelForm):
    """
    Form for creating agent notes
    """
    class Meta:
        model = AgentNote
        fields = [
            'note_type', 'subject', 'content', 
            'is_private', 'is_important'
        ]
        widgets = {
            'note_type': forms.Select(attrs={'class': 'form-select'}),
            'subject': forms.TextInput(attrs={'class': 'form-control'}),
            'content': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 5
            }),
            'is_private': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_important': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class QuickDialForm(forms.Form):
    """
    Form for quick dialing
    """
    phone_validator = RegexValidator(
        regex=r'^\+?1?\d{9,15}',
        message="Enter a valid phone number"
    )
    
    phone_number = forms.CharField(
        validators=[phone_validator],
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '(555) 123-4567',
            'id': 'quick-dial-number'
        })
    )
    
    campaign = forms.ModelChoiceField(
        queryset=Campaign.objects.filter(is_active=True),
        empty_label="Select Campaign (Optional)",
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )


class LeadSearchForm(forms.Form):
    """
    Form for searching leads in agent interface
    """
    search_term = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search by name, phone, or email...',
            'id': 'lead-search-input'
        })
    )
    
    campaign = forms.ModelChoiceField(
        queryset=Campaign.objects.filter(is_active=True),
        empty_label="All Campaigns",
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    status = forms.ChoiceField(
        choices=[('', 'All Statuses')] + Lead.STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )


class WebRTCConfigForm(forms.Form):
    """
    Form for WebRTC configuration
    """
    sip_server = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'SIP Server URL'
        })
    )
    
    sip_username = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'SIP Username/Extension'
        })
    )
    
    sip_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'SIP Password'
        })
    )
    
    auto_answer = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    enable_video = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )


class CallTransferForm(forms.Form):
    """
    Form for call transfers
    """
    TRANSFER_TYPES = [
        ('warm', 'Warm Transfer'),
        ('cold', 'Cold Transfer'),
        ('conference', 'Conference Transfer'),
    ]
    
    transfer_to = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Extension or phone number'
        })
    )
    
    transfer_type = forms.ChoiceField(
        choices=TRANSFER_TYPES,
        initial='warm',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    reason = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': 'Transfer reason (optional)'
        })
    )
    
    call_id = forms.CharField(
        widget=forms.HiddenInput()
    )


class BreakRequestForm(forms.Form):
    """
    Form for requesting breaks
    """
    break_code = forms.ModelChoiceField(
        queryset=AgentBreakCode.objects.filter(is_active=True),
        empty_label="Select Break Type",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    duration = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=120,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Duration in minutes (optional)'
        })
    )
    
    reason = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': 'Additional reason (optional)'
        })
    )


class CampaignSelectionForm(forms.Form):
    """
    Form for selecting active campaign
    """
    campaign = forms.ModelChoiceField(
        queryset=Campaign.objects.none(),
        empty_label="Select Campaign",
        widget=forms.Select(attrs={
            'class': 'form-select',
            'id': 'campaign-selector'
        })
    )
    
    def __init__(self, *args, **kwargs):
        agent = kwargs.pop('agent', None)
        super().__init__(*args, **kwargs)
        
        if agent:
            # Only show campaigns assigned to this agent
            self.fields['campaign'].queryset = Campaign.objects.filter(
                agent_assignments__agent=agent,
                agent_assignments__is_active=True,
                status='active'
            )


class AgentLoginForm(forms.Form):
    """
    Form for agent session login
    """
    campaign = forms.ModelChoiceField(
        queryset=Campaign.objects.none(),
        empty_label="Select Campaign",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    phone_extension = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Phone extension (optional)'
        })
    )
    
    auto_answer = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    def __init__(self, *args, **kwargs):
        agent = kwargs.pop('agent', None)
        super().__init__(*args, **kwargs)
        
        if agent:
            self.fields['campaign'].queryset = Campaign.objects.filter(
                agent_assignments__agent=agent,
                agent_assignments__is_active=True,
                status='active'
            )


class CallNotesForm(forms.Form):
    """
    Form for adding call notes
    """
    notes = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 4,
            'placeholder': 'Add notes about this call...'
        })
    )
    
    call_id = forms.CharField(
        widget=forms.HiddenInput()
    )
    
    is_important = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )


class LeadUpdateForm(forms.Form):
    """
    Quick form for updating lead information during call
    """
    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={'class': 'form-control'})
    )
    
    company = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    
    address = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    
    city = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    
    state = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    
    zip_code = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    
    comments = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3
        })
    )
    
    lead_id = forms.CharField(
        widget=forms.HiddenInput()
    )