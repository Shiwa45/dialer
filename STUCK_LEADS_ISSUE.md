# Summary of Issues and Solutions

## Current Status

### ✅ WORKING
1. **Hopper Fill Service** - Adding leads to Redis hopper
2. **Lead Retrieval** - Fixed `get_next_leads()` to fetch from database
3. **Call Origination** - Dialer successfully originates calls
4. **Softphone Registration Check** - Only counts registered agents

### ❌ PROBLEM: Calls Getting Stuck in Dialing Set

**Symptom**: 
- Dialer originates call successfully
- Lead gets added to Redis dialing set
- Call fails or completes
- Lead NEVER gets removed from dialing set
- Dialer thinks there's still an active call
- No more calls are placed

**Root Cause**:
The call cleanup isn't happening. Leads need to be removed from the dialing set when:
1. Call completes (answered and hung up)
2. Call fails (no answer, busy, error)
3. Call times out

**Current Flow**:
```
Dialer → Originate Call → Add to Redis dialing set → ???
                                                       ↓
                                              STUCK FOREVER
```

**Expected Flow**:
```
Dialer → Originate Call → Add to Redis dialing set
                                    ↓
                          Call Ends (any reason)
                                    ↓
                          Remove from dialing set
                                    ↓
                          Ready for next call
```

---

## Solutions Needed

### Option 1: Add Timeout Cleanup (Quick Fix)
Add a background task that removes leads from dialing set after 2-3 minutes

**Pros**: Simple, fixes stuck leads
**Cons**: Doesn't fix root cause

### Option 2: Fix ARI Event Handling (Proper Fix)
Ensure ARI event worker properly handles all call end events:
- `ChannelDestroyed`
- `ChannelHangupRequest`  
- `StasisEnd`

**Pros**: Fixes root cause
**Cons**: More complex

### Option 3: Add Cleanup in Predictive Dialer (Hybrid)
Before each dial cycle, check for leads in dialing set > 2 minutes old and remove them

**Pros**: Self-healing, simple
**Cons**: Adds overhead to dial cycle

---

## Immediate Workaround

Run this command periodically to clear stuck leads:
```bash
source env/bin/activate && python3 cleanup_stuck_leads.py
```

Or add to cron:
```bash
*/5 * * * * cd /home/shiwansh/dialer && source env/bin/activate && python3 cleanup_stuck_leads.py
```

---

## Next Steps

1. **Investigate why calls aren't triggering cleanup**
   - Check Asterisk dialplan
   - Check ARI event subscriptions
   - Check call flow

2. **Implement proper cleanup**
   - Add timeout tracking to Redis
   - Enhance ARI event worker
   - Add failsafe cleanup in dialer

3. **Test end-to-end**
   - Successful call → cleanup
   - Failed call → cleanup
   - Timeout → cleanup
