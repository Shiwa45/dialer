# leads/utils.py

import re
import csv
import io
import pandas as pd
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import datetime, timedelta
import phonenumbers
from phonenumbers import NumberParseException


def validate_phone_number(phone_number, country_code='US'):
    """
    Validate phone number using phonenumbers library
    """
    try:
        parsed_number = phonenumbers.parse(phone_number, country_code)
        if phonenumbers.is_valid_number(parsed_number):
            # Format the number consistently
            formatted_number = phonenumbers.format_number(
                parsed_number, 
                phonenumbers.PhoneNumberFormat.NATIONAL
            )
            return True, formatted_number
        else:
            return False, "Invalid phone number"
    except NumberParseException as e:
        return False, f"Phone number parse error: {str(e)}"


def clean_phone_number(phone_number):
    """
    Clean and format phone number
    """
    if not phone_number:
        return None
    
    # Remove all non-digit characters
    digits_only = re.sub(r'\D', '', phone_number)
    
    # Handle different US phone number formats
    if len(digits_only) == 10:
        # Format as (XXX) XXX-XXXX
        return f"({digits_only[:3]}) {digits_only[3:6]}-{digits_only[6:]}"
    elif len(digits_only) == 11 and digits_only.startswith('1'):
        # Remove leading 1 and format
        digits_only = digits_only[1:]
        return f"({digits_only[:3]}) {digits_only[3:6]}-{digits_only[6:]}"
    else:
        # Return as-is if it doesn't match expected patterns
        return phone_number


def validate_email(email):
    """
    Validate email address
    """
    if not email:
        return True, email
    
    email_pattern = re.compile(
        r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    )
    
    if email_pattern.match(email):
        return True, email.lower()
    else:
        return False, "Invalid email format"


def parse_csv_file(file_path, encoding='utf-8'):
    """
    Parse CSV file and return headers and sample data
    """
    try:
        with open(file_path, 'r', encoding=encoding) as file:
            # Try to detect delimiter
            sample = file.read(1024)
            file.seek(0)
            
            sniffer = csv.Sniffer()
            delimiter = sniffer.sniff(sample).delimiter
            
            reader = csv.reader(file, delimiter=delimiter)
            headers = next(reader)
            
            # Get sample rows
            sample_rows = []
            for i, row in enumerate(reader):
                if i >= 5:  # Limit to first 5 rows
                    break
                sample_rows.append(row)
            
            return True, {
                'headers': [h.strip() for h in headers],
                'sample_data': sample_rows,
                'delimiter': delimiter
            }
    
    except Exception as e:
        return False, f"Error parsing CSV: {str(e)}"


def parse_excel_file(file_path):
    """
    Parse Excel file and return headers and sample data
    """
    try:
        df = pd.read_excel(file_path, nrows=5)
        
        return True, {
            'headers': df.columns.tolist(),
            'sample_data': df.values.tolist(),
            'total_rows': len(pd.read_excel(file_path, usecols=[0]))
        }
    
    except Exception as e:
        return False, f"Error parsing Excel: {str(e)}"


def detect_field_mapping(header_name):
    """
    Auto-detect field mapping based on header name
    """
    header_lower = header_name.lower().strip()
    
    mapping = {
        'first_name': ['first name', 'firstname', 'fname', 'first'],
        'last_name': ['last name', 'lastname', 'lname', 'last', 'surname'],
        'phone_number': ['phone', 'phone number', 'telephone', 'tel', 'mobile', 'cell'],
        'email': ['email', 'email address', 'e-mail', 'mail'],
        'company': ['company', 'business', 'organization', 'org'],
        'address': ['address', 'street', 'street address'],
        'city': ['city', 'town'],
        'state': ['state', 'province', 'region'],
        'zip_code': ['zip', 'zipcode', 'postal', 'postal code'],
        'source': ['source', 'lead source', 'origin'],
        'comments': ['comments', 'notes', 'remarks', 'description']
    }
    
    for field, patterns in mapping.items():
        if any(pattern in header_lower for pattern in patterns):
            return field
    
    return 'skip'


def validate_lead_data(lead_data):
    """
    Validate lead data before import
    """
    errors = []
    
    # Required fields
    if not lead_data.get('first_name'):
        errors.append("First name is required")
    
    if not lead_data.get('last_name'):
        errors.append("Last name is required")
    
    if not lead_data.get('phone_number'):
        errors.append("Phone number is required")
    
    # Validate phone number
    if lead_data.get('phone_number'):
        is_valid, message = validate_phone_number(lead_data['phone_number'])
        if not is_valid:
            errors.append(f"Phone: {message}")
        else:
            lead_data['phone_number'] = message
    
    # Validate email
    if lead_data.get('email'):
        is_valid, message = validate_email(lead_data['email'])
        if not is_valid:
            errors.append(f"Email: {message}")
        else:
            lead_data['email'] = message
    
    return len(errors) == 0, errors, lead_data


def check_duplicate_lead(phone_number, email=None, exclude_id=None):
    """
    Check for duplicate leads
    """
    from .models import Lead
    
    queryset = Lead.objects.none()
    
    if phone_number:
        phone_duplicates = Lead.objects.filter(phone_number=phone_number)
        if exclude_id:
            phone_duplicates = phone_duplicates.exclude(id=exclude_id)
        queryset = queryset | phone_duplicates
    
    if email:
        email_duplicates = Lead.objects.filter(email__iexact=email)
        if exclude_id:
            email_duplicates = email_duplicates.exclude(id=exclude_id)
        queryset = queryset | email_duplicates
    
    return queryset.distinct()


def check_dnc_status(phone_number):
    """
    Check if phone number is in DNC list
    """
    from .models import DNCEntry
    
    return DNCEntry.objects.filter(phone_number=phone_number).exists()


def format_import_summary(import_obj):
    """
    Format import summary for display
    """
    summary = {
        'total_rows': import_obj.total_rows,
        'processed_rows': import_obj.processed_rows,
        'successful_imports': import_obj.successful_imports,
        'failed_imports': import_obj.failed_imports,
        'duplicate_count': import_obj.duplicate_count,
        'progress_percentage': import_obj.progress_percentage(),
        'status': import_obj.get_status_display(),
        'error_message': import_obj.error_message,
    }
    
    if import_obj.total_rows > 0:
        summary['success_rate'] = round(
            (import_obj.successful_imports / import_obj.total_rows) * 100, 2
        )
    else:
        summary['success_rate'] = 0
    
    return summary


def generate_lead_report(lead_queryset, report_type='basic'):
    """
    Generate lead reports
    """
    stats = {
        'total_leads': lead_queryset.count(),
        'status_breakdown': {},
        'priority_breakdown': {},
        'source_breakdown': {},
        'creation_timeline': {},
    }
    
    # Status breakdown
    from django.db.models import Count
    status_counts = lead_queryset.values('status').annotate(count=Count('status'))
    for item in status_counts:
        stats['status_breakdown'][item['status']] = item['count']
    
    # Priority breakdown
    priority_counts = lead_queryset.values('priority').annotate(count=Count('priority'))
    for item in priority_counts:
        stats['priority_breakdown'][item['priority']] = item['count']
    
    # Source breakdown
    source_counts = lead_queryset.values('source').annotate(count=Count('source'))
    for item in source_counts:
        source = item['source'] or 'Unknown'
        stats['source_breakdown'][source] = item['count']
    
    if report_type == 'detailed':
        # Add more detailed statistics
        today = timezone.now().date()
        
        stats['daily_stats'] = {
            'created_today': lead_queryset.filter(created_at__date=today).count(),
            'contacted_today': lead_queryset.filter(last_contact_date__date=today).count(),
            'callbacks_due': lead_queryset.filter(
                status='callback',
                callbacks__scheduled_time__date=today,
                callbacks__is_completed=False
            ).count(),
        }
        
        # Conversion rates
        total = stats['total_leads']
        if total > 0:
            stats['conversion_rates'] = {
                'contact_rate': round((stats['status_breakdown'].get('contacted', 0) / total) * 100, 2),
                'sale_rate': round((stats['status_breakdown'].get('sale', 0) / total) * 100, 2),
                'callback_rate': round((stats['status_breakdown'].get('callback', 0) / total) * 100, 2),
                'dnc_rate': round((stats['status_breakdown'].get('dnc', 0) / total) * 100, 2),
            }
        else:
            stats['conversion_rates'] = {
                'contact_rate': 0,
                'sale_rate': 0,
                'callback_rate': 0,
                'dnc_rate': 0,
            }
    
    return stats


def export_leads_to_csv(lead_queryset, include_notes=False):
    """
    Export leads to CSV format
    """
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header row
    headers = [
        'First Name', 'Last Name', 'Phone Number', 'Email', 'Company',
        'Address', 'City', 'State', 'ZIP Code', 'Status', 'Priority',
        'Source', 'Lead List', 'Assigned User', 'Call Count',
        'Created Date', 'Last Contact Date', 'Comments'
    ]
    
    if include_notes:
        headers.append('Latest Note')
    
    writer.writerow(headers)
    
    # Data rows
    for lead in lead_queryset.select_related('lead_list', 'assigned_user'):
        row = [
            lead.first_name,
            lead.last_name,
            lead.phone_number,
            lead.email or '',
            lead.company or '',
            lead.address or '',
            lead.city or '',
            lead.state or '',
            lead.zip_code or '',
            lead.get_status_display(),
            lead.get_priority_display(),
            lead.source or '',
            lead.lead_list.name if lead.lead_list else '',
            lead.assigned_user.get_full_name() if lead.assigned_user else '',
            lead.call_count or 0,
            lead.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            lead.last_contact_date.strftime('%Y-%m-%d %H:%M:%S') if lead.last_contact_date else '',
            lead.comments or ''
        ]
        
        if include_notes:
            latest_note = lead.get_latest_note()
            row.append(latest_note.note if latest_note else '')
        
        writer.writerow(row)
    
    return output.getvalue()


def schedule_lead_recycling():
    """
    Schedule leads for recycling based on rules
    """
    from .models import LeadRecyclingRule, Lead
    
    recycled_count = 0
    rules = LeadRecyclingRule.objects.filter(is_active=True)
    
    for rule in rules:
        # Calculate cutoff date
        cutoff_date = timezone.now() - timedelta(days=rule.days_since_contact)
        
        # Find leads matching criteria
        leads_to_recycle = Lead.objects.filter(
            status=rule.source_status,
            last_contact_date__lte=cutoff_date,
            call_count__lt=rule.max_attempts
        )
        
        # Update leads
        updated_count = leads_to_recycle.update(
            status=rule.target_status,
            call_count=0,  # Reset call count
            last_contact_date=None
        )
        
        recycled_count += updated_count
    
    return recycled_count


def send_callback_reminders():
    """
    Send reminders for upcoming callbacks
    """
    from .models import CallbackSchedule
    from django.core.mail import send_mail
    from django.conf import settings
    
    # Get callbacks due in the next hour
    now = timezone.now()
    reminder_time = now + timedelta(hours=1)
    
    callbacks = CallbackSchedule.objects.filter(
        scheduled_time__lte=reminder_time,
        scheduled_time__gte=now,
        is_completed=False,
        reminder_sent=False
    ).select_related('lead', 'agent', 'campaign')
    
    reminder_count = 0
    
    for callback in callbacks:
        try:
            subject = f'Callback Reminder: {callback.lead.get_full_name()}'
            message = f"""
            Callback Reminder
            
            Lead: {callback.lead.get_full_name()}
            Phone: {callback.lead.phone_number}
            Campaign: {callback.campaign.name}
            Scheduled Time: {callback.scheduled_time.strftime('%Y-%m-%d %H:%M')}
            
            Notes: {callback.notes}
            """
            
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [callback.agent.email],
                fail_silently=True
            )
            
            callback.reminder_sent = True
            callback.save()
            reminder_count += 1
            
        except Exception as e:
            print(f"Error sending callback reminder: {str(e)}")
    
    return reminder_count


def calculate_lead_score(lead):
    """
    Calculate lead score based on various factors
    """
    score = 0
    
    # Base score
    score += 10
    
    # Priority bonus
    if lead.priority == 'high':
        score += 20
    elif lead.priority == 'medium':
        score += 10
    
    # Source bonus
    source_scores = {
        'referral': 15,
        'website': 10,
        'advertisement': 8,
        'cold_call': 5,
        'import': 3
    }
    score += source_scores.get(lead.source, 0)
    
    # Recency bonus (newer leads get higher scores)
    days_old = lead.days_since_created()
    if days_old <= 1:
        score += 15
    elif days_old <= 7:
        score += 10
    elif days_old <= 30:
        score += 5
    
    # Company bonus
    if lead.company:
        score += 5
    
    # Email bonus
    if lead.email:
        score += 5
    
    # Previous contact penalty
    if lead.call_count > 0:
        score -= min(lead.call_count * 2, 10)
    
    # Status adjustments
    status_adjustments = {
        'new': 0,
        'contacted': -5,
        'callback': 10,
        'not_interested': -20,
        'dnc': -50,
        'sale': -100  # Already converted
    }
    score += status_adjustments.get(lead.status, 0)
    
    return max(score, 0)  # Don't allow negative scores


def get_lead_recommendations(agent_user, limit=10):
    """
    Get recommended leads for an agent
    """
    from .models import Lead
    
    # Get leads assigned to agent or unassigned
    leads = Lead.objects.filter(
        models.Q(assigned_user=agent_user) | models.Q(assigned_user__isnull=True),
        status__in=['new', 'callback'],
        lead_list__is_active=True
    ).select_related('lead_list')
    
    # Calculate scores and sort
    lead_scores = []
    for lead in leads:
        score = calculate_lead_score(lead)
        lead_scores.append((lead, score))
    
    # Sort by score (highest first) and return top leads
    lead_scores.sort(key=lambda x: x[1], reverse=True)
    return [lead for lead, score in lead_scores[:limit]]


def cleanup_old_data():
    """
    Clean up old data to free up space
    """
    from .models import LeadImport, LeadNote
    import os
    
    # Delete old import files (older than 30 days)
    cutoff_date = timezone.now() - timedelta(days=30)
    old_imports = LeadImport.objects.filter(created_at__lt=cutoff_date)
    
    deleted_files = 0
    for import_obj in old_imports:
        try:
            if import_obj.file and os.path.exists(import_obj.file.path):
                os.remove(import_obj.file.path)
                deleted_files += 1
        except Exception as e:
            print(f"Error deleting file {import_obj.file}: {str(e)}")
    
    # Delete the import records
    deleted_imports = old_imports.delete()[0]
    
    # Clean up old notes (keep only last 100 per lead)
    from django.db.models import Subquery, OuterRef
    
    leads_with_many_notes = Lead.objects.annotate(
        note_count=Count('notes')
    ).filter(note_count__gt=100)
    
    deleted_notes = 0
    for lead in leads_with_many_notes:
        # Keep only the 100 most recent notes
        notes_to_keep = lead.notes.order_by('-created_at')[:100].values_list('id', flat=True)
        old_notes = lead.notes.exclude(id__in=notes_to_keep)
        deleted_notes += old_notes.count()
        old_notes.delete()
    
    return {
        'deleted_files': deleted_files,
        'deleted_imports': deleted_imports,
        'deleted_notes': deleted_notes
    }


def generate_phone_variations(phone_number):
    """
    Generate different phone number variations for better duplicate detection
    """
    if not phone_number:
        return []
    
    # Remove all non-digit characters
    digits_only = re.sub(r'\D', '', phone_number)
    
    variations = []
    
    if len(digits_only) == 10:
        # Add different formats for 10-digit numbers
        variations.extend([
            digits_only,
            f"({digits_only[:3]}) {digits_only[3:6]}-{digits_only[6:]}",
            f"{digits_only[:3]}-{digits_only[3:6]}-{digits_only[6:]}",
            f"{digits_only[:3]}.{digits_only[3:6]}.{digits_only[6:]}",
            f"1{digits_only}",
            f"+1{digits_only}",
        ])
    elif len(digits_only) == 11 and digits_only.startswith('1'):
        # Handle 11-digit numbers starting with 1
        ten_digit = digits_only[1:]
        variations.extend([
            digits_only,
            ten_digit,
            f"({ten_digit[:3]}) {ten_digit[3:6]}-{ten_digit[6:]}",
            f"{ten_digit[:3]}-{ten_digit[3:6]}-{ten_digit[6:]}",
            f"+{digits_only}",
        ])
    
    return list(set(variations))  # Remove duplicates


def validate_import_file(file):
    """
    Validate uploaded import file
    """
    errors = []
    
    # Check file size (10MB limit)
    if file.size > 10 * 1024 * 1024:
        errors.append("File size exceeds 10MB limit")
    
    # Check file extension
    allowed_extensions = ['.csv', '.xlsx', '.xls']
    file_extension = os.path.splitext(file.name)[1].lower()
    if file_extension not in allowed_extensions:
        errors.append("File must be CSV or Excel format")
    
    # Try to read the file to check if it's valid
    try:
        if file_extension == '.csv':
            # Try to read first few lines of CSV
            file.seek(0)
            sample = file.read(1024).decode('utf-8')
            file.seek(0)
            
            # Check if it has some structure
            lines = sample.split('\n')
            if len(lines) < 2:
                errors.append("CSV file appears to be empty or invalid")
        else:
            # Try to read Excel file
            file.seek(0)
            df = pd.read_excel(file, nrows=1)
            if df.empty:
                errors.append("Excel file appears to be empty")
            file.seek(0)
    
    except Exception as e:
        errors.append(f"Unable to read file: {str(e)}")
    
    return len(errors) == 0, errors


class LeadImportProcessor:
    """
    Class to handle lead import processing
    """
    
    def __init__(self, import_obj):
        self.import_obj = import_obj
        self.processed_count = 0
        self.success_count = 0
        self.error_count = 0
        self.duplicate_count = 0
        self.errors = []
    
    def process(self):
        """
        Main processing method
        """
        try:
            self.import_obj.status = 'processing'
            self.import_obj.save()
            
            if self.import_obj.file.name.endswith('.csv'):
                self._process_csv()
            else:
                self._process_excel()
            
            self.import_obj.status = 'completed'
            self.import_obj.successful_imports = self.success_count
            self.import_obj.failed_imports = self.error_count
            self.import_obj.duplicate_count = self.duplicate_count
            self.import_obj.save()
            
        except Exception as e:
            self.import_obj.status = 'failed'
            self.import_obj.error_message = str(e)
            self.import_obj.save()
            raise
    
    def _process_csv(self):
        """Process CSV file"""
        with open(self.import_obj.file.path, 'r', encoding='utf-8-sig') as file:
            reader = csv.DictReader(file)
            total_rows = sum(1 for _ in reader)
            file.seek(0)
            reader = csv.DictReader(file)
            
            self.import_obj.total_rows = total_rows
            self.import_obj.save()
            
            for row in reader:
                self._process_row(row)
    
    def _process_excel(self):
        """Process Excel file"""
        df = pd.read_excel(self.import_obj.file.path)
        self.import_obj.total_rows = len(df)
        self.import_obj.save()
        
        for _, row in df.iterrows():
            row_dict = row.to_dict()
            self._process_row(row_dict)
    
    def _process_row(self, row_data):
        """Process a single row of data"""
        self.processed_count += 1
        
        try:
            # Extract and clean data
            lead_data = self._extract_lead_data(row_data)
            
            # Validate data
            is_valid, errors, cleaned_data = validate_lead_data(lead_data)
            if not is_valid:
                self.error_count += 1
                self.errors.extend(errors)
                return
            
            # Check for duplicates
            if self.import_obj.skip_duplicates:
                if check_duplicate_lead(cleaned_data['phone_number']).exists():
                    self.duplicate_count += 1
                    return
            
            # Check DNC
            if self.import_obj.check_dnc:
                if check_dnc_status(cleaned_data['phone_number']):
                    self.error_count += 1
                    return
            
            # Create lead
            from .models import Lead
            Lead.objects.create(
                **cleaned_data,
                lead_list=self.import_obj.lead_list,
                created_by=self.import_obj.user
            )
            
            self.success_count += 1
            
        except Exception as e:
            self.error_count += 1
            self.errors.append(f"Row {self.processed_count}: {str(e)}")
        
        # Update progress periodically
        if self.processed_count % 100 == 0:
            self.import_obj.processed_rows = self.processed_count
            self.import_obj.save()
    
    def _extract_lead_data(self, row_data):
        """Extract lead data from row based on field mapping"""
        # This would use the field mapping from the import configuration
        # For now, using basic field names
        return {
            'first_name': row_data.get('first_name', '').strip(),
            'last_name': row_data.get('last_name', '').strip(),
            'phone_number': row_data.get('phone_number', '').strip(),
            'email': row_data.get('email', '').strip() or None,
            'company': row_data.get('company', '').strip() or None,
            'address': row_data.get('address', '').strip() or None,
            'city': row_data.get('city', '').strip() or None,
            'state': row_data.get('state', '').strip() or None,
            'zip_code': row_data.get('zip_code', '').strip() or None,
            'source': row_data.get('source', 'Import').strip() or 'Import',
            'comments': row_data.get('comments', '').strip() or None,
        }