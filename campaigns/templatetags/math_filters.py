from django import template

register = template.Library()

@register.filter
def mul(value, arg):
    """Multiplies the value by the arg."""
    try:
        return value * arg
    except (ValueError, TypeError):
        return ''

@register.filter
def div(value, arg):
    """Divides the value by the arg."""
    try:
        return value / arg
    except (ValueError, TypeError, ZeroDivisionError):
        return ''
