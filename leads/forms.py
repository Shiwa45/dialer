# leads/forms.py

from django import forms
from django.contrib.auth.models import User
from django.core.validators import RegexValidator
from django.utils import timezone
from .models import (
    Lead, LeadList, LeadImport, DNCEntry, CallbackSchedule, LeadNote, LeadFilter
)
from campaigns.models import Campaign


class LeadCreateForm(forms.ModelForm):
    """
    Form for creating new leads
    """
    phone_validator = RegexValidator(
        regex=r'^\+?1?\d{9,15}$',
        message="Enter a valid phone number (e.g., (555) 123-4567)"
    )

    phone_number = forms.CharField(
        validators=[phone_validator],
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '(555) 123-4567'
        })
    )
    
    class Meta:
        model = Lead
        fields = [
            'first_name', 'last_name', 'phone_number', 'email', 'company',
            'address', 'city', 'state', 'zip_code', 'lead_list', 'status',
            'priority', 'source', 'comments'
        ]
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'company': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.TextInput(attrs={'class': 'form-control'}),
            'city': forms.TextInput(attrs={'class': 'form-control'}),
            'state': forms.TextInput(attrs={'class': 'form-control'}),
            'zip_code': forms.TextInput(attrs={'class': 'form-control'}),
            'lead_list': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'priority': forms.Select(attrs={'class': 'form-select'}),
            'source': forms.TextInput(attrs={'class': 'form-control'}),
            'comments': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Additional notes about this lead...'
            })
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['lead_list'].queryset = LeadList.objects.filter(is_active=True)
        self.fields['lead_list'].empty_label = "Select Lead List"
        
        # Make certain fields required
        self.fields['first_name'].required = True
        self.fields['last_name'].required = True
        self.fields['phone_number'].required = True
        self.fields['lead_list'].required = True

    def clean_phone_number(self):
        phone_number = self.cleaned_data['phone_number']
        
        # Check if phone is in DNC list
        if DNCEntry.objects.filter(phone_number=phone_number).exists():
            raise forms.ValidationError("This phone number is in the Do Not Call list.")
        
        return phone_number

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email:
            return email.lower()
        return email


class LeadUpdateForm(LeadCreateForm):
    """
    Form for updating existing leads
    """
    class Meta(LeadCreateForm.Meta):
        fields = LeadCreateForm.Meta.fields + ['assigned_user', 'last_contact_date', 'call_count']
        widgets = dict(LeadCreateForm.Meta.widgets)
        widgets.update({
            'assigned_user': forms.Select(attrs={'class': 'form-select'}),
            'last_contact_date': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local'
            }),
            'call_count': forms.NumberInput(attrs={'class': 'form-control', 'readonly': True})
        })

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['assigned_user'].queryset = User.objects.filter(
            groups__name__in=['Agents', 'Supervisors', 'Managers']
        ).distinct()
        self.fields['assigned_user'].empty_label = "Unassigned"

    def clean_phone_number(self):
        phone_number = self.cleaned_data['phone_number']
        
        # Skip DNC check if phone number hasn't changed
        if self.instance and self.instance.phone_number == phone_number:
            return phone_number
        
        # Check if phone is in DNC list for new numbers
        if DNCEntry.objects.filter(phone_number=phone_number).exists():
            raise forms.ValidationError("This phone number is in the Do Not Call list.")
        
        return phone_number


class LeadListCreateForm(forms.ModelForm):
    """
    Form for creating lead lists
    """
    assigned_campaign = forms.ModelChoiceField(
        queryset=Campaign.objects.filter(is_active=True),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="If set, leads in this list will be auto-queued to this campaign."
    )
    class Meta:
        model = LeadList
        fields = ['name', 'description', 'is_active', 'tags', 'assigned_campaign']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter lead list name'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Describe this lead list...'
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'tags': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter tags separated by commas'
            }),
            'assigned_campaign': forms.Select(attrs={'class': 'form-select'})
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['name'].required = True
        self.fields['is_active'].initial = True


class LeadListUpdateForm(LeadListCreateForm):
    """
    Form for updating lead lists
    """
    pass


class LeadImportForm(forms.ModelForm):
    """
    Form for importing leads from files
    """
    FIELD_MAPPING_CHOICES = [
        ('first_name', 'First Name'),
        ('last_name', 'Last Name'),
        ('phone_number', 'Phone Number'),
        ('email', 'Email'),
        ('company', 'Company'),
        ('address', 'Address'),
        ('city', 'City'),
        ('state', 'State'),
        ('zip_code', 'Zip Code'),
        ('source', 'Source'),
        ('comments', 'Comments'),
        ('skip', 'Skip Column'),
    ]
    
    skip_duplicates = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text="Skip leads with duplicate phone numbers"
    )
    
    check_dnc = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text="Skip phone numbers in DNC list"
    )
    class Meta:
        model = LeadImport
        fields = ['name', 'file', 'lead_list', 'skip_duplicates', 'check_dnc']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter import name'
            }),
            'file': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': '.csv,.xlsx,.xls'
            }),
            'lead_list': forms.Select(attrs={'class': 'form-select'})
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['lead_list'].queryset = LeadList.objects.filter(is_active=True)
        self.fields['lead_list'].empty_label = "Select Lead List"
        
        # Make fields required
        self.fields['name'].required = True
        self.fields['file'].required = True
        self.fields['lead_list'].required = True

    def clean_file(self):
        file = self.cleaned_data['file']
        
        # Check file size (limit to 10MB)
        if file.size > 10 * 1024 * 1024:
            raise forms.ValidationError("File size cannot exceed 10MB.")
        
        # Check file extension
        allowed_extensions = ['.csv', '.xlsx', '.xls']
        if not any(file.name.lower().endswith(ext) for ext in allowed_extensions):
            raise forms.ValidationError("File must be CSV or Excel format.")
        
        return file


class CallbackCreateForm(forms.ModelForm):
    """
    Form for scheduling callbacks
    """
    class Meta:
        model = CallbackSchedule
        fields = ['lead', 'agent', 'campaign', 'scheduled_time', 'timezone', 'notes']
        widgets = {
            'lead': forms.Select(attrs={'class': 'form-select'}),
            'agent': forms.Select(attrs={'class': 'form-select'}),
            'campaign': forms.Select(attrs={'class': 'form-select'}),
            'scheduled_time': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local'
            }),
            'timezone': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Callback notes...'
            })
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        self.fields['agent'].queryset = User.objects.filter(
            groups__name__in=['Agents', 'Supervisors']
        ).distinct()
        
        self.fields['campaign'].queryset = Campaign.objects.filter(is_active=True)
        
        # If user is provided, default to current user if they're an agent
        if user and user.groups.filter(name__in=['Agents', 'Supervisors']).exists():
            self.fields['agent'].initial = user

    def clean_scheduled_time(self):
        scheduled_time = self.cleaned_data['scheduled_time']
        
        if scheduled_time <= timezone.now():
            raise forms.ValidationError("Callback time must be in the future.")
        
        return scheduled_time


class LeadSearchForm(forms.Form):
    """
    Form for searching and filtering leads
    """
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search leads...'
        })
    )
    
    status = forms.ChoiceField(
        required=False,
        choices=[('', 'All Statuses')] + Lead.STATUS_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    lead_list = forms.ModelChoiceField(
        required=False,
        queryset=LeadList.objects.all(),
        empty_label="All Lead Lists",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    campaign = forms.ModelChoiceField(
        required=False,
        queryset=Campaign.objects.filter(is_active=True),
        empty_label="All Campaigns",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    assigned_user = forms.ModelChoiceField(
        required=False,
        queryset=User.objects.filter(groups__name__in=['Agents', 'Supervisors']).distinct(),
        empty_label="All Agents",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )
    
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )


class LeadFilterForm(forms.ModelForm):
    """
    Form for creating lead filters
    """
    class Meta:
        model = LeadFilter
        fields = ['name', 'description', 'filter_criteria', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2
            }),
            'filter_criteria': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'JSON filter criteria'
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'})
        }


class BulkActionForm(forms.Form):
    """
    Form for bulk actions on leads
    """
    ACTION_CHOICES = [
        ('delete', 'Delete Selected'),
        ('mark_dnc', 'Mark as DNC'),
        ('assign_list', 'Assign to Lead List'),
        ('change_status', 'Change Status'),
        ('assign_agent', 'Assign Agent'),
    ]
    
    action = forms.ChoiceField(
        choices=ACTION_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    lead_list = forms.ModelChoiceField(
        required=False,
        queryset=LeadList.objects.filter(is_active=True),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    new_status = forms.ChoiceField(
        required=False,
        choices=[('', 'Select Status')] + Lead.STATUS_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    assigned_user = forms.ModelChoiceField(
        required=False,
        queryset=User.objects.filter(groups__name__in=['Agents', 'Supervisors']).distinct(),
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    def clean(self):
        cleaned_data = super().clean()
        action = cleaned_data.get('action')
        
        if action == 'assign_list' and not cleaned_data.get('lead_list'):
            raise forms.ValidationError("Lead list is required for this action.")
        
        if action == 'change_status' and not cleaned_data.get('new_status'):
            raise forms.ValidationError("New status is required for this action.")
        
        if action == 'assign_agent' and not cleaned_data.get('assigned_user'):
            raise forms.ValidationError("Agent is required for this action.")
        
        return cleaned_data


class LeadNoteForm(forms.Form):
    """
    Form for adding notes to leads
    """
    note = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Add a note about this lead...'
        })
    )
    
    is_important = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text="Mark as important note"
    )


from django import forms
from django.core.validators import RegexValidator
from .models import LeadList  # Adjust the import as needed

class QuickLeadForm(forms.Form):
    """
    Quick form for adding leads during calls
    """
    first_name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'First Name'
        })
    )

    last_name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Last Name'
        })
    )

    phone_number = forms.CharField(
        validators=[RegexValidator(
            regex=r'^\+?1?\d{9,15}$',
            message="Enter a valid phone number"
        )],
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '(555) 123-4567'
        })
    )
    lead_list = forms.ModelChoiceField(
        queryset=LeadList.objects.filter(is_active=True),
        widget=forms.Select(attrs={'class': 'form-select'})
    )


class RecycleLeadsForm(forms.Form):
    """
    Form for recycling leads based on status
    """
    source_statuses = forms.MultipleChoiceField(
        choices=[
            ('busy', 'Busy'),
            ('no_answer', 'No Answer'),
            ('not_interested', 'Not Interested'),
            ('failed', 'Failed'),
            ('other', 'Other'),
            ('dnc', 'Do Not Call (DNC)'),
        ],
        widget=forms.CheckboxSelectMultiple,
        help_text="Select the statuses you want to reset to 'New'."
    )
    
    reset_call_count = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text="Reset"
    )

    def clean_source_statuses(self):
        statuses = self.cleaned_data['source_statuses']
        if not statuses:
            raise forms.ValidationError("Please select at least one status to recycle.")
        return statuses
