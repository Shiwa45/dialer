# core/tasks.py

from celery import shared_task
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
import csv
import io
import pandas as pd
from datetime import timedelta


@shared_task
def process_lead_import_task(import_id):
    """
    Process lead import file asynchronously
    """
    from leads.models import LeadImport, Lead, DNCEntry
    
    try:
        lead_import = LeadImport.objects.get(id=import_id)
        lead_import.status = 'processing'
        lead_import.save()
        
        # Read the uploaded file
        file_path = lead_import.file.path
        
        if file_path.endswith('.csv'):
            # Process CSV file
            with open(file_path, 'r', encoding='utf-8-sig') as file:
                reader = csv.reader(file)
                headers = next(reader)
                rows = list(reader)
                lead_import.total_rows = len(rows)
                lead_import.save()
                
                # Get field mapping
                mapping = lead_import.field_mapping
                
                for row_num, row in enumerate(rows, 1):
                    try:
                        # Helper to get value by mapped column index
                        def get_mapped_value(field_name):
                            for col_idx, mapped_field in mapping.items():
                                if mapped_field == field_name:
                                    try:
                                        return row[int(col_idx)].strip()
                                    except (IndexError, ValueError):
                                        return ''
                            return ''

                        # Extract lead data using mapping
                        first_name = get_mapped_value('first_name')
                        last_name = get_mapped_value('last_name')
                        phone_number = get_mapped_value('phone_number')
                        
                        if not first_name or not last_name or not phone_number:
                            lead_import.failed_imports += 1
                            continue
                        
                        # Check for duplicates if enabled
                        if lead_import.skip_duplicates:
                            if Lead.objects.filter(phone_number=phone_number).exists():
                                lead_import.duplicate_count += 1
                                continue
                        
                        # Check DNC if enabled
                        if lead_import.check_dnc:
                            if DNCEntry.objects.filter(phone_number=phone_number).exists():
                                lead_import.failed_imports += 1
                                continue
                        
                        # Create lead
                        lead = Lead.objects.create(
                            first_name=first_name,
                            last_name=last_name,
                            phone_number=phone_number,
                            email=get_mapped_value('email') or '',
                            company=get_mapped_value('company') or '',
                            address=get_mapped_value('address') or '',
                            city=get_mapped_value('city') or '',
                            state=get_mapped_value('state') or '',
                            zip_code=get_mapped_value('zip_code') or '',
                            source=get_mapped_value('source') or 'Import',
                            comments=get_mapped_value('comments') or '',
                            lead_list=lead_import.lead_list
                        )
                        
                        lead_import.successful_imports += 1
                        
                    except Exception as e:
                        lead_import.failed_imports += 1
                        print(f"Error processing row {row_num}: {str(e)}")
                    
                    lead_import.processed_rows = row_num
                    if row_num % 100 == 0:  # Update progress every 100 rows
                        lead_import.save()
        
        elif file_path.endswith(('.xlsx', '.xls')):
            # Process Excel file
            df = pd.read_excel(file_path)
            lead_import.total_rows = len(df)
            lead_import.save()
            
            # Get field mapping
            mapping = lead_import.field_mapping
            
            for index, row in df.iterrows():
                try:
                    # Helper to get value by mapped column index
                    def get_mapped_value(field_name):
                        for col_idx, mapped_field in mapping.items():
                            if mapped_field == field_name:
                                try:
                                    # Excel columns are 0-indexed in mapping
                                    val = row.iloc[int(col_idx)]
                                    return str(val).strip() if pd.notna(val) else ''
                                except (IndexError, ValueError):
                                    return ''
                        return ''

                    # Extract lead data using mapping
                    first_name = get_mapped_value('first_name')
                    last_name = get_mapped_value('last_name')
                    phone_number = get_mapped_value('phone_number')
                    
                    if not first_name or not last_name or not phone_number:
                        lead_import.failed_imports += 1
                        continue
                    
                    # Check for duplicates if enabled
                    if lead_import.skip_duplicates:
                        if Lead.objects.filter(phone_number=phone_number).exists():
                            lead_import.duplicate_count += 1
                            continue
                    
                    # Check DNC if enabled
                    if lead_import.check_dnc:
                        if DNCEntry.objects.filter(phone_number=phone_number).exists():
                            lead_import.failed_imports += 1
                            continue
                    
                    # Create lead
                    lead = Lead.objects.create(
                        first_name=first_name,
                        last_name=last_name,
                        phone_number=phone_number,
                        email=get_mapped_value('email') or '',
                        company=get_mapped_value('company') or '',
                        address=get_mapped_value('address') or '',
                        city=get_mapped_value('city') or '',
                        state=get_mapped_value('state') or '',
                        zip_code=get_mapped_value('zip_code') or '',
                        source=get_mapped_value('source') or 'Import',
                        comments=get_mapped_value('comments') or '',
                        lead_list=lead_import.lead_list
                    )
                    
                    lead_import.successful_imports += 1
                    
                except Exception as e:
                    lead_import.failed_imports += 1
                    print(f"Error processing row {index + 1}: {str(e)}")
                
                lead_import.processed_rows = index + 1
                if (index + 1) % 100 == 0:  # Update progress every 100 rows
                    lead_import.save()
        
        # Mark as completed
        lead_import.status = 'completed'
        lead_import.save()
        
        # Send notification email
        send_import_notification.delay(import_id)
        
    except Exception as e:
        # Mark as failed
        lead_import.status = 'failed'
        lead_import.error_message = str(e)
        lead_import.save()
        
        # Send error notification
        send_import_error_notification.delay(import_id, str(e))


@shared_task
def send_import_notification(import_id):
    """
    Send email notification when import is completed
    """
    from leads.models import LeadImport
    
    try:
        lead_import = LeadImport.objects.get(id=import_id)
        
        subject = f'Lead Import "{lead_import.name}" Completed'
        message = f"""
        Your lead import has been completed successfully.
        
        Import Details:
        - Name: {lead_import.name}
        - Lead List: {lead_import.lead_list.name}
        - Total Rows Processed: {lead_import.processed_rows}
        - Successful Imports: {lead_import.successful_imports}
        - Failed Imports: {lead_import.failed_imports}
        - Duplicates Skipped: {lead_import.duplicate_count}
        
        You can view the complete import details in the system.
        """
        
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [lead_import.user.email],
            fail_silently=True
        )
        
    except Exception as e:
        print(f"Error sending import notification: {str(e)}")


@shared_task
def send_import_error_notification(import_id, error_message):
    """
    Send email notification when import fails
    """
    from leads.models import LeadImport
    
    try:
        lead_import = LeadImport.objects.get(id=import_id)
        
        subject = f'Lead Import "{lead_import.name}" Failed'
        message = f"""
        Your lead import has failed with the following error:
        
        Error: {error_message}
        
        Import Details:
        - Name: {lead_import.name}
        - Lead List: {lead_import.lead_list.name}
        - Rows Processed: {lead_import.processed_rows}
        
        Please check your file format and try again.
        """
        
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [lead_import.user.email],
            fail_silently=True
        )
        
    except Exception as e:
        print(f"Error sending import error notification: {str(e)}")


@shared_task
def run_lead_recycling_task():
    """
    Run lead recycling based on active recycling rules
    """
    from leads.models import LeadRecyclingRule, Lead
    
    recycled_count = 0
    
    try:
        # Get active recycling rules
        rules = LeadRecyclingRule.objects.filter(is_active=True)
        
        for rule in rules:
            # Calculate cutoff date
            cutoff_date = timezone.now() - timedelta(days=rule.days_since_contact)
            
            # Find leads matching the rule criteria
            leads_to_recycle = Lead.objects.filter(
                status=rule.source_status,
                last_contact_date__lte=cutoff_date,
                call_count__lt=rule.max_attempts
            )
            
            # Update leads to target status
            updated_count = leads_to_recycle.update(
                status=rule.target_status,
                call_count=0,  # Reset call count for recycled leads
                last_contact_date=None
            )
            
            recycled_count += updated_count
        
        # Send notification about recycling results
        if recycled_count > 0:
            send_recycling_notification.delay(recycled_count)
            
    except Exception as e:
        print(f"Error running lead recycling: {str(e)}")
    
    return recycled_count


@shared_task
def send_recycling_notification(recycled_count):
    """
    Send notification about lead recycling results
    """
    from django.contrib.auth.models import User
    
    try:
        # Send to managers and supervisors
        managers = User.objects.filter(
            groups__name__in=['Managers', 'Supervisors']
        ).distinct()
        
        subject = f'{recycled_count} Leads Recycled'
        message = f"""
        Lead recycling process has completed.
        
        Results:
        - {recycled_count} leads have been recycled and are available for new attempts
        
        These leads have been reset to "new" status and can be contacted again.
        """
        
        recipient_emails = [user.email for user in managers if user.email]
        
        if recipient_emails:
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                recipient_emails,
                fail_silently=True
            )
            
    except Exception as e:
        print(f"Error sending recycling notification: {str(e)}")


@shared_task
def send_callback_reminders():
    """
    Send reminders for upcoming callbacks
    """
    from leads.models import CallbackSchedule
    from django.template.loader import render_to_string
    
    # Get callbacks due in the next hour that haven't been reminded
    now = timezone.now()
    reminder_time = now + timedelta(hours=1)
    
    callbacks = CallbackSchedule.objects.filter(
        scheduled_time__lte=reminder_time,
        scheduled_time__gte=now,
        is_completed=False,
        reminder_sent=False
    ).select_related('lead', 'agent', 'campaign')
    
    for callback in callbacks:
        try:
            subject = f'Callback Reminder: {callback.lead.get_full_name()}'
            
            # Use template for email content
            context = {
                'callback': callback,
                'lead': callback.lead,
                'campaign': callback.campaign
            }
            
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
            
            # Mark reminder as sent
            callback.reminder_sent = True
            callback.save()
            
        except Exception as e:
            print(f"Error sending callback reminder for {callback.id}: {str(e)}")


@shared_task
def cleanup_old_imports():
    """
    Clean up old import files and records
    """
    from leads.models import LeadImport
    import os
    
    # Delete import records older than 30 days
    cutoff_date = timezone.now() - timedelta(days=30)
    old_imports = LeadImport.objects.filter(created_at__lt=cutoff_date)
    
    deleted_count = 0
    for import_obj in old_imports:
        try:
            # Delete the file
            if import_obj.file and os.path.exists(import_obj.file.path):
                os.remove(import_obj.file.path)
            
            # Delete the record
            import_obj.delete()
            deleted_count += 1
            
        except Exception as e:
            print(f"Error deleting import {import_obj.id}: {str(e)}")
    
    return deleted_count


@shared_task
def update_lead_statistics():
    """
    Update lead statistics for dashboards
    """
    from leads.models import Lead, LeadList
    from django.core.cache import cache
    
    try:
        # Calculate overall statistics
        stats = {
            'total_leads': Lead.objects.count(),
            'fresh_leads': Lead.objects.filter(status='new').count(),
            'contacted_leads': Lead.objects.filter(status__in=['contacted', 'callback']).count(),
            'sales': Lead.objects.filter(status='sale').count(),
            'dnc_leads': Lead.objects.filter(status='dnc').count(),
            'today_leads': Lead.objects.filter(created_at__date=timezone.now().date()).count(),
            'today_contacts': Lead.objects.filter(last_contact_date__date=timezone.now().date()).count(),
        }
        
        # Calculate conversion rates
        if stats['total_leads'] > 0:
            stats['conversion_rate'] = round((stats['sales'] / stats['total_leads']) * 100, 2)
            stats['contact_rate'] = round((stats['contacted_leads'] / stats['total_leads']) * 100, 2)
        else:
            stats['conversion_rate'] = 0
            stats['contact_rate'] = 0
        
        # Cache the statistics for 5 minutes
        cache.set('lead_statistics', stats, 300)
        
        return stats
        
    except Exception as e:
        print(f"Error updating lead statistics: {str(e)}")
        return None