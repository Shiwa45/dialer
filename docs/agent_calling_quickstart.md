# Agent Calling Quickstart

This guide shows how to create an agent, log in, and place a call using your current telephony setup (Asterisk in WSL with PJSIP realtime).

## Prerequisites
- Asterisk in WSL is running and mapped to realtime (ps_* tables) with sorcery.
- Your extension (e.g., `1001`) exists in Django and appears in `pjsip show endpoints`.
- Your softphone can register to Asterisk (WSL IP) using the extension’s Secret.

## Create an Agent
- Create user
  - Go to `Users → Add User` (or `/admin`) and create a user with username/password.
  - Add the user to an `Agent` group (create if needed) so agent features are enabled.
- Assign an extension
  - `Telephony → Extensions` → open your extension (or create one).
  - Set the “User” to the new agent and Save.
  - Optional: set Secret to a known value (e.g., `1001`) and Save (re-syncs to Asterisk).
- Confirm registration (softphone)
  - Softphone settings: Domain/SIP Server: your WSL IP (e.g., `172.26.7.107`), Username: the extension (e.g., `1001`), Password: the extension Secret, Transport: UDP (or TCP if enabled).
  - In Asterisk CLI: `pjsip show contacts` should list the extension after registration.

## Log In and Set Agent Status
- Log in at `/users/login/` with the agent account.
- Visit `/agents/` (Agent Dashboard).
- Set status to `Available` using the dashboard controls (calls are only allowed when available).

## Place a Call
- Option A — Agent UI
  - On `/agents/`, use the call controls (or dial input) to place a call.
  - This posts to `POST /agents/call/make/` with fields:
    - `phone_number`: destination number (E.164 or your test extension)
    - `campaign_id` (optional)
- Option B — API (quick test)
  - `POST /telephony/calls/originate/`
  - JSON body: `{ "phone_number": "<destination>", "campaign_id": null }`
  - The backend uses `AgentTelephonyService` and `AsteriskService` to originate via `PJSIP/<your extension>`.

## What Happens Under the Hood
- `AgentTelephonyService.make_call` verifies:
  - Agent has an active Phone and an active Asterisk Server.
  - Agent is `available`.
  - Creates an outbound `CallLog` and calls `AsteriskService.originate_call`.
- `telephony/services.py:originate_call` (using ARI):
  - Uses `PJSIP/{extension}`
  - Creates `CallLog` with `call_type='outbound'`, `call_status='initiated'`, `start_time`, and `channel` (ARI id).

## Dialplan Echo Test (optional)
Add a quick test to `/etc/asterisk/extensions.conf`:
```
[agents]
exten => 7000,1,Answer()
 same => n,Echo()
 same => n,Hangup()
```
Reload: `asterisk -rx "dialplan reload"` and dial `7000` from your softphone.

## Troubleshooting
- Agent cannot dial
  - Ensure agent status is `available`.
  - Ensure an active Phone is assigned and an Asterisk Server exists in Telephony.
- REGISTER fails
  - Reset the Phone Secret in `Telephony → Extensions`, paste it into the softphone.
  - Use WSL IP (e.g., `172.26.7.107`) and correct transport.
  - In Asterisk CLI: `pjsip set logger on` to inspect REGISTER exchange.
- Originate API returns error
  - Confirm ARI connectivity (Asterisk Server → Test Connection).
  - `pjsip show endpoints` lists your extension; verify your dialplan context (`agents`).

## Optional Next Steps
- Add a small dial widget on the Agent dashboard that posts to `/agents/call/make/`.
- Implement ARI-backed hangup/transfer in `telephony/services.py` and wire the views so agents can end/transfer calls from the UI.
- Align templates using `call_direction` to use `call_type` (or add a compatibility property on `CallLog`).

