# Debug Logging Added to ARI Worker

## Changes Made

Added comprehensive logging to see exactly what's happening with the WebSocket connection:

1. **Log every received message** - See raw ARI events as they arrive
2. **Log event type being handled** - See which handler is being called
3. **Log unhandled events** - See if events are being received but not processed

## Restart and Check Logs

```bash
# Press Ctrl+C
sudo ./start_autodialer.sh
```

Then immediately watch the ARI worker log:
```bash
tail -f logs/ARI_Worker.log
```

## What to Look For

### If WebSocket is Working
You should see:
```
INFO Connected to Asterisk ARI
INFO Received ARI event: {"type":"StasisStart","channel":{"id":"PJSIP/openvox-0000006b"...
INFO Handling event: StasisStart
INFO StasisStart: PJSIP/openvox-0000006b
INFO Channel PJSIP/openvox-0000006b variables: {'CALL_TYPE': 'autodial', ...}
```

### If WebSocket is NOT Receiving Events
You'll only see:
```
INFO Connected to Asterisk ARI
(nothing else)
```

This will tell us if:
- Events are being received but not processed (we'll see "Received ARI event")
- Events aren't being received at all (we'll see nothing)
- Events are being received but handler is failing (we'll see errors)

## Next Steps Based on Results

### Case 1: Events ARE Being Received
- Check the event handling logic
- Verify channel variable retrieval
- Check agent availability

### Case 2: Events are NOT Being Received
- WebSocket connection issue
- Asterisk ARI configuration problem
- Need to check Asterisk ARI settings

Let's see what the logs show!
