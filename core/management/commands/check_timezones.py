"""
management/commands/check_timezones.py  –  Phase 4

Usage
-----
    python manage.py check_timezones              # report only
    python manage.py check_timezones --fix        # repair bad values
    python manage.py check_timezones --set-system Asia/Kolkata
"""

from django.core.management.base import BaseCommand
from core.timezone_utils import ALL_TIMEZONES, get_system_timezone, set_system_timezone

VALID_TZ = {tz[0] for tz in ALL_TIMEZONES}


class Command(BaseCommand):
    help = 'Audit and repair timezone configuration across the system'

    def add_arguments(self, parser):
        parser.add_argument('--fix', action='store_true',
                            help='Auto-fix invalid timezone values (reset to system default)')
        parser.add_argument('--set-system', metavar='TZ',
                            help='Set the system-wide default timezone (e.g. Asia/Kolkata)')

    # ──────────────────────────────────────
    def handle(self, *args, **options):
        W = self.style.WARNING
        S = self.style.SUCCESS
        E = self.style.ERROR
        line = '─' * 65

        self.stdout.write(S(line))
        self.stdout.write(S('Phase 4 – Timezone Audit'))
        self.stdout.write(S(line))

        # ── 0. Set system tz if requested ──────────────────────────────
        if options['set_system']:
            tz = options['set_system'].strip()
            ok = set_system_timezone(tz)
            if ok:
                self.stdout.write(S(f'✅  System timezone set to: {tz}'))
            else:
                self.stdout.write(E(f'❌  Invalid timezone: {tz}'))
            return

        # ── 1. System timezone ────────────────────────────────────────
        sys_tz = get_system_timezone()
        self.stdout.write(f'\nSystem timezone : {sys_tz}')
        if sys_tz not in VALID_TZ:
            self.stdout.write(W(f'  ⚠  "{sys_tz}" is not in the standard list'))

        # ── 2. Campaign timezones ─────────────────────────────────────
        self.stdout.write('\n── Campaign timezones ──')
        try:
            from campaigns.models import Campaign
            bad_campaigns = []
            for c in Campaign.objects.only('id', 'name', 'timezone'):
                tz = (c.timezone or '').strip()
                if tz and tz not in VALID_TZ:
                    bad_campaigns.append(c)
                    self.stdout.write(W(f'  ⚠  Campaign #{c.id} "{c.name}": bad tz = "{tz}"'))

            if not bad_campaigns:
                self.stdout.write(S('  ✅  All campaigns have valid timezones'))
            elif options['fix']:
                Campaign.objects.filter(
                    id__in=[c.id for c in bad_campaigns]
                ).update(timezone=sys_tz)
                self.stdout.write(S(f'  Fixed {len(bad_campaigns)} campaign(s) → {sys_tz}'))

        except Exception as e:
            self.stdout.write(E(f'  Error checking campaigns: {e}'))

        # ── 3. User profile timezones ─────────────────────────────────
        self.stdout.write('\n── User profile timezones ──')
        try:
            from django.contrib.auth.models import User
            bad_users = []
            for u in User.objects.select_related('profile').all():
                try:
                    tz = (u.profile.timezone or '').strip()
                    if tz and tz not in VALID_TZ:
                        bad_users.append(u)
                        self.stdout.write(W(f'  ⚠  User "{u.username}": bad tz = "{tz}"'))
                except Exception:
                    pass

            if not bad_users:
                self.stdout.write(S('  ✅  All user profiles have valid timezones'))
            elif options['fix']:
                for u in bad_users:
                    u.profile.timezone = ''
                    u.profile.save(update_fields=['timezone'])
                self.stdout.write(S(f'  Cleared timezone for {len(bad_users)} user(s) (will use system default)'))

        except Exception as e:
            self.stdout.write(E(f'  Error checking user profiles: {e}'))

        # ── 4. Django settings audit ───────────────────────────────────
        self.stdout.write('\n── Django settings ──')
        from django.conf import settings as dj_settings
        use_tz   = getattr(dj_settings, 'USE_TZ', False)
        dj_tz    = getattr(dj_settings, 'TIME_ZONE', 'UTC')

        self.stdout.write(f'  USE_TZ    = {use_tz}')
        self.stdout.write(f'  TIME_ZONE = {dj_tz}  (DB storage — should stay UTC)')

        if not use_tz:
            self.stdout.write(E('  ❌  USE_TZ is False — set USE_TZ = True in settings.py'))
        else:
            self.stdout.write(S('  ✅  USE_TZ = True (correct)'))

        if dj_tz != 'UTC':
            self.stdout.write(W(f'  ⚠  TIME_ZONE should be "UTC" for correct DB storage; display TZ is handled by middleware'))
        else:
            self.stdout.write(S('  ✅  TIME_ZONE = "UTC" (correct)'))

        # ── 5. Middleware check ───────────────────────────────────────
        self.stdout.write('\n── Middleware check ──')
        mw_list = getattr(dj_settings, 'MIDDLEWARE', [])
        if 'core.middleware.TimezoneMiddleware' in mw_list:
            self.stdout.write(S('  ✅  TimezoneMiddleware is installed'))
        else:
            self.stdout.write(W(
                '  ⚠  TimezoneMiddleware not found in MIDDLEWARE.\n'
                '     Add  "core.middleware.TimezoneMiddleware"  to settings.MIDDLEWARE.'
            ))

        self.stdout.write('')
        self.stdout.write(S(line))
        self.stdout.write(S('Audit complete'))
        self.stdout.write(S(line))
