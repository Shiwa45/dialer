
# users/forms.py

from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm, PasswordChangeForm
from django.contrib.auth.models import User, Group
from .models import UserProfile

class CustomUserCreationForm(UserCreationForm):
    """
    Custom user creation form with additional fields
    """
    email = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=30, required=True)
    last_name = forms.CharField(max_length=30, required=True)
    
    # Profile fields
    phone_number = forms.CharField(max_length=15, required=True)
    extension = forms.CharField(max_length=10, required=False)
    department = forms.CharField(max_length=100, required=False)
    employee_id = forms.CharField(max_length=20, required=False)
    role = forms.ModelChoiceField(queryset=Group.objects.all(), required=True)
    
    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'password1', 'password2')
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Add CSS classes to all fields
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control'
        
        # Customize specific fields
        self.fields['username'].help_text = 'Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only.'
        self.fields['password1'].help_text = 'Your password must contain at least 8 characters.'
        
    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        
        if commit:
            user.save()
            
            # Update profile
            profile = user.profile
            profile.phone_number = self.cleaned_data['phone_number']
            profile.extension = self.cleaned_data['extension']
            profile.department = self.cleaned_data['department']
            profile.employee_id = self.cleaned_data['employee_id']
            profile.save()
            
            # Add user to selected role
            role = self.cleaned_data['role']
            user.groups.add(role)
            
        return user

class UserProfileForm(forms.ModelForm):
    """
    Form for editing user profile
    """
    first_name = forms.CharField(max_length=30, required=True)
    last_name = forms.CharField(max_length=30, required=True)
    email = forms.EmailField(required=True)
    
    class Meta:
        model = UserProfile
        fields = [
            'employee_id', 'phone_number', 'extension', 'department',
            'skill_level', 'can_make_outbound', 'can_receive_inbound',
            'can_transfer_calls', 'can_conference_calls', 'shift_start',
            'shift_end', 'timezone', 'avatar', 'theme_preference'
        ]
        widgets = {
            'shift_start': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'shift_end': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'avatar': forms.FileInput(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Add CSS classes
        for field_name, field in self.fields.items():
            if field_name not in ['avatar']:
                field.widget.attrs['class'] = 'form-control'
        
        # Initialize user fields if user is provided
        if self.user:
            self.fields['first_name'].initial = self.user.first_name
            self.fields['last_name'].initial = self.user.last_name
            self.fields['email'].initial = self.user.email
    
    def save(self, commit=True):
        profile = super().save(commit=False)
        
        if commit and self.user:
            # Update user fields
            self.user.first_name = self.cleaned_data['first_name']
            self.user.last_name = self.cleaned_data['last_name']
            self.user.email = self.cleaned_data['email']
            self.user.save()
            
            profile.save()
        
        return profile

class CustomPasswordChangeForm(PasswordChangeForm):
    """
    Custom password change form with styling
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control'

class UserSearchForm(forms.Form):
    """
    Form for searching and filtering users
    """
    search = forms.CharField(
        max_length=100, 
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search by name, username, or email...'
        })
    )
    role = forms.ModelChoiceField(
        queryset=Group.objects.all(),
        required=False,
        empty_label="All Roles",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    department = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Department'
        })
    )
    is_active = forms.ChoiceField(
        choices=[
            ('', 'All'),
            ('true', 'Active'),
            ('false', 'Inactive')
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )