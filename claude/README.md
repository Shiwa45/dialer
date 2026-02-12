# WebRTC Rebuild v2 — Implementation Guide

## Files Provided

| File | Copy To | Description |
|------|---------|-------------|
| `agents_views_simple.py` | `agents/views_simple.py` | Replace entire file. Routes WebRTC→webrtc_dashboard, softphone→simple_dashboard |
| `webrtc_dashboard.html` | `templates/agents/webrtc_dashboard.html` | Replace entire file. Dedicated WebRTC page with simple_dashboard UI + full JsSIP |
| `users_views.py` | `users/views.py` | Replace `CustomLoginView` + `CustomLogoutView`. Keep other views unchanged |

## What's Different Now

### Previous Problems
1. `agent_dashboard.js` (current) is the Phase 1 IIFE version — has NO WebRTC, NO RetroPhoneController
2. `agent_dashboard.js.backup` has RetroPhoneController but is never loaded
3. Old `webrtc_dashboard.html` used separate `webrtc_phone.js` + different UI
4. 404 errors from missing/unreferenced JS files
5. "Not registered" shown because WebRTC never initialized
6. No microphone permission asked because JsSIP never loaded properly

### Solution
- **Dedicated `webrtc_dashboard.html`** with ALL JavaScript inline — no external JS dependencies except JsSIP CDN
- Clones the exact `simple_dashboard.html` UI (same CSS, same layout, same RetroPhone)
- Full JsSIP integration: register, call, answer, hangup, mute, hold, transfer, DTMF
- Auto-answer toggle button
- Django WebSocket integration for backend events (call_incoming, call_ended, etc.)
- Disposition modal
- Keyboard support (type digits, Enter to call, Escape to hangup)

## Flow

```
Agent Login
├── WebRTC phone → Login allowed → webrtc_dashboard.html
│   └── JsSIP auto-registers → mic permission requested → "READY"
├── Softphone (registered) → Login allowed → simple_dashboard.html
└── Softphone (not registered) → Login BLOCKED

webrtc_dashboard.html
├── JsSIP connects to wss://asterisk:8089/ws
├── Registers sip:extension@domain
├── Incoming calls: auto-answer or manual answer
├── Outgoing calls: dial via keypad → SIP INVITE
├── Mute / Hold / Transfer / DTMF
├── Django WebSocket: receives call_incoming, call_ended events
└── Disposition modal after call ends
```

## Asterisk Requirements

Your Asterisk MUST have:

1. **WSS transport** (port 8089 with TLS):
   ```ini
   ; http.conf
   [general]
   enabled=yes
   tlsenable=yes
   tlsbindaddr=0.0.0.0:8089
   tlscertfile=/etc/asterisk/keys/cert.pem
   tlsprivatekey=/etc/asterisk/keys/key.pem
   ```

2. **PJSIP WebRTC endpoint** for the extension:
   ```ini
   [1001]
   type=wizard
   transport=transport-wss
   webrtc=yes
   dtls_auto_generate_cert=yes
   allow=!all,ulaw,alaw,opus
   endpoint/context=agents
   ```

3. If using self-signed certs, the agent must visit `https://asterisk-ip:8089/` in their browser first and accept the certificate.

## Verification

1. Login as WebRTC agent → should see webrtc_dashboard.html
2. Green dot + "Registered (1001)" should appear
3. Browser should ask for microphone permission
4. Type a number → press CALL → SIP INVITE sent
5. Incoming call → phone shows "INCOMING" + auto-answers if toggle is on
6. Mute/Hold/Transfer buttons work during call
7. After call ends → disposition modal appears
8. Login as non-WebRTC agent without softphone → should be blocked
