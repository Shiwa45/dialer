# Phase 8 - Sarvam AI Agent System - DEPLOYMENT GUIDE

---

## 📋 Complete Installation Checklist

### Pre-requisites
- ✅ Django project with Asterisk ARI integration (you have this!)
- ✅ Celery + Redis configured
- ✅ Asterisk server with ARI enabled
- ✅ Python 3.8+

---

## STEP 1: Install Dependencies

```bash
pip install requests
pip install pydub  # Optional: for long-text TTS
```

---

## STEP 2: Add Sarvam API Key

```python
# settings.py

# Add this line:
SARVAM_API_KEY = 'your_api_key_here'  # Get from console.sarvam.ai

# Also ensure this exists:
TTS_AUDIO_DIR = str(BASE_DIR / 'media' / 'tts')
```

---

## STEP 3: Copy All Files

```bash
# Copy Phase 8 files to your project:

# Core AI Engine (Phase 8.1)
sarvam/asr_service.py
sarvam/intent_detector.py
sarvam/ai_conversation_engine.py
sarvam/action_executor.py

# ARI Integration (Phase 8.2)
sarvam/ai_call_handler.py
campaigns/models_ai_fields.py  # Add to your models.py
campaigns/migrations/0XXX_add_ai_agent_fields.py
telephony/ari_worker_ai_integration.py  # Add to your ari_worker.py
templates/campaigns/ai_agent_config.html

# Views & Tasks (Phase 8.3)
campaigns/views_ai.py
campaigns/tasks_ai.py  # Add to your tasks.py
campaigns/urls_ai.py  # Add to your urls.py
sarvam/management/commands/test_ai_agent.py
```

---

## STEP 4: Update Campaign Model

### Open `campaigns/models.py` and add the AI fields:

```python
# At the end of your Campaign model class, add:

from campaigns.models_ai_fields import Campaign as AICampaign

# Copy all the ai_* fields from models_ai_fields.py
# (17 fields starting with ai_enabled, ai_language, etc.)

# Also add the methods:
def get_ai_config(self):
    # ... copy from models_ai_fields.py

def increment_ai_call_stats(self, success=False, transferred=False, appointment_booked=False):
    # ... copy from models_ai_fields.py
```

### Do the same for CallLog model:

```python
# In calls/models.py CallLog class, add:
# handled_by_ai, ai_conversation_transcript, etc.
# (8 fields - copy from models_ai_fields.py)
```

---

## STEP 5: Run Database Migrations

```bash
# Create migration
python manage.py makemigrations campaigns
python manage.py makemigrations calls

# Apply migration
python manage.py migrate campaigns
python manage.py migrate calls
```

---

## STEP 6: Integrate with ARI Worker

### Open `telephony/management/commands/ari_worker.py`

Add these imports at the top:
```python
import asyncio
from sarvam.ai_call_handler import AICallHandler
```

Then in your `_handle_stasis_start` method, ADD THIS CODE AT THE VERY BEGINNING:

```python
def _handle_stasis_start(self, server, chan_id, bridge_id, call_type, agent_id, 
                         target_agent_id, campaign_id, lead_id, hopper_id, 
                         customer_number, queue_id, amd_status=None):
    
    # ═══════════════════════════════════════════════════════════
    # PHASE 8: AI CHECK - ADD THIS FIRST!
    # ═══════════════════════════════════════════════════════════
    
    if campaign_id and call_type in ['autodial', 'outbound']:
        try:
            from campaigns.models import Campaign
            campaign = Campaign.objects.get(id=campaign_id)
            
            if campaign.ai_enabled:
                logger.info(f"🤖 AI-enabled campaign detected: {campaign_id}")
                
                # Get lead
                lead = None
                if lead_id:
                    from leads.models import Lead
                    try:
                        lead = Lead.objects.get(id=lead_id)
                    except Lead.DoesNotExist:
                        pass
                
                # Get or create call log
                from calls.models import CallLog
                call_log, created = CallLog.objects.get_or_create(
                    channel_id=chan_id,
                    defaults={
                        'campaign_id': campaign_id,
                        'lead_id': lead_id,
                        'called_number': customer_number or '',
                        'call_type': call_type,
                        'call_status': 'answered',
                        'handled_by_ai': True,
                    }
                )
                
                if not created:
                    call_log.handled_by_ai = True
                    call_log.save()
                
                # Get AI config
                ai_config = campaign.get_ai_config()
                
                # Create Asterisk service
                from telephony.services import AsteriskService
                asterisk = AsteriskService(server)
                
                # Launch AI handler
                ai_handler = AICallHandler(
                    asterisk_service=asterisk,
                    channel_id=chan_id,
                    call_log=call_log,
                    lead=lead,
                    language=ai_config['language'],
                    agent_name=ai_config['agent_name'],
                    company_name=ai_config['company_name'],
                )
                
                # Run AI handler
                asyncio.create_task(ai_handler.start())
                
                # Update stats
                campaign.increment_ai_call_stats()
                
                # Exit early - AI is handling this call
                logger.info(f"✅ AI handler launched for call {chan_id}")
                return
        
        except Campaign.DoesNotExist:
            logger.warning(f"Campaign {campaign_id} not found")
        except Exception as e:
            logger.error(f"AI handler launch error: {e}", exc_info=True)
    
    # ═══════════════════════════════════════════════════════════
    # YOUR EXISTING CODE CONTINUES HERE
    # (AMD handling, bridge logic, agent routing, etc.)
    # ═══════════════════════════════════════════════════════════
    
    if amd_status:
        # ... your existing AMD code ...
        pass
    
    # ... rest of your existing code ...
```

---

## STEP 7: Add URL Patterns

### In `campaigns/urls.py`, add:

```python
from campaigns import views_ai

urlpatterns = [
    # ... existing patterns ...
    
    # AI Agent URLs
    path('<int:campaign_id>/ai-config/', views_ai.ai_agent_config, name='ai_agent_config'),
    path('<int:campaign_id>/ai-toggle/', views_ai.toggle_ai_enabled, name='toggle_ai_enabled'),
    path('<int:campaign_id>/test-ai-call/', views_ai.test_ai_call, name='test_ai_call'),
    path('<int:campaign_id>/ai-calls/', views_ai.ai_call_history, name='ai_call_history'),
    path('ai-calls/<int:call_id>/transcript/', views_ai.ai_call_transcript, name='ai_call_transcript'),
    path('<int:campaign_id>/ai-stats/', views_ai.ai_stats_api, name='ai_stats_api'),
]
```

---

## STEP 8: Add Celery Tasks

### In `campaigns/tasks.py`, add:

```python
# Copy the tasks from tasks_ai.py:
# - make_ai_outbound_call
# - process_ai_call_queue
```

---

## STEP 9: Create Required Directories

```bash
mkdir -p /tmp/ai_recordings
chmod 777 /tmp/ai_recordings

mkdir -p media/tts
chmod 777 media/tts
```

---

## STEP 10: Test the System

### Test 1: Run the test command

```bash
python manage.py test_ai_agent --language hi-IN --simulate-call
```

Expected output:
```
==========================================
AI Agent Test Suite
==========================================

📝 Test 1: ASR Service
  ✅ ASR configured (API key present)

🧠 Test 2: Intent Detection
  ✅ "मुझे अपॉइंटमेंट बुक करना है" → book_appointment
  ✅ "कीमत क्या है?" → pricing_inquiry
  📊 Accuracy: 100% (5/5)

💬 Test 3: Conversation Engine
  ✅ Conversation engine working

🎙️  Test 4: TTS Service
  ✅ TTS generated: /media/tts/test_abc123.wav

⚡ Test 5: Action Executor
  ✅ Action executor working

📞 Test 6: Full Call Simulation
  [Shows full conversation flow]

✅ All tests completed!
```

### Test 2: Access AI Config Page

1. Navigate to: `http://localhost:8000/campaigns/1/ai-config/`
2. Enable AI toggle
3. Select language: Hindi
4. Save configuration

### Test 3: Make a Test Call

1. In AI config page, click "Test AI Call"
2. Enter your phone number
3. You should receive a call from the AI agent!

---

## STEP 11: Enable for Production Campaign

### Via Admin UI:
1. Go to: `/campaigns/<campaign_id>/ai-config/`
2. Toggle "Enable AI Agent" → ON
3. Configure:
   - Language: Hindi (hi-IN)
   - Agent Name: सीमा
   - Voice: aditya
   - Enable: "Can Book Appointments"
4. Click "Save Configuration"

### Via Django Shell:
```python
from campaigns.models import Campaign

campaign = Campaign.objects.get(id=1)
campaign.ai_enabled = True
campaign.ai_language = 'hi-IN'
campaign.ai_agent_name = 'सीमा'
campaign.ai_voice = 'aditya'
campaign.ai_can_book_appointments = True
campaign.save()

print(f"✅ AI enabled for: {campaign.name}")
```

---

## 🎯 Usage

### Making AI Calls:

**Option 1: Via Celery Task (Recommended)**
```python
from campaigns.tasks import make_ai_outbound_call

result = make_ai_outbound_call.delay(
    lead_id=123,
    campaign_id=1,
)
```

**Option 2: Via Admin UI**
- Click "Test AI Call" button in campaign AI config page

**Option 3: Automated Queue Processing**
```bash
# Add to Celery Beat schedule in settings.py:
'process-ai-call-queues': {
    'task': 'campaigns.tasks.process_ai_call_queue',
    'schedule': 60.0,
    'kwargs': {'campaign_id': 1, 'max_calls': 10}
}
```

---

## 📊 Monitoring

### View AI Stats:
- Navigate to: `/campaigns/<campaign_id>/ai-config/`
- Stats show:
  - Total AI calls
  - Successful calls (no transfer)
  - Transferred to human
  - Appointments booked
  - Success rate %

### View Call Transcripts:
- Navigate to: `/campaigns/<campaign_id>/ai-calls/`
- Click on any call to see full transcript

---

## 🐛 Troubleshooting

### Issue: "AI not launching"
**Check:**
1. `campaign.ai_enabled = True`
2. Sarvam API key configured
3. ARI worker integration added
4. Check logs: `tail -f logs/autodialer.log | grep AI`

### Issue: "No audio generated"
**Check:**
1. Sarvam API key valid
2. TTS_AUDIO_DIR exists and writable
3. Check: `python manage.py test_ai_agent`

### Issue: "Call doesn't enter Stasis"
**Check:**
1. Asterisk dialplan sends to `Stasis(autodialer,...)`
2. Channel variables set correctly
3. Check Asterisk logs: `asterisk -rx "core show channels"`

---

## 🎉 Success Criteria

You know it's working when:
1. ✅ Test command passes all tests
2. ✅ AI config page loads without errors
3. ✅ Test call connects and AI speaks
4. ✅ AI responds to customer speech
5. ✅ Stats increment after calls
6. ✅ Transcripts saved in database

---

## 📚 Next Steps

1. **Train your team** on AI configuration
2. **Start with 1 campaign** to test
3. **Monitor stats daily** for first week
4. **Adjust prompts** based on feedback
5. **Scale to more campaigns** after validation

---

**Need help? Check logs or run: `python manage.py test_ai_agent`**
