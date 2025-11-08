from django.core.management.base import BaseCommand
from telephony.models import Carrier, DialplanContext, DialplanExtension, PsEndpoint, PsAuth, PsAor, ExtensionsTable


class Command(BaseCommand):
    help = "Sync carriers and dialplan to Asterisk realtime tables (ps_* and extensions_table)."

    def handle(self, *args, **options):
        created_updated = 0
        # Sync PJSIP carriers to realtime
        for c in Carrier.objects.filter(is_active=True, protocol__iexact='pjsip'):
            endpoint_id = c.name
            contact_uri = f"sip:{c.server_ip}:{c.port}"
            PsEndpoint.objects.update_or_create(
                id=endpoint_id,
                defaults={
                    'aors': endpoint_id,
                    'auth': endpoint_id,
                    'context': 'from-campaign',
                    'allow': c.codec.replace(' ', ''),
                    'disallow': 'all',
                    'direct_media': 'no',
                    'force_rport': 'yes',
                    'rewrite_contact': 'yes',
                }
            )
            PsAuth.objects.update_or_create(
                id=endpoint_id,
                defaults={
                    'auth_type': 'userpass',
                    'username': c.auth_username or c.username,
                    'password': c.password,
                    'realm': ''
                }
            )
            PsAor.objects.update_or_create(
                id=endpoint_id,
                defaults={
                    'max_contacts': 1,
                    'remove_existing': 'yes',
                    'qualify_frequency': 60,
                    'contact': contact_uri,
                }
            )
            created_updated += 1

        # Sync Dialplan contexts/extensions to extensions_table
        for dpe in DialplanExtension.objects.filter(is_active=True, context__is_active=True).select_related('context'):
            ExtensionsTable.objects.update_or_create(
                context=dpe.context.name,
                exten=dpe.extension,
                priority=dpe.priority,
                defaults={'app': dpe.application, 'appdata': dpe.arguments or ''}
            )
            created_updated += 1

        self.stdout.write(self.style.SUCCESS(f"Asterisk realtime sync complete. Objects updated: {created_updated}"))

