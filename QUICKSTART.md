# Quick Start Guide - Predictive Autodialer

## What Was Built

✅ **ARI Event Worker** - Real-time call bridging and event handling  
✅ **Enhanced Predictive Dialer** - FCC-compliant with drop rate monitoring  
✅ **WebSocket Consumers** - Real-time agent interface updates  
✅ **Performance Tracking** - Agent session statistics  

## Quick Deployment

### 1. Run Deployment Script

```bash
cd /home/shiwansh/dialer
./deploy_autodialer.sh
```

This will:
- Activate virtual environment
- Create and apply database migrations
- Check Redis and Asterisk status

### 2. Start All Services

Open **5 separate terminals** and run:

**Terminal 1:**
```bash
source env/bin/activate
python3 manage.py runserver
```

**Terminal 2:**
```bash
source env/bin/activate
celery -A autodialer worker -l info
```

**Terminal 3:**
```bash
source env/bin/activate
python3 manage.py predictive_dialer --interval=3
```

**Terminal 4:**
```bash
source env/bin/activate
python3 manage.py ari_event_worker
```

**Terminal 5:**
```bash
source env/bin/activate
daphne -b 0.0.0.0 -p 8001 autodialer.asgi:application
```

## Quick Test

1. Open agent dashboard: `http://localhost:8000/agents/dashboard/`
2. Set status to "Ready"
3. Watch Terminal 3 for dialer activity
4. Watch Terminal 4 for ARI events
5. Calls should arrive automatically when leads are in hopper

## Key Files Created

- `campaigns/management/commands/ari_event_worker.py` - ARI event consumer
- `agents/consumers.py` - WebSocket consumers
- `deploy_autodialer.sh` - Deployment script

## Key Files Modified

- `campaigns/management/commands/predictive_dialer.py` - Enhanced dialer
- `agents/models.py` - Added performance tracking
- `agents/routing.py` - Updated WebSocket routes

## Next Steps

See `walkthrough.md` for:
- Detailed testing procedures
- Troubleshooting guide
- Remaining features to implement

See `implementation_plan.md` for:
- Complete architecture details
- Verification plan
- Success criteria
