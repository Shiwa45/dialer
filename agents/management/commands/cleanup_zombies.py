# agents/management/commands/cleanup_zombies.py
# Usage: python manage.py cleanup_zombies [--timeout-minutes 5] [--dry-run]

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Q


class Command(BaseCommand):
    help = "Mark zombie agent sessions as offline (agents with stale heartbeats)"

    def add_arguments(self, parser):
        parser.add_argument(
            '--timeout-minutes', type=int, default=5,
            help='Minutes without heartbeat to consider agent a zombie (default: 5)',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Show zombies without marking them offline',
        )

    def handle(self, *args, **options):
        from users.models import AgentStatus

        timeout = options['timeout_minutes']
        dry_run = options['dry_run']
        cutoff  = timezone.now() - timezone.timedelta(minutes=timeout)

        zombies = AgentStatus.objects.exclude(status='offline').filter(
            Q(last_heartbeat__lt=cutoff) |
            Q(last_heartbeat__isnull=True, status_changed_at__lt=cutoff)
        ).select_related('user')

        count = zombies.count()
        self.stdout.write(f"\nZombie agent check (timeout={timeout}min):")
        self.stdout.write(f"Found {count} zombie(s)\n")

        now = timezone.now()
        for ag in zombies:
            hb = ag.last_heartbeat.strftime('%H:%M:%S') if ag.last_heartbeat else 'never'
            self.stdout.write(
                f"  {ag.user.username:<20} status={ag.status:<12} "
                f"last_heartbeat={hb}"
            )
            if not dry_run:
                try:
                    ag._close_time_log(ended_at=now)
                    ag.status = 'offline'
                    ag.current_call_id = ''
                    ag.wrapup_call_id  = ''
                    ag.save()
                    ag._open_time_log(status='offline', started_at=now)
                    self.stdout.write(self.style.SUCCESS('    → Marked offline'))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'    → Error: {e}'))

        if dry_run:
            self.stdout.write(self.style.WARNING('\nDry run — no changes made'))
        else:
            self.stdout.write(self.style.SUCCESS(f'\nDone: {count} zombie(s) cleaned'))
