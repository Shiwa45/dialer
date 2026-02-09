from django.core.management.base import BaseCommand
from django.utils import timezone
from agents.models import AgentDialerSession
from users.models import AgentStatus

class Command(BaseCommand):
    help = 'Reset status of all agents to offline and clear stuck sessions'

    def handle(self, *args, **options):
        self.stdout.write('Resetting agent statuses...')

        # 1. Reset AgentStatus
        updated_count = AgentStatus.objects.exclude(status='offline').update(
            status='offline',
            current_call_id='',
            call_start_time=None,
            break_reason='',
            status_changed_at=timezone.now()
        )
        self.stdout.write(self.style.SUCCESS(f'Reset {updated_count} AgentStatus records to offline'))

        # 2. Close stuck AgentDialerSessions
        # Find sessions that are not 'offline' or 'error' and don't have an ended_at time
        stuck_sessions = AgentDialerSession.objects.filter(
            ended_at__isnull=True
        ).exclude(status__in=['offline', 'error'])
        
        sessions_count = stuck_sessions.count()
        if sessions_count > 0:
            stuck_sessions.update(
                status='offline',
                ended_at=timezone.now(),
                last_error='Session force closed by reset_agent_status command'
            )
            self.stdout.write(self.style.SUCCESS(f'Closed {sessions_count} stuck AgentDialerSessions'))
        else:
            self.stdout.write('No stuck AgentDialerSessions found')

        self.stdout.write(self.style.SUCCESS('Agent status reset complete'))
