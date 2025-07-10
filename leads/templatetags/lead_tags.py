# leads/templatetags/lead_tags.py

from django import template
from django.utils.safestring import mark_safe
from django.utils import timezone
from datetime import timedelta
import re

register = template.Library()


@register.filter
def phone_format(phone_number):
    """
    Format phone number for display
    """
    if not phone_number:
        return ""
    
    # Remove all non-digit characters
    digits = re.sub(r'\D', '', str(phone_number))
    
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    elif len(digits) == 11 and digits.startswith('1'):
        digits = digits[1:]
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    else:
        return phone_number


@register.filter
def lead_status_badge(status):
    """
    Return Bootstrap badge HTML for lead status
    """
    badges = {
        'new': '<span class="badge bg-success">New</span>',
        'contacted': '<span class="badge bg-primary">Contacted</span>',
        'callback': '<span class="badge bg-warning">Callback</span>',
        'sale': '<span class="badge bg-success">Sale</span>',
        'no_answer': '<span class="badge bg-secondary">No Answer</span>',
        'busy': '<span class="badge bg-info">Busy</span>',
        'not_interested': '<span class="badge bg-dark">Not Interested</span>',
        'dnc': '<span class="badge bg-danger">Do Not Call</span>',
    }
    return mark_safe(badges.get(status, f'<span class="badge bg-light">{status}</span>'))


@register.filter
def priority_badge(priority):
    """
    Return Bootstrap badge HTML for priority
    """
    badges = {
        'high': '<span class="badge bg-danger">High</span>',
        'medium': '<span class="badge bg-warning">Medium</span>',
        'low': '<span class="badge bg-success">Low</span>',
    }
    return mark_safe(badges.get(priority, f'<span class="badge bg-secondary">{priority}</span>'))


@register.filter
def days_since(date):
    """
    Calculate days since a given date
    """
    if not date:
        return None
    
    delta = timezone.now() - date
    return delta.days


@register.filter
def time_until_callback(callback_time):
    """
    Return human-readable time until callback
    """
    if not callback_time:
        return ""
    
    now = timezone.now()
    delta = callback_time - now
    
    if delta.total_seconds() < 0:
        return "Overdue"
    elif delta.days > 0:
        return f"In {delta.days} day{'s' if delta.days != 1 else ''}"
    elif delta.seconds > 3600:
        hours = delta.seconds // 3600
        return f"In {hours} hour{'s' if hours != 1 else ''}"
    elif delta.seconds > 60:
        minutes = delta.seconds // 60
        return f"In {minutes} minute{'s' if minutes != 1 else ''}"
    else:
        return "Soon"


@register.filter
def lead_score_color(score):
    """
    Return CSS class for lead score color
    """
    if not score:
        return "text-muted"
    
    if score >= 80:
        return "text-success"
    elif score >= 60:
        return "text-warning"
    elif score >= 40:
        return "text-info"
    else:
        return "text-danger"


@register.filter
def contact_attempts_badge(count):
    """
    Return badge for contact attempts
    """
    if not count or count == 0:
        return mark_safe('<span class="badge bg-light">No attempts</span>')
    elif count <= 2:
        return mark_safe(f'<span class="badge bg-info">{count} attempt{"s" if count != 1 else ""}</span>')
    elif count <= 5:
        return mark_safe(f'<span class="badge bg-warning">{count} attempts</span>')
    else:
        return mark_safe(f'<span class="badge bg-danger">{count} attempts</span>')


@register.filter
def split(value, delimiter):
    """
    Split a string by delimiter
    """
    if not value:
        return []
    return value.split(delimiter)


@register.filter
def trim(value):
    """
    Strip leading and trailing whitespace from the string
    """
    if not isinstance(value, str):
        return value
    return value.strip()


@register.filter
def percentage(value, total):
    """
    Calculate percentage
    """
    if not total or total == 0:
        return 0
    return round((value / total) * 100, 1)


@register.simple_tag
def lead_progress_bar(current, total, css_class="progress-bar bg-primary"):
    """
    Generate a progress bar for lead statistics
    """
    if not total or total == 0:
        percent = 0
    else:
        percent = round((current / total) * 100, 1)
    
    return mark_safe(f'''
        <div class="progress" style="height: 8px;">
            <div class="{css_class}" role="progressbar" 
                 style="width: {percent}%" 
                 aria-valuenow="{current}" 
                 aria-valuemin="0" 
                 aria-valuemax="{total}">
            </div>
        </div>
    ''')


@register.inclusion_tag('leads/tags/lead_card.html')
def lead_card(lead, show_actions=True):
    """
    Render a lead card component
    """
    return {
        'lead': lead,
        'show_actions': show_actions
    }


@register.inclusion_tag('leads/tags/callback_badge.html')
def callback_badge(lead):
    """
    Render callback badge for lead
    """
    upcoming_callbacks = lead.callbacks.filter(
        is_completed=False,
        scheduled_time__gte=timezone.now()
    ).order_by('scheduled_time')
    
    return {
        'lead': lead,
        'upcoming_callbacks': upcoming_callbacks
    }


@register.simple_tag
def get_lead_stats(lead_list=None, campaign=None):
    """
    Get lead statistics for a lead list or campaign
    """
    from leads.models import Lead
    
    queryset = Lead.objects.all()
    
    if lead_list:
        queryset = queryset.filter(lead_list=lead_list)
    
    if campaign:
        queryset = queryset.filter(lead_list__campaigns=campaign)
    
    stats = {
        'total': queryset.count(),
        'new': queryset.filter(status='new').count(),
        'contacted': queryset.filter(status='contacted').count(),
        'callbacks': queryset.filter(status='callback').count(),
        'sales': queryset.filter(status='sale').count(),
        'dnc': queryset.filter(status='dnc').count(),
    }
    
    if stats['total'] > 0:
        stats['contact_rate'] = round((stats['contacted'] / stats['total']) * 100, 1)
        stats['conversion_rate'] = round((stats['sales'] / stats['total']) * 100, 1)
    else:
        stats['contact_rate'] = 0
        stats['conversion_rate'] = 0
    
    return stats


@register.filter
def lead_age_class(lead):
    """
    Return CSS class based on lead age
    """
    age_days = lead.days_since_created()
    
    if age_days <= 1:
        return "text-success"  # New lead
    elif age_days <= 7:
        return "text-info"     # Fresh lead
    elif age_days <= 30:
        return "text-warning"  # Getting old
    else:
        return "text-danger"   # Old lead


@register.filter
def format_duration(seconds):
    """
    Format duration in seconds to human readable format
    """
    if not seconds:
        return "0s"
    
    hours, remainder = divmod(int(seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    
    if hours > 0:
        return f"{hours}h {minutes}m {seconds}s"
    elif minutes > 0:
        return f"{minutes}m {seconds}s"
    else:
        return f"{seconds}s"


@register.simple_tag
def call_outcome_icon(outcome):
    """
    Return icon for call outcome
    """
    icons = {
        'sale': 'fas fa-trophy text-success',
        'callback': 'fas fa-calendar text-warning',
        'no_answer': 'fas fa-phone-slash text-muted',
        'busy': 'fas fa-busy text-info',
        'not_interested': 'fas fa-times text-danger',
        'dnc': 'fas fa-ban text-danger',
    }
    
    icon_class = icons.get(outcome, 'fas fa-phone text-primary')
    return mark_safe(f'<i class="{icon_class}"></i>')


@register.filter
def truncate_phone(phone_number, length=10):
    """
    Truncate phone number for display in small spaces
    """
    if not phone_number:
        return ""
    
    if len(phone_number) <= length:
        return phone_number
    
    return phone_number[:length] + "..."


@register.simple_tag
def lead_trend_arrow(current, previous):
    """
    Show trend arrow for statistics
    """
    if not previous or previous == 0:
        return mark_safe('<i class="fas fa-minus text-muted"></i>')
    
    change = ((current - previous) / previous) * 100
    
    if change > 5:
        return mark_safe('<i class="fas fa-arrow-up text-success"></i>')
    elif change < -5:
        return mark_safe('<i class="fas fa-arrow-down text-danger"></i>')
    else:
        return mark_safe('<i class="fas fa-arrow-right text-warning"></i>')


@register.filter
def is_callback_overdue(callback_time):
    """
    Check if callback is overdue
    """
    if not callback_time:
        return False
    
    return callback_time < timezone.now()


@register.simple_tag
def get_recent_activity(lead, limit=5):
    """
    Get recent activity for a lead
    """
    activities = []
    
    # Get recent notes
    recent_notes = lead.notes.order_by('-created_at')[:limit]
    for note in recent_notes:
        activities.append({
            'type': 'note',
            'timestamp': note.created_at,
            'user': note.user,
            'description': f"Added note: {note.note[:50]}{'...' if len(note.note) > 50 else ''}"
        })
    
    # Get recent callbacks
    recent_callbacks = lead.callbacks.order_by('-created_at')[:limit]
    for callback in recent_callbacks:
        activities.append({
            'type': 'callback',
            'timestamp': callback.created_at,
            'user': callback.agent,
            'description': f"Scheduled callback for {callback.scheduled_time.strftime('%m/%d/%Y %H:%M')}"
        })
    
    # Sort by timestamp and return limited results
    activities.sort(key=lambda x: x['timestamp'], reverse=True)
    return activities[:limit]


@register.filter
def mask_phone(phone_number):
    """
    Mask phone number for privacy (show only last 4 digits)
    """
    if not phone_number:
        return ""
    
    digits = re.sub(r'\D', '', str(phone_number))
    
    if len(digits) >= 4:
        masked = 'X' * (len(digits) - 4) + digits[-4:]
        if len(digits) == 10:
            return f"({masked[:3]}) {masked[3:6]}-{masked[6:]}"
        else:
            return masked
    else:
        return 'X' * len(digits)


@register.filter
def lead_priority_color(priority):
    """
    Return color class for lead priority
    """
    colors = {
        'high': 'text-danger',
        'medium': 'text-warning', 
        'low': 'text-success'
    }
    return colors.get(priority, 'text-muted')


@register.simple_tag
def campaign_lead_count(campaign):
    """
    Get total lead count for a campaign
    """
    if not campaign:
        return 0
    
    return sum(lead_list.leads.count() for lead_list in campaign.lead_lists.all())


@register.filter
def default_if_empty(value, default):
    """
    Return default value if the given value is empty
    """
    return value if value else default


@register.simple_tag(takes_context=True)
def query_string(context, **kwargs):
    """
    Update query string with new parameters
    """
    request = context['request']
    query_dict = request.GET.copy()
    
    for key, value in kwargs.items():
        if value is None:
            query_dict.pop(key, None)
        else:
            query_dict[key] = value
    
    return '?' + query_dict.urlencode() if query_dict else ''


@register.inclusion_tag('leads/tags/pagination.html', takes_context=True)
def lead_pagination(context, page_obj):
    """
    Render pagination for lead lists
    """
    return {
        'page_obj': page_obj,
        'request': context['request']
    }