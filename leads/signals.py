# leads/signals.py

from django.db.models.signals import post_save, pre_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from django.utils import timezone
from .models import Lead, LeadList, DNCEntry, CallbackSchedule, LeadImport
from .utils import clean_phone_number


@receiver(pre_save, sender=Lead)
def clean_lead_data(sender, instance, **kwargs):
    """
    Clean and format lead data before saving
    """
    # Clean phone number
    if instance.phone_number:
        instance.phone_number = clean_phone_number(instance.phone_number)
    
    # Clean email
    if instance.email:
        instance.email = instance.email.lower().strip()
    
    # Clean names
    if instance.first_name:
        instance.first_name = instance.first_name.strip().title()
    
    if instance.last_name:
        instance.last_name = instance.last_name.strip().title()
    
    # Clean company
    if instance.company:
        instance.company = instance.company.strip()
    
    # Set last contact date when status changes to contacted
    if instance.pk:
        try:
            old_instance = Lead.objects.get(pk=instance.pk)
            if (old_instance.status != instance.status and 
                instance.status in ['contacted', 'callback', 'sale', 'not_interested']):
                instance.last_contact_date = timezone.now()
        except Lead.DoesNotExist:
            pass


@receiver(post_save, sender=Lead)
def lead_post_save(sender, instance, created, **kwargs):
    """
    Handle lead post-save operations
    """
    # Clear cache
    cache.delete('lead_statistics')
    
    # If lead is marked as DNC, add to DNC list
    if instance.status == 'dnc':
        DNCEntry.objects.get_or_create(
            phone_number=instance.phone_number,
            defaults={
                'reason': 'Lead marked as DNC',
                'added_by': instance.assigned_user or instance.created_by
            }
        )
    
    # Update lead list statistics
    if instance.lead_list:
        cache.delete(f'lead_list_stats_{instance.lead_list.id}')
    
    # If this is a new lead, check for potential duplicates and log
    if created:
        from .utils import check_duplicate_lead
        duplicates = check_duplicate_lead(
            instance.phone_number, 
            instance.email, 
            exclude_id=instance.id
        )
        
        if duplicates.exists():
            # Log potential duplicate (you might want to create a notification system)
            pass


@receiver(post_delete, sender=Lead)
def lead_post_delete(sender, instance, **kwargs):
    """
    Handle lead deletion
    """
    # Clear cache
    cache.delete('lead_statistics')
    
    # Update lead list statistics
    if instance.lead_list:
        cache.delete(f'lead_list_stats_{instance.lead_list.id}')


@receiver(post_save, sender=LeadList)
def lead_list_post_save(sender, instance, created, **kwargs):
    """
    Handle lead list post-save operations
    """
    # Clear cache
    cache.delete('lead_list_statistics')
    cache.delete(f'lead_list_stats_{instance.id}')


@receiver(post_save, sender=DNCEntry)
def dnc_entry_post_save(sender, instance, created, **kwargs):
    """
    Handle DNC entry post-save operations
    """
    if created:
        # Mark all leads with this phone number as DNC
        from .models import Lead
        Lead.objects.filter(
            phone_number=instance.phone_number
        ).exclude(
            status='dnc'
        ).update(
            status='dnc',
            last_contact_date=timezone.now()
        )
        
        # Clear cache
        cache.delete('lead_statistics')


@receiver(post_save, sender=CallbackSchedule)
def callback_schedule_post_save(sender, instance, created, **kwargs):
    """
    Handle callback schedule post-save operations
    """
    if created:
        # Update lead status to callback if not already
        if instance.lead.status != 'callback':
            instance.lead.status = 'callback'
            instance.lead.save()
    
    # Clear callback-related cache
    cache.delete(f'agent_callbacks_{instance.agent.id}')


@receiver(post_save, sender=LeadImport)
def lead_import_post_save(sender, instance, created, **kwargs):
    """
    Handle lead import post-save operations
    """
    if instance.status == 'completed':
        # Send notification email
        from core.tasks import send_import_notification
        send_import_notification.delay(instance.id)
    
    elif instance.status == 'failed':
        # Send error notification
        from core.tasks import send_import_error_notification
        send_import_error_notification.delay(instance.id, instance.error_message)


# Custom signal for lead activity tracking
from django.dispatch import Signal

lead_activity = Signal()

@receiver(lead_activity)
def log_lead_activity(sender, lead, activity_type, user, details=None, **kwargs):
    """
    Log lead activity for audit trail
    """
    from .models import LeadNote
    
    # Create activity note
    activity_message = f"Activity: {activity_type}"
    if details:
        activity_message += f" - {details}"
    
    LeadNote.objects.create(
        lead=lead,
        user=user,
        note=activity_message,
        is_important=(activity_type in ['call_made', 'sale', 'dnc'])
    )


# Signal for automatic lead scoring updates
@receiver(post_save, sender=Lead)
def update_lead_score(sender, instance, **kwargs):
    """
    Update lead score when lead data changes
    """
    from .utils import calculate_lead_score
    
    # Calculate new score
    new_score = calculate_lead_score(instance)
    
    # Update if score has changed significantly
    if abs((instance.score or 0) - new_score) >= 5:
        Lead.objects.filter(pk=instance.pk).update(score=new_score)


# Signal for campaign statistics updates
@receiver(post_save, sender=Lead)
def update_campaign_stats(sender, instance, **kwargs):
    """
    Update campaign statistics when lead status changes
    """
    if instance.lead_list:
        # Get campaigns using this lead list
        campaigns = instance.lead_list.campaigns.all()
        
        for campaign in campaigns:
            # Clear campaign statistics cache
            cache.delete(f'campaign_stats_{campaign.id}')


# Signal for lead recycling
@receiver(post_save, sender=Lead)
def check_lead_recycling(sender, instance, **kwargs):
    """
    Check if lead should be considered for recycling
    """
    if instance.status in ['no_answer', 'busy'] and instance.call_count >= 3:
        # Schedule for potential recycling
        from .models import LeadRecyclingRule
        
        applicable_rules = LeadRecyclingRule.objects.filter(
            is_active=True,
            source_status=instance.status,
            max_attempts__gte=instance.call_count
        )
        
        if applicable_rules.exists():
            # Add to recycling queue (you might implement this as a separate model)
            pass


# Signal for data integrity checks
@receiver(pre_save, sender=Lead)
def validate_lead_data_integrity(sender, instance, **kwargs):
    """
    Validate data integrity before saving lead
    """
    from .utils import validate_phone_number, validate_email
    
    # Validate phone number
    if instance.phone_number:
        is_valid, message = validate_phone_number(instance.phone_number)
        if not is_valid:
            raise ValueError(f"Invalid phone number: {message}")
    
    # Validate email
    if instance.email:
        is_valid, message = validate_email(instance.email)
        if not is_valid:
            raise ValueError(f"Invalid email: {message}")
    
    # Check required fields
    if not instance.first_name or not instance.last_name:
        raise ValueError("First name and last name are required")


# Signal for automatic tagging
@receiver(post_save, sender=Lead)
def auto_tag_leads(sender, instance, created, **kwargs):
    """
    Automatically tag leads based on certain criteria
    """
    if created and instance.lead_list:
        tags = []
        
        # Tag based on source
        if instance.source:
            tags.append(f"source:{instance.source.lower()}")
        
        # Tag based on company
        if instance.company:
            tags.append("has_company")
        
        # Tag based on priority
        if instance.priority == 'high':
            tags.append("high_priority")
        
        # Update lead list tags if needed
        if tags:
            current_tags = instance.lead_list.tags or ""
            new_tags = set(current_tags.split(",") + tags)
            instance.lead_list.tags = ",".join(filter(None, new_tags))
            instance.lead_list.save()


# Signal for callback reminders
@receiver(post_save, sender=CallbackSchedule)
def schedule_callback_reminder(sender, instance, created, **kwargs):
    """
    Schedule callback reminder
    """
    if created and not instance.reminder_sent:
        # Schedule reminder task for 1 hour before callback
        from celery import current_app
        from datetime import timedelta
        
        reminder_time = instance.scheduled_time - timedelta(hours=1)
        
        if reminder_time > timezone.now():
            # Schedule the reminder task
            current_app.send_task(
                'core.tasks.send_callback_reminders',
                eta=reminder_time
            )