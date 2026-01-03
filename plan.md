# Autodialer Modernization Plan

This plan ties legacy Newfies autodialing patterns to the current Asterisk/ARI stack in this repo. Each section lists what to keep, what to change, and the concrete tasks/files to touch.

## 0. References
- Legacy (Newfies): `newfies/dialer_cdr/tasks.py` (originate + retries), `lua/newfies.lua` + `lua/libs/fsm_callflow.lua` (IVR/callflow), `newfies/dialer_gateway/models.py` (gateways), `install/conf/settings_local.py` (ESL vars).
- Current: `campaigns/management/commands/run_dialer.py`, `campaigns/tasks.py`, `telephony/services.py`, `telephony/models.py` (AsteriskServer/Carrier/Phone), `calls/models.py` (CallLog), `agents` app (AgentStatus/AgentDialerSession), dialplan `asterisk_campaign_dialplan.conf`.

## 1. Call Request Model & Metadata
- Goal: Centralize per-call metadata (campaign, lead, queue_id, agent_id, carrier_id, caller ID, timeout, account/prefix) like legacy `Callrequest`.
- Tasks:
  - Add a CallRequest-like model or extend `OutboundQueue` with immutable call_vars/json storing all vars used for originate.
  - Add helper `build_call_variables(campaign, queue_item, agent=None, carrier=None)` in `telephony/services.py` (or a new `telephony/callvars.py`) and use everywhere.
  - Track which carrier/trunk was used for each call; persist to `CallLog` and queue item.

## 2. Origination Flow (Two-Leg Bridge)
- Goal: Mirror legacy originate robustness (timeouts, DTMF, retries) on ARI.
- Tasks:
  - Wrap originate calls in a single service (customer leg via Local/ context, agent leg via PJSIP) with per-leg timeouts and preanswer DTMF support (legacy had queued digits).
  - Ensure dial prefix enforcement: server-side prepend `campaign.dial_prefix` before any originate.
  - Persist bridge/channel IDs on `AgentDialerSession` and queue item for tear-down.
  - Harden failure handling: on any leg failure, hang up other leg, free agent, increment attempts.

## 3. Pacing, Hopper, and Retries
- Goal: Borrow legacy retry/completion logic (`check_retrycall_completion`) and add pacing safeguards.
- Tasks:
  - Add per-campaign retry policy (max attempts, retry delay, retryable dispositions). Use in `process_outbound_queue_task` and recycling logic.
  - Respect campaign operating hours (`CampaignHours`) and pause dialing outside window.
  - Add backpressure: if ARI/AMI or DB errors occur, temporarily pause dialing loop and resume with jitter.
  - Tune hopper: use `campaign.hopper_size`; add DB fallback if Redis unavailable; ensure `fill_hopper` skips numbers already locked/dialing.

## 4. Carrier/Trunk Selection (Gateway Parity)
- Goal: Replace FS `Gateway` string with structured carrier selection.
- Tasks:
  - Implement weighted round-robin over `CampaignCarrier` with optional health checks; return chosen `Carrier` and dial string.
  - Allow per-carrier overrides: caller ID, timeout, tech (PJSIP/SIP/DAHDI), dial prefix, and custom channel vars.
  - Pass chosen carrier into originate (Local/ context that picks trunk) and store in `CallLog`/queue item.

## 5. ARI Stasis App & Event Handling
- Goal: Port Lua callflow/IVR behaviors to ARI.
- Tasks:
  - Build/extend Stasis app `autodialer`: tag legs (CALL_TYPE), detect answer, optional AMD, play prompts, collect DTMF, bridge agent↔customer, start/stop recording.
  - Implement ARI websocket consumer (can live in `telephony/services.py` or a dedicated worker) that handles ChannelStateChange/Destroyed and updates `OutboundQueue`, `AgentStatus`, `CallLog`, retries. This replaces legacy `process_callevent`.
  - Expose webhooks or a message bus path for IVR results (digits, AMD outcome, recordings) back to Django.

## 6. Dispositions, CDR, and Reporting
- Goal: Normalize Asterisk causes to dispositions and drive retries/metrics.
- Tasks:
  - Map hangup causes to disposition codes; store on `OutboundQueue` and `CallLog`.
  - Capture carrier used, call vars, and recording link in `CallLog`.
  - Add reporting queries (answer rate, drop rate, ACD) per campaign/carrier/agent.

## 7. Agent State Machine
- Goal: Keep agent workflow consistent during autodial.
- Tasks:
  - Ensure `AgentStatus` transitions (available → busy → wrapup → available) are driven by ARI events and timeouts (wrapup timeout per campaign).
  - On dropped/missed connects (customer answered but no agent), mark queue item dropped and adjust pacing.

## 8. Dialplan Alignment
- Goal: Ensure dialplan supports the originate patterns.
- Tasks:
  - Update `asterisk_campaign_dialplan.conf` contexts (`from-campaign`, agent contexts) to set channel vars (CAMPAIGN_ID, QUEUE_ID, CALL_TYPE, CARRIER_ID) before Stasis.
  - Add contexts for carrier selection (per-carrier prefixes/tech) and MoH/recording options.

## 9. Testing & Ops
- Goal: De-risk changes.
- Tasks:
  - Unit tests: call variable builder, carrier selection, pacing math, retry logic.
  - Integration tests: mock ARI (http + websocket) to simulate answer/busy/no-answer and assert queue/agent/CDR updates.
  - Smoke script to seed demo campaign/leads (`campaigns/management/commands/seed_demo_leads.py`) and run a short dial loop.
  - Health checks: ARI connectivity (`AsteriskService.test_connection`), Redis availability, dialer loop watchdog.

## 10. Execution Order
1) Add call variable helper + carrier selection helper; wire into `run_dialer.py` and `campaigns/tasks.py`.
2) Implement retry policy fields on Campaign + wiring in queue recycling.
3) Build ARI event consumer and wire status/CDR updates.
4) Extend Stasis app (AMD/DTMF/recording) and dialplan contexts; test end-to-end with a demo campaign.
5) Add reporting/disposition mapping and agent state tightening.
6) Add tests + health checks, then enable in production dialer loop.
