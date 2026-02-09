import logging
import random
from collections import defaultdict
from django.db import transaction
from .models import Carrier, DialplanContext, DialplanExtension

logger = logging.getLogger(__name__)

class DialplanService:
    @staticmethod
    def regenerate_dialplan():
        """
        Regenerate the entire 'from-campaign' dialplan context based on active carriers.
        Supports load balancing for carriers with the same prefix.
        """
        logger.info("Regenerating dialplan for from-campaign context")
        
        with transaction.atomic():
            # Get or create the context
            ctx, _ = DialplanContext.objects.get_or_create(
                name='from-campaign',
                defaults={
                    'description': 'Auto-generated outbound routing',
                    'is_active': True,
                    # Assign to first available server if not set (fallback)
                    # Realworld scenario might need more specific server selection
                }
            )
            
            # If new context created without server, try to assign one
            if not ctx.asterisk_server:
                from .models import AsteriskServer
                server = AsteriskServer.objects.first()
                if server:
                    ctx.asterisk_server = server
                    ctx.save()
            
            # clear existing extensions in this context
            DialplanExtension.objects.filter(context=ctx).delete()
            
            # Group active carriers by prefix
            carriers_by_prefix = defaultdict(list)
            active_carriers = Carrier.objects.filter(is_active=True).order_by('priority')
            
            for carrier in active_carriers:
                prefix = carrier.dial_prefix
                # key by prefix, default to 'default' if empty (though usually required)
                key = prefix if prefix else '_' 
                carriers_by_prefix[key].append(carrier)
            
            # Generate dialplan for each prefix group
            for prefix, carriers in carriers_by_prefix.items():
                if prefix == '_':
                    # Skip carriers without prefix for now, or handle as catch-all
                    continue
                
                DialplanService._generate_prefix_logic(ctx, prefix, carriers)
                
    @staticmethod
    def _generate_prefix_logic(ctx, prefix, carriers):
        """
        Generate dialplan extensions for a specific prefix and list of carriers
        """
        pattern = f"_{prefix}X."
        strip_len = len(prefix)
        priority = 1
        
        # Common start: Log and Strip
        DialplanExtension.objects.create(
            context=ctx, extension=pattern, priority=priority,
            application='NoOp', arguments=f'Outbound for prefix {prefix} via {len(carriers)} carriers', is_active=True
        ); priority += 1
        
        DialplanExtension.objects.create(
            context=ctx, extension=pattern, priority=priority,
            application='Set', arguments=f'STRIPPED=${{EXTEN:{strip_len}}}', is_active=True
        ); priority += 1

        if len(carriers) == 1:
            # Simple case: Single carrier
            carrier = carriers[0]
            DialplanService._generate_dial_block(ctx, pattern, carrier, priority)
        else:
            # Multi-carrier randomization
            # We use RAND() to pick a carrier and Jump to a specific extension
            # This avoids using Priority Labels which can be tricky in Realtime
            
            count = len(carriers)
            DialplanExtension.objects.create(
               context=ctx, extension=pattern, priority=priority,
               application='Set', arguments=f'target=${{RAND(1,{count})}}', is_active=True
            ); priority += 1
            
            for i, carrier in enumerate(carriers, 1):
                 # We simply branch to a specific priority for each carrier?
                 # Since we cannot easily use labels in DB-based dialplan (usually), 
                 # we will implement a slightly different pattern:
                 # We will create specific extensions for each carrier: _9119X.-carrier1, _9119X.-carrier2
                 # And existing _9119X. will just Goto one of them.
                 
                 carrier_ext = f"{prefix}X.-{carrier.name}-{carrier.id}"
                 
                 # Create the GotoIf in main pattern
                 DialplanExtension.objects.create(
                    context=ctx, extension=pattern, priority=priority,
                    application='GotoIf', arguments=f'$[${{target}} = {i}]?{carrier_ext},1', is_active=True
                 ); priority += 1
                 
                 # Create the specific extension for this carrier
                 c_prio = 1
                 DialplanExtension.objects.create(
                    context=ctx, extension=carrier_ext, priority=c_prio,
                    application='NoOp', arguments=f'Dialing via {carrier.name}', is_active=True
                 ); c_prio += 1
                 
                 DialplanExtension.objects.create(
                    context=ctx, extension=carrier_ext, priority=c_prio,
                    # We need to re-calculate STRIPPED or pass it? 
                    # Set STRIPPED in main pattern used EXTEN. Here EXTEN is different.
                    # We can pass STRIPPED variable if it inherits channel vars. Yes.
                    # Or just use the original ${STRIPPED} set in main pattern.
                    application='Dial', 
                    arguments=f'PJSIP/{carrier.name}/${{STRIPPED}},{carrier.dial_timeout}', 
                    is_active=True
                 ); c_prio += 1
                 
                 DialplanExtension.objects.create(
                    context=ctx, extension=carrier_ext, priority=c_prio,
                    application='Hangup', arguments='', is_active=True
                 )

    @staticmethod
    def _generate_dial_block(ctx, pattern, carrier, start_priority):
        """
        Helper to generate standard dial block
        """
        pr = start_priority
        DialplanExtension.objects.create(
            context=ctx, extension=pattern, priority=pr,
            application='Dial', 
            arguments=f'PJSIP/{carrier.name}/${{STRIPPED}},{carrier.dial_timeout}', 
            is_active=True
        ); pr += 1
        
        DialplanExtension.objects.create(
            context=ctx, extension=pattern, priority=pr,
            application='Hangup', arguments='', is_active=True
        )
