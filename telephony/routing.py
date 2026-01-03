# Helpers for outbound routing and call metadata
import random
from typing import Optional, Dict, Any
from django.utils import timezone


def select_carrier_for_campaign(campaign):
    """
    Pick an active carrier for the given campaign using weighted choice.
    Updates last_used_at on the CampaignCarrier entry to enable simple round-robin.
    Returns Carrier instance or None.
    """
    qs = campaign.campaign_carriers.select_related('carrier', 'carrier__asterisk_server')\
        .filter(carrier__is_active=True, carrier__asterisk_server__is_active=True)
    carriers = list(qs)
    if not carriers:
        return None
    weights = [(c.weight or 1) for c in carriers]
    chosen_cc = random.choices(carriers, weights=weights, k=1)[0]
    chosen_cc.last_used_at = timezone.now()
    chosen_cc.save(update_fields=['last_used_at', 'updated_at'])
    return chosen_cc.carrier


def build_dial_number(phone_number: str, campaign=None, carrier=None) -> str:
    """
    Apply campaign and carrier prefixes to the raw number.
    Carrier prefix is applied first, then campaign prefix (if any).
    """
    prefix = ''
    if carrier and getattr(carrier, 'dial_prefix', ''):
        prefix += carrier.dial_prefix
    if campaign and getattr(campaign, 'dial_prefix', ''):
        prefix += campaign.dial_prefix
    return f\"{prefix}{phone_number}\" if prefix else phone_number


def build_call_variables(
    call_type: str,
    campaign=None,
    queue_item=None,
    agent=None,
    carrier=None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Assemble channel variables used during originate and in the ARI app.
    """
    vars = {
        'CALL_TYPE': call_type,
    }
    if campaign:
        vars['CAMPAIGN_ID'] = str(campaign.id)
    if queue_item:
        vars['QUEUE_ID'] = str(queue_item.id)
        if getattr(queue_item, 'lead_id', None):
            vars['LEAD_ID'] = str(queue_item.lead_id)
        if getattr(queue_item, 'phone_number', None):
            vars['CUSTOMER_NUMBER'] = queue_item.phone_number
    if agent:
        vars['AGENT_ID'] = str(agent.id)
    if carrier:
        vars['CARRIER_ID'] = str(carrier.id)
    if extra:
        vars.update(extra)
    return vars
