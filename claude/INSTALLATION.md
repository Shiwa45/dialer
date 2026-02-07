# Phase 4: Advanced Features - Installation Guide

This document provides instructions for implementing Phase 4 advanced features.

## Overview of Phase 4 Features

| Feature | Description | Files |
|---------|-------------|-------|
| **4.1** | Predictive Dialer + AMD | `predictive_dialer.py`, `amd_service.py` |
| **4.2** | Call Scoring & Quality | `quality_scoring.py`, `supervisor_monitoring.html` |
| **4.3** | Advanced Analytics | `analytics.py`, `analytics_dashboard.html` |

---

## Files Included

```
phase4_fixes/
├── INSTALLATION.md                          # This file
├── campaigns/
│   ├── predictive_dialer.py                # Predictive dialing algorithm
│   └── amd_service.py                      # AMD integration
├── calls/
│   └── quality_scoring.py                  # Call scoring & monitoring
├── reports/
│   ├── analytics.py                        # Analytics engine
│   └── templates/reports/
│       └── analytics_dashboard.html        # Analytics UI
└── agents/
    └── templates/agents/
        └── supervisor_monitoring.html      # Monitoring UI
```

---

## Phase 4.1: Predictive Dialer & AMD

### Step 1: Install Predictive Dialer

1. **Copy the predictive dialer:**
   ```bash
   cp phase4_fixes/campaigns/predictive_dialer.py campaigns/
   cp phase4_fixes/campaigns/amd_service.py campaigns/
   ```

2. **Add Campaign model fields:**
   ```python
   # campaigns/models.py
   
   class Campaign(models.Model):
       # ... existing fields ...
       
       # Predictive dialer settings
       dial_mode = models.CharField(
           max_length=20,
           choices=[
               ('predictive', 'Predictive'),
               ('progressive', 'Progressive'),
               ('power', 'Power'),
               ('preview', 'Preview'),
           ],
           default='predictive'
       )
       target_abandon_rate = models.FloatField(default=3.0)
       max_dial_ratio = models.FloatField(default=3.0)
       avg_talk_time = models.IntegerField(default=180)
       wrapup_time = models.IntegerField(default=30)
       
       # AMD settings
       amd_enabled = models.BooleanField(default=False)
       amd_action = models.CharField(
           max_length=20,
           choices=[
               ('hangup', 'Hangup'),
               ('voicemail', 'Drop Voicemail'),
               ('transfer', 'Transfer'),
           ],
           default='hangup'
       )
       voicemail_file = models.FileField(
           upload_to='voicemail/',
           blank=True,
           null=True
       )
   ```

3. **Run migrations:**
   ```bash
   python manage.py makemigrations campaigns
   python manage.py migrate
   ```

4. **Add Celery task for predictive dialing:**
   ```python
   # campaigns/tasks.py
   
   from campaigns.predictive_dialer import DialerManager
   
   @shared_task
   def predictive_dial():
       '''Runs every second to dial calls based on predictive algorithm'''
       from campaigns.models import Campaign
       
       total_dialed = 0
       
       for campaign in Campaign.objects.filter(status='active', dial_mode='predictive'):
           try:
               dialed = DialerManager.dial_for_campaign(campaign.id)
               total_dialed += dialed
           except Exception as e:
               logger.error(f"Error dialing for campaign {campaign.id}: {e}")
       
       return {'dialed': total_dialed}
   ```

5. **Update Celery Beat schedule:**
   ```python
   # settings.py or celery.py
   
   CELERY_BEAT_SCHEDULE = {
       # ... existing tasks ...
       'predictive-dial': {
           'task': 'campaigns.tasks.predictive_dial',
           'schedule': 1.0,  # Every second
       },
   }
   ```

### Step 2: Configure AMD in Asterisk

1. **Update Asterisk dialplan:**
   ```
   ; extensions.conf
   
   [autodialer-amd]
   exten => _X.,1,NoOp(Autodialer AMD Call)
    same => n,Answer()
    same => n,AMD(2500,1500,800,5000,100,50,3,256,5000)
    same => n,GotoIf($["${AMDSTATUS}" = "MACHINE"]?machine:human)
    same => n(human),Stasis(autodialer,human,${AMDSTATUS})
    same => n,Hangup()
    same => n(machine),Stasis(autodialer,machine,${AMDSTATUS})
    same => n,Hangup()
   ```

2. **Update ARI worker to handle AMD:**
   ```python
   # In ari_worker.py _handle_stasis_start()
   
   from campaigns.amd_service import AMDService, AMDResult
   
   amd_service = AMDService()
   
   # Check AMD result from channel variables
   amd_status = channel.get('channelvars', {}).get('AMDSTATUS', '')
   
   if amd_status:
       result = amd_service.parse_amd_result(amd_status)
       
       if not amd_service.should_connect_to_agent(result):
           # Don't connect to agent - hangup or voicemail
           await self._hangup_channel(channel_id)
           return
   ```

---

## Phase 4.2: Call Scoring & Quality Monitoring

### Step 1: Install Quality Scoring

1. **Copy quality scoring module:**
   ```bash
   cp phase4_fixes/calls/quality_scoring.py calls/
   ```

2. **Add CallLog model fields:**
   ```python
   # calls/models.py
   
   class CallLog(models.Model):
       # ... existing fields ...
       
       # Quality fields
       quality_score = models.FloatField(null=True, blank=True)
       hold_duration = models.IntegerField(null=True, blank=True)
       amd_result = models.CharField(max_length=20, blank=True)
       amd_action = models.CharField(max_length=20, blank=True)
       ring_duration = models.IntegerField(null=True, blank=True)
   ```

3. **Create CallQualityScore model:**
   ```python
   # calls/models.py
   
   class CallQualityScore(models.Model):
       call = models.OneToOneField(
           'CallLog',
           on_delete=models.CASCADE,
           related_name='quality_details'
       )
       duration_score = models.FloatField(default=0)
       hold_score = models.FloatField(default=0)
       disposition_score = models.FloatField(default=0)
       resolution_score = models.FloatField(default=0)
       total_score = models.FloatField(default=0)
       category = models.CharField(max_length=20, default='average')
       flagged_for_review = models.BooleanField(default=False)
       flag_reason = models.CharField(max_length=200, blank=True)
       reviewed_by = models.ForeignKey(
           'auth.User', on_delete=models.SET_NULL,
           null=True, blank=True
       )
       reviewed_at = models.DateTimeField(null=True, blank=True)
       review_notes = models.TextField(blank=True)
       created_at = models.DateTimeField(auto_now_add=True)
   ```

4. **Run migrations:**
   ```bash
   python manage.py makemigrations calls
   python manage.py migrate
   ```

5. **Add auto-scoring after call ends:**
   ```python
   # In your call end handler
   
   from calls.quality_scoring import CallScorer
   
   scorer = CallScorer()
   scores = scorer.score_call(call_log)
   
   call_log.quality_score = scores['total_score']
   call_log.save()
   
   # Optionally create detailed score record
   CallQualityScore.objects.create(
       call=call_log,
       **scores
   )
   ```

### Step 2: Install Supervisor Monitoring

1. **Copy monitoring template:**
   ```bash
   cp phase4_fixes/agents/templates/agents/supervisor_monitoring.html templates/agents/
   ```

2. **Add monitoring views:**
   ```python
   # reports/views.py
   
   from calls.quality_scoring import SupervisorMonitor
   
   @login_required
   @supervisor_required
   def monitoring_dashboard(request):
       return render(request, 'agents/supervisor_monitoring.html', {
           'campaigns': Campaign.objects.filter(status='active')
       })
   
   @login_required
   @supervisor_required
   def monitoring_agents_api(request):
       # Return list of agents with call status
       ...
   
   @login_required
   @supervisor_required
   @require_POST
   def start_monitoring(request):
       data = json.loads(request.body)
       monitor = SupervisorMonitor(asterisk_service)
       result = monitor.start_monitoring(
           supervisor_channel=get_supervisor_channel(request.user),
           target_channel=get_agent_channel(data['agent_id']),
           mode=MonitorMode(data['mode'])
       )
       return JsonResponse(result)
   ```

3. **Add URL patterns:**
   ```python
   # reports/urls.py
   
   urlpatterns = [
       path('monitoring/', views.monitoring_dashboard, name='monitoring_dashboard'),
       path('api/monitoring/agents/', views.monitoring_agents_api, name='monitoring_agents_api'),
       path('api/monitoring/start/', views.start_monitoring, name='start_monitoring'),
       path('api/monitoring/stop/', views.stop_monitoring, name='stop_monitoring'),
       path('api/monitoring/mode/', views.switch_monitoring_mode, name='switch_monitoring_mode'),
   ]
   ```

---

## Phase 4.3: Advanced Analytics

### Step 1: Install Analytics Engine

1. **Copy analytics module:**
   ```bash
   cp phase4_fixes/reports/analytics.py reports/
   mkdir -p templates/reports
   cp phase4_fixes/reports/templates/reports/analytics_dashboard.html templates/reports/
   ```

2. **Install openpyxl for Excel export:**
   ```bash
   pip install openpyxl --break-system-packages
   ```

3. **Add analytics views:**
   ```python
   # reports/views.py
   
   from reports.analytics import AnalyticsEngine, ReportExporter
   
   @login_required
   @supervisor_required
   def analytics_dashboard(request):
       engine = AnalyticsEngine()
       
       campaign_id = request.GET.get('campaign')
       days = int(request.GET.get('days', 30))
       
       context = {
           'trends': engine.get_call_trends(campaign_id, days),
           'hourly': engine.get_hourly_performance(campaign_id, days),
           'leaderboard': engine.get_agent_leaderboard(campaign_id, days)[:10],
           'campaigns': Campaign.objects.filter(status='active'),
           'days': days,
           'selected_campaign_id': int(campaign_id) if campaign_id else None,
       }
       
       if campaign_id:
           context['roi'] = engine.get_campaign_roi(int(campaign_id), days)
       
       return render(request, 'reports/analytics_dashboard.html', context)
   
   
   @login_required
   @supervisor_required
   def export_report(request):
       engine = AnalyticsEngine()
       exporter = ReportExporter()
       
       report_type = request.GET.get('type', 'trends')
       format = request.GET.get('format', 'xlsx')
       campaign_id = request.GET.get('campaign')
       days = int(request.GET.get('days', 30))
       
       # Get data
       if report_type == 'trends':
           data = engine.get_call_trends(campaign_id, days)
       elif report_type == 'leaderboard':
           data = engine.get_agent_leaderboard(campaign_id, days)
       elif report_type == 'roi' and campaign_id:
           data = engine.get_campaign_roi(int(campaign_id), days)
       else:
           return HttpResponse('Invalid report type', status=400)
       
       # Export
       filename = f"{report_type}_{timezone.now().strftime('%Y%m%d')}"
       
       if format == 'xlsx':
           buffer = exporter.export_to_excel(data, report_type)
           return exporter.get_http_response(
               buffer, f"{filename}.xlsx",
               'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
           )
       
       return HttpResponse('Invalid format', status=400)
   ```

4. **Add URL patterns:**
   ```python
   # reports/urls.py
   
   urlpatterns = [
       # ... existing patterns ...
       path('analytics/', views.analytics_dashboard, name='analytics_dashboard'),
       path('analytics/export/', views.export_report, name='export_report'),
       path('api/leaderboard/', views.leaderboard_api, name='leaderboard_api'),
   ]
   ```

5. **Add ROI configuration to Campaign:**
   ```python
   # campaigns/models.py
   
   class Campaign(models.Model):
       # ... existing fields ...
       
       # ROI tracking
       cost_per_minute = models.DecimalField(
           max_digits=6, decimal_places=4, default=0.03
       )
       revenue_per_sale = models.DecimalField(
           max_digits=10, decimal_places=2, default=100
       )
       agent_hourly_cost = models.DecimalField(
           max_digits=6, decimal_places=2, default=15
       )
   ```

---

## Testing Phase 4 Features

### 4.1 Predictive Dialer
1. Set campaign to `dial_mode='predictive'`
2. Start Celery worker and beat
3. Add agents to campaign
4. Monitor dial ratio in logs
5. Check abandon rate stays below target

### 4.2 Call Scoring
1. Make test calls
2. Verify quality_score is populated after call ends
3. Check supervisor monitoring UI
4. Test listen/whisper/barge modes

### 4.3 Analytics
1. Access analytics dashboard
2. Filter by campaign and date range
3. Verify charts display correctly
4. Test Excel export
5. Check ROI calculations

---

## Performance Considerations

1. **Predictive Dialer:** Runs every second - ensure Celery worker can handle load
2. **Analytics:** Complex queries - consider adding database indexes
3. **Monitoring:** Uses WebSocket - ensure channels is properly configured

---

## Summary

Phase 4 adds enterprise-grade features:

- **Predictive Dialing:** Automatic dial ratio optimization to maximize agent utilization
- **AMD:** Answering machine detection to save agent time
- **Call Scoring:** Automated quality assessment for every call
- **Supervisor Tools:** Listen, whisper, and barge capabilities
- **Analytics:** Deep insights with trends, ROI, and exportable reports

Total new files: 6
Required migrations: campaigns, calls
