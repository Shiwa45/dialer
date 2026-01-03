# campaigns/services.py

import logging
import json
from decimal import Decimal
from django.utils import timezone
from django.db.models import Count, Q
from datetime import timedelta

from .models import Campaign, CampaignStats, DialerHopper

logger = logging.getLogger(__name__)


class DropRateMonitor:
    """
    Monitor and adjust dial_level based on drop rate to maintain compliance
    """
    
    @staticmethod
    def check_and_adjust_dial_level(campaign):
        """
        Check drop rate for campaign and adjust dial_level if needed
        Returns: dict with status and any adjustments made
        """
        from calls.models import CallLog

        # Get stats for last hour
        one_hour_ago = timezone.now() - timedelta(hours=1)
        
        # Count total answered calls in last hour (Answered time is set)
        answered_calls = CallLog.objects.filter(
            campaign=campaign,
            call_type='outbound',
            start_time__gte=one_hour_ago,
            answer_time__isnull=False
        )
        answered_last_hour = answered_calls.count()
        
        # Count drops: Answered but no agent assigned
        drops_last_hour = answered_calls.filter(
            agent__isnull=True
        ).count()
        
        if answered_last_hour == 0:
            return {
                'status': 'ok',
                'message': 'No calls in last hour',
                'drop_rate': 0,
                'dial_level': float(campaign.dial_level)
            }
        
        # Calculate drop rate
        drop_rate = (drops_last_hour / answered_last_hour) * 100
        target_abandon_rate = float(campaign.abandon_rate)
        
        logger.info(f'{campaign.name}: Drop rate {drop_rate:.2f}% (target: {target_abandon_rate}%)')
        
        # Check if we need to adjust
        if drop_rate > target_abandon_rate:
            # Too many drops - reduce dial_level
            old_level = campaign.dial_level
            new_level = max(Decimal('1.0'), old_level - Decimal('0.1'))
            campaign.dial_level = new_level
            campaign.save(update_fields=['dial_level'])
            
            logger.warning(
                f'{campaign.name}: Drop rate {drop_rate:.2f}% exceeds target {target_abandon_rate}%. '
                f'Reducing dial_level from {old_level} to {new_level}'
            )
            
            return {
                'status': 'reduced',
                'message': f'Dial level reduced from {old_level} to {new_level}',
                'drop_rate': drop_rate,
                'dial_level': float(new_level),
                'old_dial_level': float(old_level)
            }
        
        elif drop_rate < (target_abandon_rate - 1.0) and campaign.dial_level < Decimal('3.0'):
            # Drop rate is well below target and we have room to increase
            old_level = campaign.dial_level
            new_level = min(Decimal('3.0'), old_level + Decimal('0.05'))
            
            # Only increase if we previously reduced
            if new_level > old_level:
                campaign.dial_level = new_level
                campaign.save(update_fields=['dial_level'])
                
                logger.info(
                    f'{campaign.name}: Drop rate {drop_rate:.2f}% is safe. '
                    f'Increasing dial_level from {old_level} to {new_level}'
                )
                
                return {
                    'status': 'increased',
                    'message': f'Dial level increased from {old_level} to {new_level}',
                    'drop_rate': drop_rate,
                    'dial_level': float(new_level),
                    'old_dial_level': float(old_level)
                }
        
        return {
            'status': 'ok',
            'message': 'Dial level unchanged',
            'drop_rate': drop_rate,
            'dial_level': float(campaign.dial_level)
        }
    
    @staticmethod
    def get_drop_rate_stats(campaign, hours=24):
        """Get drop rate statistics for a campaign"""
        from calls.models import CallLog
        
        cutoff = timezone.now() - timedelta(hours=hours)
        
        # Base query for calls in time range
        base_query = CallLog.objects.filter(
            campaign=campaign,
            call_type='outbound',
            start_time__gte=cutoff
        )
        
        total = base_query.count()
        
        # Answered calls
        answered_query = base_query.filter(answer_time__isnull=False)
        answered_count = answered_query.count()
        
        # Dropped calls: Answered but no agent
        dropped = answered_query.filter(agent__isnull=True).count()
        
        # Completed (handled) calls: Answered AND Agent assigned
        completed = answered_query.filter(agent__isnull=False).count()
        
        # Drop rate based on answered calls
        drop_rate = (dropped / answered_count * 100) if answered_count > 0 else 0
        
        return {
            'total_calls': total,
            'answered_calls': answered_count,
            'dropped_calls': dropped,
            'completed_calls': completed,
            'drop_rate': round(drop_rate, 2),
            'target_abandon_rate': float(campaign.abandon_rate),
            'current_dial_level': float(campaign.dial_level),
            'hours': hours
        }


class HopperManager:
    """Utility methods for hopper management"""
    
    @staticmethod
    def get_hopper_stats(campaign):
        """Get current hopper statistics"""
        stats = DialerHopper.objects.filter(campaign=campaign).aggregate(
            total=Count('id'),
            new=Count('id', filter=Q(status='new')),
            locked=Count('id', filter=Q(status='locked')),
            dialing=Count('id', filter=Q(status='dialing')),
            completed=Count('id', filter=Q(status='completed')),
            dropped=Count('id', filter=Q(status='dropped')),
            failed=Count('id', filter=Q(status='failed'))
        )
        
        return {
            'total': stats['total'],
            'new': stats['new'],
            'locked': stats['locked'],
            'dialing': stats['dialing'],
            'completed': stats['completed'],
            'dropped': stats['dropped'],
            'failed': stats['failed'],
            'hopper_level': campaign.hopper_level,
            'hopper_size': campaign.hopper_size
        }
    
    @staticmethod
    def clear_hopper(campaign, status=None):
        """Clear hopper entries for a campaign"""
        query = DialerHopper.objects.filter(campaign=campaign)
        
        if status:
            query = query.filter(status=status)
        else:
            # Only clear non-active entries
            query = query.exclude(status__in=['dialing', 'locked'])
        
        count = query.count()
        query.delete()
        
        logger.info(f'Cleared {count} hopper entries for {campaign.name}')
        return count
    
    @staticmethod
    def reset_stuck_entries(campaign):
        """Reset hopper entries that are stuck in locked/dialing status"""
        # Find entries locked/dialing for more than 5 minutes
        cutoff = timezone.now() - timedelta(minutes=5)
        
        stuck_entries = DialerHopper.objects.filter(
            campaign=campaign,
            status__in=['locked', 'dialing'],
            updated_at__lt=cutoff
        )
        
        count = stuck_entries.count()
        stuck_entries.update(status='new', locked_by=None, locked_at=None)
        
        logger.info(f'Reset {count} stuck hopper entries for {campaign.name}')
        return count


class HopperService:
    """
    Redis-backed Hopper Service for high-performance dialing
    
    Data Structures:
    - campaign:{id}:hopper (List) - Lead IDs waiting to dial
    - campaign:{id}:dialing (Set) - Lead IDs currently being dialed
    - lead:{id}:data (Hash) - Cached lead details
    """
    
    @staticmethod
    def get_redis():
        from django_redis import get_redis_connection
        return get_redis_connection("default")
        
    @staticmethod
    def add_leads(campaign_id, leads):
        """
        Add leads to Redis hopper and cache their data
        """
        r = HopperService.get_redis()
        pipe = r.pipeline()
        
        hopper_key = f"campaign:{campaign_id}:hopper"
        
        added_count = 0
        for lead in leads:
            # Cache lead data
            lead_key = f"lead:{lead.id}:data"
            lead_data = {
                'id': lead.id,
                'phone_number': lead.phone_number,
                'first_name': lead.first_name,
                'last_name': lead.last_name,
                'call_count': lead.call_count,
            }
            pipe.hmset(lead_key, lead_data)
            pipe.expire(lead_key, 3600)  # Cache for 1 hour
            
            # Add to hopper list (push to right/tail)
            pipe.rpush(hopper_key, lead.id)
            added_count += 1
            
        pipe.execute()
        return added_count

    @staticmethod
    def get_next_leads(campaign_id, count=1):
        """
        Pop leads from the hopper
        Fallback to database if Redis cache is missing
        """
        from leads.models import Lead
        
        r = HopperService.get_redis()
        hopper_key = f"campaign:{campaign_id}:hopper"
        
        leads = []
        # Pop 'count' items from left/head
        for _ in range(count):
            lead_id = r.lpop(hopper_key)
            if lead_id:
                lead_id = int(lead_id)
                
                # Try to fetch cached data first
                lead_key = f"lead:{lead_id}:data"
                data = r.hgetall(lead_key)
                
                if data:
                    # Convert bytes to string
                    clean_data = {k.decode('utf-8'): v.decode('utf-8') for k, v in data.items()}
                    leads.append(clean_data)
                else:
                    # Cache miss - fetch from database
                    try:
                        lead = Lead.objects.get(id=lead_id)
                        lead_data = {
                            'id': str(lead.id),
                            'phone_number': lead.phone_number,
                            'first_name': lead.first_name or '',
                            'last_name': lead.last_name or '',
                            'call_count': str(lead.call_count),
                        }
                        
                        # Cache it for next time
                        r.hmset(lead_key, lead_data)
                        r.expire(lead_key, 3600)  # Cache for 1 hour
                        
                        leads.append(lead_data)
                    except Lead.DoesNotExist:
                        logger.warning(f"Lead {lead_id} not found in database")
                        continue
            else:
                break
                
        return leads

    @staticmethod
    def get_hopper_count(campaign_id):
        """Get number of leads in hopper"""
        r = HopperService.get_redis()
        return r.llen(f"campaign:{campaign_id}:hopper")

    @staticmethod
    def register_dialing(campaign_id, lead_id):
        """Mark a lead as currently being dialed"""
        r = HopperService.get_redis()
        r.sadd(f"campaign:{campaign_id}:dialing", lead_id)

    @staticmethod
    def unregister_dialing(campaign_id, lead_id):
        """Remove a lead from dialing set (call ended)"""
        r = HopperService.get_redis()
        r.srem(f"campaign:{campaign_id}:dialing", lead_id)
        
    @staticmethod
    def get_active_call_count(campaign_id):
        """Get count of currently dialing leads"""
        r = HopperService.get_redis()
        return r.scard(f"campaign:{campaign_id}:dialing")
        
    @staticmethod
    def get_queued_lead_ids(campaign_id):
        """Get all lead IDs currently in hopper or being dialed"""
        r = HopperService.get_redis()
        hopper_key = f"campaign:{campaign_id}:hopper"
        dialing_key = f"campaign:{campaign_id}:dialing"
        
        # Get all from list
        hopper_ids = r.lrange(hopper_key, 0, -1)
        # Get all from set
        dialing_ids = r.smembers(dialing_key)
        
        # Combine and convert to int
        all_ids = set()
        for lid in hopper_ids:
            all_ids.add(int(lid))
        for lid in dialing_ids:
            all_ids.add(int(lid))
            
        return all_ids

    @staticmethod
    def clear_hopper(campaign_id):
        """Clear the Redis hopper"""
        r = HopperService.get_redis()
        r.delete(f"campaign:{campaign_id}:hopper")
