Testing Steps (Current Build)

Prereqs
- Redis running on localhost:6379.
- Postgres up; migrations applied: `python manage.py migrate`.
- Services running: `./scripts/start_dialer_stack.sh` (Celery worker/beat, ARI worker) plus Django/Channels (Daphne/runserver).
- Agent assigned to campaign and has active phone; WebRTC enabled only if desired (loads JsSIP).

Smoke: Status & WebSocket
1) Open agent dashboard; ensure status pill matches DB.
2) Change status (Available/Break) in UI; pill updates immediately (no refresh).
3) Watch server logs for `status_update` broadcasts (optional).

Manual Dial
1) Set agent to Available.
2) Dial a number from retro phone/manual form.
3) UI shows call ringing → answered → wrapup on customer hangup; disposition modal appears; after submit, agent returns to Available.
4) If WebRTC enabled, hangup drops browser call; otherwise softphone rings/ends.

Autodial/Hopper
1) Ensure OutboundQueue has pending rows (seed/import). Hopper size per campaign (default 500).
2) Start Celery/beat; verify pending count drops when agent Available.
3) No available agents ⇒ no dialing (check Celery logs).
4) Queue row statuses: pending → dialing → answered → completed.

Wrap-up & Timeout
1) After customer leg ends, agent status becomes wrapup.
2) Disposition submission returns agent to Available.
3) If no disposition submitted, wrapup auto-resets after campaign wrapup_timeout (default 120s).

Lead Screen Pop
1) On call start/answer, lead card should populate using lead_id or phone number (last 10 digits fallback).

WebRTC (optional)
1) Enable WebRTC on agent phone; confirm JsSIP loads and registers (status toast shows registered).
2) Place a call from browser; hangup from UI ends call.
3) If JsSIP missing or disabled, fallback to external softphone.

Hangup Behavior
1) Hangup from agent panel should terminate agent & customer legs (bridge destroyed) and move to wrapup.

Busy/Wrapup Resets
1) Agents stuck in busy without current_call auto-reset after 10 minutes.
2) Agents stuck in wrapup auto-reset after wrapup_timeout per campaign (or 5 min default).

Notes
- Hopper uses Redis keys `hopper:<campaign_id>`.
- Queue recycler recycles dispositions `no_answer`/`busy` after 5 minutes.
