
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import UserProfile, AgentStatus

@receiver(post_save, sender=User)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    """
    Create or update user profile when user is created/updated
    """
    if created:
        # Generate unique agent_id and employee_id
        existing_count = UserProfile.objects.count()
        
        # Create profile with unique identifiers
        profile_data = {
            'user': instance,
            'agent_id': f'USR{existing_count + 1:03d}',
            'employee_id': f'EMP{existing_count + 1:03d}',
        }
        
        try:
            UserProfile.objects.create(**profile_data)
        except Exception:
            # If there's a conflict, try with a different number
            for i in range(existing_count + 1, existing_count + 100):
                try:
                    profile_data['agent_id'] = f'USR{i:03d}'
                    profile_data['employee_id'] = f'EMP{i:03d}'
                    UserProfile.objects.create(**profile_data)
                    break
                except Exception:
                    continue
        
        # Create agent status
        try:
            AgentStatus.objects.create(user=instance)
        except Exception:
            pass  # AgentStatus might already exist
    else:
        # Update profile if it exists
        if hasattr(instance, 'profile'):
            instance.profile.save()

@receiver(pre_delete, sender=User)
def delete_user_related_data(sender, instance, **kwargs):
    """
    Clean up related data when user is deleted
    """
    # Set agent status to offline before deletion
    if hasattr(instance, 'agent_status'):
        instance.agent_status.status = 'offline'
        instance.agent_status.save()
