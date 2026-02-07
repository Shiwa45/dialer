"""
User Signals - PHASE 2.1: Auto-generate Extension on User Creation

This module contains Django signals for user-related events.
When a new user is created with the 'Agent' role, an extension
is automatically generated and a Phone record is created.
"""

import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User, Group

logger = logging.getLogger(__name__)


@receiver(post_save, sender=User)
def create_agent_extension(sender, instance, created, **kwargs):
    """
    PHASE 2.1: Auto-generate extension when a new agent user is created
    
    This signal fires after a User is saved. If the user:
    1. Is newly created (created=True)
    2. Is assigned to the 'Agent' group
    
    Then we automatically:
    1. Generate the next available extension number
    2. Create a Phone record for the user
    3. Sync the phone to Asterisk
    
    Args:
        sender: The User model class
        instance: The User instance being saved
        created: Boolean indicating if this is a new user
        kwargs: Additional arguments
    """
    if not created:
        return
    
    # Check if user is an agent
    try:
        agent_group = Group.objects.filter(name__iexact='agent').first()
        if not agent_group:
            # Try alternative group names
            agent_group = Group.objects.filter(
                name__iexact='agents'
            ).first()
        
        if not agent_group:
            logger.debug(f"No Agent group found, skipping extension creation for {instance.username}")
            return
        
        # Check if user is in agent group
        if not instance.groups.filter(id=agent_group.id).exists():
            logger.debug(f"User {instance.username} is not an agent, skipping extension creation")
            return
        
    except Exception as e:
        logger.error(f"Error checking user groups: {e}")
        return
    
    # Generate extension
    try:
        _create_extension_for_user(instance)
    except Exception as e:
        logger.error(f"Error creating extension for {instance.username}: {e}")


def _create_extension_for_user(user):
    """
    Create a phone extension for a user
    
    Args:
        user: User instance
    """
    from telephony.models import Phone, AsteriskServer
    from core.models import SystemConfiguration
    
    # Check if user already has a phone
    existing_phone = Phone.objects.filter(user=user).first()
    if existing_phone:
        logger.info(f"User {user.username} already has extension {existing_phone.extension}")
        return existing_phone
    
    # Get extension configuration
    extension_prefix = '100'  # Default prefix
    try:
        config = SystemConfiguration.objects.filter(key='EXTENSION_PREFIX').first()
        if config:
            extension_prefix = config.value
    except Exception:
        pass
    
    # Find next available extension
    next_extension = _get_next_extension(extension_prefix)
    
    # Get active Asterisk server
    server = AsteriskServer.objects.filter(is_active=True).first()
    if not server:
        logger.warning(f"No active Asterisk server, creating phone without server for {user.username}")
    
    # Create phone
    phone = Phone.objects.create(
        extension=next_extension,
        name=f"{user.get_full_name() or user.username} Phone",
        phone_type='sip',
        user=user,
        asterisk_server=server,
        host='dynamic',
        context='agents',
        codec='ulaw,alaw',
        qualify='yes',
        nat='force_rport,comedia',
        call_waiting=True,
        call_transfer=True,
        three_way_calling=True,
        is_active=True
    )
    
    logger.info(f"Created extension {next_extension} for user {user.username}")
    
    return phone


def _get_next_extension(prefix='100'):
    """
    Get the next available extension number
    
    Strategy:
    1. Find the highest extension starting with the prefix
    2. Increment by 1
    3. If no extensions exist, start with prefix + '1'
    
    Args:
        prefix: Extension prefix (e.g., '100')
    
    Returns:
        str: Next available extension (e.g., '1001', '1002')
    """
    from telephony.models import Phone
    
    # Get all extensions starting with prefix
    existing_extensions = Phone.objects.filter(
        extension__startswith=prefix
    ).values_list('extension', flat=True)
    
    if not existing_extensions:
        # No extensions yet, start with prefix + '1'
        return f"{prefix}1"
    
    # Find the highest number
    max_extension = 0
    for ext in existing_extensions:
        try:
            # Extract the numeric part after prefix
            num_part = ext[len(prefix):]
            if num_part.isdigit():
                max_extension = max(max_extension, int(num_part))
        except (ValueError, IndexError):
            continue
    
    # Return next extension
    return f"{prefix}{max_extension + 1}"


@receiver(post_save, sender=User)
def create_agent_status(sender, instance, created, **kwargs):
    """
    Create AgentStatus record for new users
    
    Every user should have an AgentStatus record for tracking.
    """
    if not created:
        return
    
    try:
        from users.models import AgentStatus
        
        AgentStatus.objects.get_or_create(
            user=instance,
            defaults={
                'status': 'offline'
            }
        )
        logger.debug(f"Created AgentStatus for {instance.username}")
        
    except Exception as e:
        logger.error(f"Error creating AgentStatus for {instance.username}: {e}")


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """
    Create UserProfile for new users
    """
    if not created:
        return
    
    try:
        from users.models import UserProfile
        
        # Check if profile already exists
        if hasattr(instance, 'profile'):
            return
        
        # Generate unique IDs
        existing_count = UserProfile.objects.count()
        agent_id = f'USR{existing_count + 1:04d}'
        employee_id = f'EMP{existing_count + 1:04d}'
        
        UserProfile.objects.get_or_create(
            user=instance,
            defaults={
                'agent_id': agent_id,
                'employee_id': employee_id
            }
        )
        logger.debug(f"Created UserProfile for {instance.username}")
        
    except Exception as e:
        logger.error(f"Error creating UserProfile for {instance.username}: {e}")


def manually_create_extension(user, extension=None):
    """
    Manually create an extension for a user
    
    This can be called from admin or API to create extension
    for an existing user.
    
    Args:
        user: User instance
        extension: Optional specific extension number
    
    Returns:
        Phone: Created or existing Phone instance
    """
    from telephony.models import Phone, AsteriskServer
    
    # Check for existing phone
    existing = Phone.objects.filter(user=user).first()
    if existing:
        return existing
    
    # Get extension
    if not extension:
        extension = _get_next_extension()
    
    # Validate extension is unique
    if Phone.objects.filter(extension=extension).exists():
        raise ValueError(f"Extension {extension} already exists")
    
    # Get server
    server = AsteriskServer.objects.filter(is_active=True).first()
    
    # Create phone
    phone = Phone.objects.create(
        extension=extension,
        name=f"{user.get_full_name() or user.username} Phone",
        phone_type='sip',
        user=user,
        asterisk_server=server,
        is_active=True
    )
    
    return phone


# ========================================
# Add to apps.py to connect signals
# ========================================
"""
In users/apps.py, add:

class UsersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'users'
    
    def ready(self):
        import users.signals  # noqa
"""
