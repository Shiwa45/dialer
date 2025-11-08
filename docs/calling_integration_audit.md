# Calling Integration Audit and Fix Plan

This document lists the current state of the campaigns ↔ telephony integration, issues found, fixes applied, and a step‑by‑step plan to complete the calling workflow (originate, hangup, transfer, logging) using Asterisk ARI.

## Summary (current state)
- Asterisk realtime (PJSIP) and ODBC are set up; endpoints load from DB and can register.
- Django switched to PostgreSQL and migrations are applied.
- Extensions (Phones) auto‑sync to ps_endpoints/ps_auths/ps_aors.
- Server “Test Connection” now performs a real ARI check.

## Issues Found and Fixes

1) Server test always “connected” (stub)
- Problem: `telephony/views.py:test_asterisk_connection` set status unconditionally.
- Fix: It now uses `AsteriskService.test_connection()` and sets status based on ARI response.

2) ARI URL mistake
- Problem: Called `/ari/applications` despite `ari_base_url` already ending with `/ari`.
- Fix: `telephony/services.py:test_connection()` now calls `.../applications`.

3) Asterisk 20 realtime schema mismatch (mailboxes)
- Problem: Asterisk 20 expects `ps_endpoints.mailboxes` (ODBC error 42703).
- Fix: Added `mailboxes` to `PsEndpoint` and migrated (telephony.0006).

4) Asterisk PJSIP config parse error in WSL
- Problem: `/etc/asterisk/pjsip.conf` had invalid lines.
- Action: Simplify to a minimal valid transport + include. See docs/generated and docs/wsl_asterisk_setup.md.

5) PJSIP sorcery mapping missing
- Problem: `res_pjsip` wouldn’t read realtime tables without `sorcery.conf`.
- Action: Added template (docs/generated/sorcery.conf). Deploy to `/etc/asterisk/sorcery.conf`.

6) Originate used SIP/ and wrong CallLog fields
- Problem: Provisioned PJSIP endpoints, but originate used `SIP/`. Also used non‑existent `channel_id` and `call_direction` fields.
- Fix: `telephony/services.py:originate_call()` now:
  - Uses `PJSIP/{extension}` endpoint.
  - Creates `CallLog` with `call_type='outbound'`, `channel=<channel_id>`, `start_time=now()`.

7) API originate was a stub
- Problem: `telephony/views.py:originate_call` returned a fake success.
- Fix: It now delegates to `agents.AgentTelephonyService.make_call()` and returns real status.

8) Hangup/transfer stubs (TODO)
- Problem: Views and AgentTelephonyService indicate TODOs for ARI‑backed hangup/transfer.
- Plan: Implement via ARI:
  - Hangup: `DELETE /ari/channels/{channel_id}` (we store ARI id in `CallLog.channel`).
  - Blind transfer: `POST /ari/channels/{channel_id}/redirect` with endpoint `PJSIP/<ext or trunk>`.

9) Template uses `call_direction` but model has `call_type`
- Problem: Some templates reference `call.call_direction`.
- Plan: Replace with `call.call_type` and display text accordingly, or add a `@property` on `CallLog` for backward compatibility.

10) Campaign dialer queue (progressive/predictive) not implemented
- Problem: `AgentTelephonyService.queue_call_for_dialing()` is a stub.
- Plan: Implement a lightweight queue table and a Celery task to originate using dial ratio from Campaign.

11) Recording and storage
- Optional: configure Asterisk `mixmonitor` or ARI bridges to record and update `Recording` model.

## Implementation Plan (step‑by‑step)

A) Complete ARI operations
- [x] Server ARI connectivity test (done)
- [x] Originate PJSIP and correct CallLog fields (done)
- [ ] Hangup endpoint
  - telephony/services.py: implement `hangup_call(channel_id)` via `DELETE /ari/channels/{id}` and update `CallLog.end_time`, `call_status`.
  - telephony/views.py: route POST to services and return status.
- [ ] Transfer endpoint
  - telephony/services.py: implement blind transfer using `POST /ari/channels/{id}/redirect` with `endpoint`.
  - Optional attended transfer via ARI bridges (out of scope initially).

B) Fix template/model mismatch
- [ ] Update templates to use `call.call_type` or add a `CallLog.call_direction` property returning `Inbound/Outbound` from `call_type`.

C) Agent UI wiring
- [ ] Agents views (agents/views.py) `make_call`, `hangup_call`, `transfer_call` to call `AgentTelephonyService`, which calls `AsteriskService`.
- [ ] Add success/error toasts and disable buttons while requests in flight.

D) Campaign queue (optional phase 2)
- [ ] Introduce `OutboundQueue` model with fields: campaign, phone_number, lead, status, attempts.
- [ ] Celery task that pulls from queue, calls `AsteriskService.originate_call`, assigns to free agents (based on AgentStatus), respects dial ratio.

E) Testing checklist
- Originate: POST `/telephony/calls/originate/` JSON `{ "phone_number": "<dest>", "campaign_id": <id> }` returns success and creates `CallLog` with channel id.
- Hangup: POST `/telephony/calls/hangup/` JSON `{ "channel_id": "<from CallLog.channel>" }` tears down channel and updates `CallLog`.
- Transfer: POST `/telephony/calls/transfer/` JSON `{ "channel_id": "..", "destination": "PJSIP/1002" }` moves the call.
- Dashboard / Reports reflect new `CallLog` entries.

## File References
- telephony/services.py:18,114
- telephony/views.py:1446
- agents/telephony_service.py: make_call() integration path
- calls/models.py (fields used by call logging)
- templates referencing call_direction: search `call_direction` in repo

## Generated Configs (for WSL Asterisk)
- docs/generated/extconfig.conf
- docs/generated/res_odbc.conf
- docs/generated/pjsip_realtime.conf
- docs/generated/sorcery.conf

## Notes
- Keep using PJSIP throughout (endpoints, dialplan).
- Use the WSL IP (172.26.7.107) from Windows softphones if UDP/localhost is unreliable; or enable TCP transport.

Once the remaining TODOs (hangup/transfer + template fix) are implemented, agents can place, end, and transfer calls via the app, and `CallLog` will be consistent with reporting.

