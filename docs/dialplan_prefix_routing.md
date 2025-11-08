# Dial Prefix Routing (Local/ ? Asterisk Dialplan)

This project now prefers a dialplan-centric approach for outbound routing. Campaigns can set a dial_prefix and all customer calls are originated into the Asterisk dialplan via a Local channel:

- Customer leg: Local/{dial_prefix}{number}@from-campaign
- Agent leg: still PJSIP/{agent_extension} (for MicroSIP/WebRTC)

The dialplan decides which trunk/gateway (e.g., Dinstar/OpenVox) to use per prefix — ideal for physical GSM gateways.

## 1) Asterisk Dialplan

Edit /etc/asterisk/extensions.conf in WSL and add a context like:

`
[from-campaign]
; 9-prefix ? Dinstar E1 or GSM gateway
exten => _9X.,1,NoOp(Outbound via Dinstar: )
 same => n,Set(STRIPPED=)
 same => n,Dial(PJSIP/dinstar/,60)
 same => n,Hangup()

; 91-prefix ? OpenVox GSM gateway
exten => _91X.,1,NoOp(Outbound via OpenVox: )
 same => n,Set(STRIPPED=)
 same => n,Dial(PJSIP/openvox/,60)
 same => n,Hangup()

; default fallback (no prefix)
exten => _X.,1,NoOp(Default trunk: )
 same => n,Dial(PJSIP/default/,60)
 same => n,Hangup()
`

Reload dialplan:

`
asterisk -rx "dialplan reload"
`

Ensure your PJSIP trunk names (dinstar, openvox, default) match your pjsip.conf endpoint names or realtime rows.

## 2) Campaign Setup

- Set Dial Prefix on the campaign:
  - 9 to use Dinstar
  - 91 to use OpenVox
- The app will originate the customer leg to Local/{prefix}{number}@from-campaign. The dialplan will strip the prefix and route to the gateway.

Manual dialing also honors dial_prefix and uses the rom-campaign context when present.

## 3) Verifying

- From Asterisk CLI:
  - pjsip set logger on
  - Place an outbound call from the app.
  - You should see Local/… call into rom-campaign and a subsequent Dial(PJSIP/…) to your gateway.

## 4) Notes

- If a campaign has no dial_prefix, it falls back to the legacy behavior.
- You can add as many prefixes as you need for multiple trunks/carriers.
- WebRTC and agent registration are unaffected by this change.

