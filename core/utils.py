# core/utils.py

import json
import csv
import logging
from datetime import datetime, timedelta
from django.core.cache import cache
from django.conf import settings
from django.contrib.auth.models import User
from django.db.models import Q
from .models import SystemSettings

logger = logging.getLogger(__name__)

class SettingsManager:
    """
    Utility class for managing system settings
    """
    
    @staticmethod
    def get_setting(key, default=None):
        """Get a system setting value"""
        try:
            cache_key = f"setting_{key}"
            value = cache.get(cache_key)
            
            if value is None:
                setting = SystemSettings.objects.filter(key=key, is_active=True).first()
                if setting:
                    value = setting.value
                    cache.set(cache_key, value, 300)  # Cache for 5 minutes
                else:
                    value = default
            
            return value
        except Exception as e:
            logger.error(f"Error getting setting {key}: {e}")
            return default
    
    @staticmethod
    def set_setting(key, value, description=""):
        """Set a system setting value"""
        try:
            setting, created = SystemSettings.objects.get_or_create(
                key=key,
                defaults={'value': value, 'description': description}
            )
            
            if not created:
                setting.value = value
                setting.description = description
                setting.save()
            
            # Clear cache
            cache.delete(f"setting_{key}")
            
            return setting
        except Exception as e:
            logger.error(f"Error setting {key}: {e}")
            return None

class FileHandler:
    """
    Utility class for handling file operations
    """
    
    @staticmethod
    def validate_csv_file(file):
        """Validate CSV file format and structure"""
        try:
            # Check file size
            if file.size > settings.FILE_UPLOAD_MAX_MEMORY_SIZE:
                return False, "File size too large"
            
            # Check file extension
            if not file.name.endswith('.csv'):
                return False, "Invalid file format. Please upload a CSV file"
            
            # Try to read first few lines
            file.seek(0)
            sample = file.read(1024).decode('utf-8')
            file.seek(0)
            
            # Basic CSV structure check
            lines = sample.split('\n')
            if len(lines) < 2:
                return False, "File appears to be empty or invalid"
            
            return True, "Valid CSV file"
        
        except Exception as e:
            return False, f"Error validating file: {str(e)}"
    
    @staticmethod
    def parse_csv_headers(file):
        """Parse and return CSV headers"""
        try:
            file.seek(0)
            reader = csv.reader(file.read().decode('utf-8').splitlines())
            headers = next(reader)
            file.seek(0)
            return [header.strip() for header in headers]
        except Exception as e:
            logger.error(f"Error parsing CSV headers: {e}")
            return []

class PhoneNumberValidator:
    """
    Utility class for phone number validation and formatting
    """
    
    @staticmethod
    def clean_phone_number(phone):
        """Clean and format phone number"""
        if not phone:
            return ""
        
        # Remove all non-numeric characters
        cleaned = ''.join(filter(str.isdigit, str(phone)))
        
        # Remove leading 1 if it's 11 digits
        if len(cleaned) == 11 and cleaned.startswith('1'):
            cleaned = cleaned[1:]
        
        return cleaned
    
    @staticmethod
    def validate_phone_number(phone):
        """Validate phone number format"""
        cleaned = PhoneNumberValidator.clean_phone_number(phone)
        
        if len(cleaned) != 10:
            return False, "Phone number must be 10 digits"
        
        if cleaned[0] in ['0', '1']:
            return False, "Invalid area code"
        
        if cleaned[3] in ['0', '1']:
            return False, "Invalid exchange code"
        
        return True, "Valid phone number"
