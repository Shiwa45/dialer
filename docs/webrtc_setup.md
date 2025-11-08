# Asterisk WebRTC (WSS) Setup

To use the in‑browser phone (SIP.js) on the Agent dashboard, enable WebSocket (WSS) and TLS in Asterisk.

1) HTTP/HTTPS for ARI + WebSocket
- /etc/asterisk/http.conf
```
enabled=yes
bindaddr=0.0.0.0
bindport=8088

; TLS/WSS for WebRTC
; Make sure these files exist (use a proper certificate in production)
tlsenable=yes
tlsbindaddr=0.0.0.0:8089
;tlscertfile=/etc/asterisk/keys/asterisk.pem
;tlsprivatekey=/etc/asterisk/keys/asterisk.key
;tlscafile=/etc/ssl/certs/ca-certificates.crt
```

2) PJSIP transports (add to /etc/asterisk/pjsip.conf)
```
[transport-wss]
type=transport
protocol=wss
bind=0.0.0.0:8089
```

3) Endpoint for WebRTC phones (chan PJSIP)
- Ensure your realtime endpoints include WebRTC‑friendly options:
  - dtls_auto_generate_cert=yes (or proper cert), rewrite_contact=yes, force_rport=yes, direct_media=no.
- Your Phone model sync already sets these defaults.

4) Browser side
- The Agent dashboard attempts to register SIP.js when `webrtc_config.success` is true.
- You may need to set the phone’s `webrtc_enabled=True` and optionally `ice_host` for TURN.
- Update `WebRTCService.get_webrtc_config()` as needed (it already emits wss://<server>:8089/ws and STUN/optional TURN entries).

5) Test
- Open the agent dashboard and check the “phone status” badge changes to Registered.
- If it fails:
  - Check the browser console for TLS/WS errors.
  - Confirm 8089 is open and certificates are valid (or temporarily allow self‑signed for test).
  - Use `pjsip set logger on` to see SIP over WSS traffic in the Asterisk console.

Security note
- Always use proper TLS certificates and limit origins with `allowed_origins` in `ari.conf` and CORS/proxy for production.

