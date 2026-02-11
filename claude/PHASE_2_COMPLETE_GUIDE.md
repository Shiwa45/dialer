# Phase 2 Complete Implementation Guide - Lead Recycling System Fix

## Overview

Phase 2 is now **COMPLETE** with all components to fix the lead recycling system and ensure no leads are "lost" without proper status tracking.

### ✅ Phase 2.1: Lead Status Audit & Data Cleanup
- Enhanced Lead model with comprehensive tracking fields
- Lead Status Management Service
- Automatic status synchronization from CallLog
- Management command to find and fix problematic leads
- Database indexes for performance

### ✅ Phase 2.2: Hopper Management Enhancement
- Real-time status updates on dial attempts
- Proper tracking of dial results
- Failed call classification (network, busy, no answer, congestion)
- Retry delay and eligibility logic

### ✅ Phase 2.3: Lead Recycling Page Enhancement
- Complete status breakdown (including NULL/empty status)
- "Fix Problematic Leads" button
- Multi-select recycling with target status
- Reset dial count option
- Recycling activity logging

### ✅ Phase 2.4: Automated Lead Status Management
- CallLog → Lead status sync service
- Background reconciliation task
- Status transition validation
- Comprehensive audit trail

---

## File Structure

```
Phase 2 Implementation Files:
├── leads/
│   ├── migrations/
│   │   └── 0007_lead_enhanced_tracking.py
│   ├── management/commands/
│   │   └── fix_lead_status.py
│   ├── lead_status_service.py
│   └── views_recycling.py
├── campaigns/
│   └── tasks.py (updated with reconciliation tasks)
└── templates/
    └── leads/
        ├── lead_recycling.html
        └── lead_status_report.html
```

---

## New Database Fields

### Lead Model Enhancements

```python
# New tracking fields
last_dial_attempt = DateTimeField(null=True, blank=True)
dial_result = CharField(max_length=50, blank=True)
dial_attempts = PositiveIntegerField(default=0)
answered_count = PositiveIntegerField(default=0)
last_status_change = DateTimeField(null=True, blank=True)

# Enhanced status choices
status = CharField(
    max_length=50,
    choices=[
        ('new', 'New'),
        ('contacted', 'Contacted'),
        ('callback', 'Callback Scheduled'),
        ('sale', 'Sale'),
        ('no_answer', 'No Answer'),
        ('busy', 'Busy'),
        ('failed', 'Failed'),           # NEW
        ('dropped', 'Dropped'),         # NEW
        ('congestion', 'Congestion'),   # NEW
        ('not_interested', 'Not Interested'),
        ('dnc', 'Do Not Call'),
        ('invalid', 'Invalid'),
    ]
)
```

### New Indexes
```python
# Performance indexes
Index(fields=['status', 'dial_attempts', 'last_dial_attempt'])
Index(fields=['lead_list', 'status'])
```

---

## Installation Steps

### Step 1: Run Migration

```bash
cd /path/to/autodialer
python manage.py migrate leads 0007_lead_enhanced_tracking
```

### Step 2: Install Services

```bash
# Copy lead status service
cp leads/lead_status_service.py /path/to/your/project/leads/

# Copy recycling views
cp leads/views_recycling.py /path/to/your/project/leads/

# Copy management command
mkdir -p /path/to/your/project/leads/management/commands/
cp leads/management/commands/fix_lead_status.py \
   /path/to/your/project/leads/management/commands/
```

### Step 3: Update URL Configuration

Add to `leads/urls.py`:

```python
from leads import views_recycling

urlpatterns = [
    # ... existing patterns ...
    
    # Phase 2.3: Enhanced recycling
    path('list/<int:list_id>/recycle/', 
         views_recycling.lead_recycling_page, 
         name='lead_recycling'),
    
    path('list/<int:list_id>/recycle/action/', 
         views_recycling.recycle_leads_action, 
         name='recycle_leads_action'),
    
    path('list/<int:list_id>/fix-problematic/', 
         views_recycling.fix_problematic_leads_action, 
         name='fix_problematic_leads'),
    
    path('list/<int:list_id>/status-report/', 
         views_recycling.lead_status_report, 
         name='lead_status_report'),
]
```

### Step 4: Update ARI Worker / Call Handling

Integrate lead status updates in call end handler:

```python
# In telephony/management/commands/ari_worker.py or similar

from leads.lead_status_service import get_lead_status_service

def _handle_call_end(self, call_log):
    """Handle call end - update lead status"""
    
    if call_log.lead_id:
        service = get_lead_status_service()
        
        # Update lead based on call result
        service.update_lead_from_call_result(
            lead_id=call_log.lead_id,
            call_status=call_log.call_status,
            disposition=call_log.disposition_status,
            increment_dial=True
        )
```

### Step 5: Add Background Reconciliation Task

Update `campaigns/tasks.py`:

```python
@shared_task
def reconcile_lead_status():
    """
    Daily reconciliation of lead status
    
    Schedule: Daily at 2 AM
    """
    from leads.lead_status_service import get_lead_status_service
    
    service = get_lead_status_service()
    
    # Find and fix problematic leads
    issues = service.find_leads_with_missing_status()
    
    if issues.get('total_issues', 0) > 0:
        logger.warning(f"Found {issues['total_issues']} leads with status issues")
        
        # Auto-fix if under threshold
        if issues['total_issues'] < 1000:
            result = service.fix_leads_with_missing_status(dry_run=False)
            logger.info(f"Auto-fixed {result.get('leads_fixed', 0)} leads")
    
    return issues
```

Add to Celery Beat schedule:

```python
'reconcile-lead-status': {
    'task': 'campaigns.tasks.reconcile_lead_status',
    'schedule': crontab(hour=2, minute=0),  # Daily at 2 AM
},
```

---

## Usage Guide

### 1. Run Initial Status Fix

First, analyze the current state:

```bash
# Report only (see what issues exist)
python manage.py fix_lead_status --report-only

# Dry run (see what would be fixed)
python manage.py fix_lead_status --dry-run

# Fix all issues
python manage.py fix_lead_status

# Fix specific campaign
python manage.py fix_lead_status --campaign=123
```

**Example Output:**
```
======================================================================
Lead Status Fix - Phase 2.1
======================================================================
Scope: All campaigns

Step 1: Analyzing leads...
  Leads with dial attempts but status "new": 458
  Leads with calls but missing dial tracking: 127
  Total issues found: 585

Step 2: Fixing issues...
  Leads checked: 585
  Leads fixed: 585
  Errors: 0

  Status distribution after fix:
    no_answer: 243
    busy: 128
    contacted: 97
    failed: 86
    dropped: 31

✅ Successfully fixed 585 leads!
```

### 2. Use Enhanced Recycling Interface

Navigate to: **Leads → Lead Lists → [Your List] → Recycle Leads**

**Features:**
1. **Complete Status Breakdown** - Shows all statuses including NULL
2. **Problematic Leads Alert** - Shows leads with tracking issues
3. **Multi-Select Recycling** - Select multiple statuses to recycle
4. **Fix Problematic Button** - One-click fix for leads with issues
5. **Status Report** - Detailed analytics and recommendations

**Recycling Process:**
1. View complete status breakdown
2. Check for problematic leads (red alert if > 0)
3. Click "Fix Problematic Leads" if needed
4. Select statuses to recycle (e.g., no_answer, busy, failed)
5. Choose target status (usually "new")
6. Optionally reset dial count
7. Click "Recycle Selected Leads"
8. Verify leads are now available in hopper

### 3. Monitor Status Distribution

Get status report:

```python
# Django shell
from leads.models import Lead, LeadList

lead_list = LeadList.objects.get(name="DELHI 80K")

# Get comprehensive stats
stats = lead_list.get_progress_stats()

print(f"Total leads: {stats['total_leads']}")
print(f"New leads: {stats['new_leads']}")
print(f"Contacted: {stats['contacted_leads']}")
print(f"Remaining: {stats['remaining_leads']}")
print("\nStatus breakdown:")
for status, count in stats['status_breakdown'].items():
    print(f"  {status}: {count}")
```

### 4. Check Recyclable Leads

```python
from leads.lead_status_service import get_lead_status_service

service = get_lead_status_service()

# Get recyclable lead IDs for campaign
recyclable_ids = service.get_recyclable_leads(
    campaign_id=123,
    max_attempts=5,
    hours_since_last=4
)

print(f"Found {len(recyclable_ids)} recyclable leads")
```

---

## Key Improvements

### Before Phase 2 ❌
- Leads dialed but status still "new"
- CallLog created but Lead not updated
- No tracking of dial attempts vs answered calls
- Missing leads not visible in recycling
- "No eligible leads" despite large lead count

### After Phase 2 ✅
- Every dial attempt tracked
- Lead status updated automatically
- Comprehensive dial attempt tracking
- All statuses visible (including NULL)
- Automatic detection and fixing of issues
- Background reconciliation
- Detailed status reports

---

## API Methods

### LeadStatusService

```python
from leads.lead_status_service import get_lead_status_service

service = get_lead_status_service()

# Update lead from call result
service.update_lead_from_call_result(
    lead_id=123,
    call_status='no_answer',
    disposition=None,
    increment_dial=True
)

# Find problematic leads
issues = service.find_leads_with_missing_status(campaign_id=456)

# Fix problematic leads
result = service.fix_leads_with_missing_status(
    campaign_id=456,
    dry_run=False
)

# Get recyclable leads
recyclable = service.get_recyclable_leads(
    campaign_id=456,
    max_attempts=5,
    hours_since_last=4
)
```

---

## Troubleshooting

### Issue: Recycling page still shows few statuses

**Check 1**: Run status fix command
```bash
python manage.py fix_lead_status --campaign=YOUR_CAMPAIGN_ID
```

**Check 2**: Verify migration applied
```bash
python manage.py showmigrations leads
# Should show [X] 0007_lead_enhanced_tracking
```

**Check 3**: Check database directly
```python
from leads.models import Lead
from django.db.models import Count

# Get all statuses
Lead.objects.values('status').annotate(count=Count('id'))
```

### Issue: "No eligible leads" in hopper

**Check 1**: Check hopper status
```python
from campaigns.models import DialerHopper

# Check hopper entries
DialerHopper.objects.filter(campaign_id=YOUR_ID).count()

# Check by status
DialerHopper.objects.filter(
    campaign_id=YOUR_ID
).values('status').annotate(count=Count('id'))
```

**Check 2**: Check lead eligibility
```python
from leads.models import Lead, LeadList

lead_list = LeadList.objects.get(assigned_campaign_id=YOUR_ID)

# Leads that should be dialable
dialable = Lead.objects.filter(
    lead_list=lead_list,
    status__in=['new', 'no_answer', 'busy', 'callback'],
    dial_attempts__lt=5
).count()

print(f"Dialable leads: {dialable}")
```

**Fix**: Recycle leads
```bash
python manage.py fix_lead_status --campaign=YOUR_ID
# Then use recycling interface to reset leads
```

### Issue: Leads stuck in "dialing" status

**Fix**: Clean up stuck hopper entries
```bash
python manage.py shell
```

```python
from campaigns.models import DialerHopper
from datetime import timedelta
from django.utils import timezone

# Find stuck entries
cutoff = timezone.now() - timedelta(minutes=10)
stuck = DialerHopper.objects.filter(
    status='locked',
    locked_at__lt=cutoff
)

print(f"Found {stuck.count()} stuck entries")

# Reset them
stuck.update(status='new', locked_at=None, locked_by=None)
```

---

## Monitoring & Maintenance

### Daily Monitoring

Check these metrics daily:

```python
from leads.lead_status_service import get_lead_status_service

service = get_lead_status_service()

# Check for issues
for campaign_id in [1, 2, 3]:  # Your campaign IDs
    issues = service.find_leads_with_missing_status(campaign_id)
    if issues.get('total_issues', 0) > 0:
        print(f"Campaign {campaign_id}: {issues['total_issues']} issues found")
```

### Weekly Recycling

Run recycling weekly:

```bash
# Generate report
python manage.py fix_lead_status --report-only > weekly_report.txt

# Fix issues
python manage.py fix_lead_status

# Email report to admins
mail -s "Weekly Lead Status Report" admin@example.com < weekly_report.txt
```

### Monthly Audit

Full audit monthly:

```python
from leads.models import Lead, LeadList
from django.db.models import Count, Q

# Leads with high attempts but no answer
high_attempts = Lead.objects.filter(
    dial_attempts__gte=10,
    answered_count=0
).count()

print(f"Leads with 10+ attempts, no answer: {high_attempts}")

# Consider marking as invalid or DNC
if high_attempts > 100:
    print("⚠️  Consider reviewing leads with excessive attempts")
```

---

## Performance Optimization

### Database Indexes

The migration adds these indexes automatically:
```sql
CREATE INDEX leads_lead_status_dial_idx 
ON leads_lead(status, dial_attempts, last_dial_attempt);

CREATE INDEX leads_lead_list_status_idx 
ON leads_lead(lead_list_id, status);
```

### Query Optimization

Use select_related and prefetch_related:

```python
# Good - Single query
leads = Lead.objects.filter(
    lead_list_id=123
).select_related('lead_list', 'assigned_user')

# Bad - N+1 queries
leads = Lead.objects.filter(lead_list_id=123)
for lead in leads:
    print(lead.lead_list.name)  # Hits DB each time
```

---

## Success Metrics

After Phase 2 deployment, you should see:

1. **Zero "lost" leads** - All leads have proper status
2. **Accurate recycling counts** - Status breakdown shows all leads
3. **No "eligible leads not found"** - Hopper properly filled
4. **Improved answer rates** - Better lead targeting
5. **Reduced manual cleanup** - Automated reconciliation

---

## Next Steps

1. ✅ **Phase 2 Complete** - Lead recycling fixed
2. 🔄 **Phase 3** - Call Recording Filename Fix
3. 🔄 **Phase 4** - Timezone Configuration
4. 🔄 **Phase 5** - Main Dashboard WebSocket
5. 🔄 **Phase 6** - Agent Call History in Admin
6. 🔄 **Phase 7** - Sarvam AI Integration

---

**Phase 2 Implementation Complete!** ✅

All lead status tracking issues resolved and recycling system fully functional.
