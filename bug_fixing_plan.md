Phase 1: Architecture & Real-Time State Management (The "Brain")

Status:
- Hopper: ✅ Redis-backed hopper per campaign with configurable size and recycler; dialer pulls from hopper and skips when no available agents.
- Global state cache: ❌ (agent/live call keys in Redis still TODO; status currently from DB/WS).
The root cause of "Agent panel is static" and "No real-time monitoring" is the lack of a centralized State Engine. In Vicidial, the database is hammered to maintain state. In modern stacks (like yours), we should use Redis.

The Problem: Currently, your system likely updates a database row when a call starts. The Agent's browser doesn't know the row changed until the page refreshes. The Solution: Use Redis as an "Event Bus" and "State Cache." (partially addressed via Channels + ARI events; Redis event bus still TODO)

Implement a "Hopper" (Lead Cache): ✅

Concept (Borrowed from Vicidial): Don't query the massive SQL Leads table every second to find the next number.

Fix: Create a Celery beat task that moves the next 500 leads per campaign into a Redis List (The Hopper). The Dialer pulls extremely fast from Redis, not Postgres.

Global State Store: ❌ (planned)

You need to know the exact status of every agent (IDLE, INCALL, PAUSED, DEAD) in milliseconds.

Store agent_status:{agent_id} and live_call:{call_id} in Redis.

The "Monitoring Dashboard" you want will simply read these keys from Redis rather than querying the database.

Phase 2: Fixing the Agent Panel (The "Frontend")

Status:
- WebSocket loop: ✅ ARI broadcasts → Channels → agent WebSocket → UI updates (status/call start/answer/end).
- UI state machine: ✅ Agent panel reacts to WS events; hangup/disposition wired; lead pop via lead_id/number.
- WebRTC integration: ▶️ Basic JsSIP bootstrap and optional in-browser dial/hangup; still needs full media handling/edge cases.
The Agent Panel needs to become a Single Page Application (SPA) logic, even if you are using Django templates. It must be event-driven.

1. Fix the WebSocket (Django Channels) Loop:

Current State: Your consumers.py exists, but likely isn't receiving events from Asterisk.

The Fix:

ARI Worker Bridge: Your ari_worker.py (which runs as a background process listening to Asterisk) must import channels.layers.

When Asterisk says StasisStart or ChannelStateChange, the ari_worker must immediately fire a message to the specific Agent's WebSocket group group_send(f"agent_{agent_id}", {"type": "call_incoming", ...}).

Frontend Listener: In agent_dashboard.js, the socket.onmessage function needs to parse these events and toggle CSS classes (e.g., show the "Hangup" button, hide "Dial" button) dynamically.

2. WebRTC Integration (Softphone in Browser): ▶️ Partial (JsSIP loaded when enabled; basic call/hangup)

Current State: You rely on an external softphone (Zoiper/Microsip). This causes the disconnect between the browser and the call.

The Fix: Integrate JSSIP or SIP.js directly into agent_dashboard.html.

The Agent Panel becomes the phone.

When the browser connects via WebSocket to Asterisk (using configured WSS ports), the audio flows through the browser.

This solves the "Hangup" issue. When the agent clicks "Hangup" in the HTML, JS sends a SIP BYE request directly, or sends an API request to Django to hang up the channel via ARI.

Phase 3: Fixing the Telephony & Autodialer Logic (The "Engine")

Status:
- Dialer engine: ▶️ Using hopper + available-agent guard; queue status sync improved; still no holding bridge/AMD.
- Disposition/Wrap-up: ✅ Wrap-up status, timeout, disposition required; queue rows updated on disposition.
Your manual and auto-dial workflows are disconnected. We need to unify them using Asterisk ARI (Asterisk REST Interface) fully.

1. The "Dialer" Engine (Script Replacement):

Currently, you have a script running loops.

The Fix: Create a dedicated Dialing Service (Daemon).

It checks active_agents count.

It checks dial_level (e.g., 3:1 ratio).

It pulls leads from the Hopper (Redis).

It initiates calls via ARI (asterisk.channels.originate).

Crucial Step: It places the originated call into a "Holding Bridge" or "Parking Lot" immediately.

AMD (Answering Machine Detection): Enable Asterisk's AMD. If a human answers, then bridge to an available agent.

2. Solving the "Call Disposition" Issue:

Currently, the system doesn't know when a call ends.

The Fix:

Listen for the ARI StasisEnd event.

When received, the backend marks the CallLog as "Finished" but keeps the Agent Session as "Wrap-up/Disposition."

The Agent Panel detects this state via WebSocket. It forces a popup: "Select Disposition" (Sale, No Answer, DNC).

The Agent cannot dial or receive new calls until a disposition is selected.

Phase 4: Advanced Monitoring & Reporting (The "Eyes")

Status:
- Real-Time Dashboard: ❌ not started (would read Redis state).
- Reporting/agent logs: ❌ not started.
To match GoAutodial/Vicidial, you need granularity.

1. Real-Time Dashboard (The Matrix):

Create a view that polls Redis (not SQL) every 1 second or uses WebSockets.

Columns: Agent Name, State (Color Coded), Time in State, Campaign, Current Number.

Functions: Listen (Chanspy), Barge (Join Bridge), Force Logout.

2. Reporting:

You need to aggregate your raw logs.

Tables needed:

call_log: Every attempt.

agent_log: Every status change (Login time, Pause time, Wait time, Talk time).

lead_log: History of a specific lead.

KPIs: AHT (Average Handle Time), ASA (Average Speed of Answer), Drop Rate (Crucial for compliance).

Phase 5: Step-by-Step Execution Plan
Here is the logical order to tackle the code:

Infrastructure Setup (Docker/Configs):

Ensure Asterisk is configured for WSS (Secure WebSockets) for WebRTC.

Set up Redis container in docker-compose.yml.

Fix the Core Event Loop (Backend):

Refactor ari_worker.py to be robust. It is the "source of truth." It must publish every event to Django Channels.

Frontend "State Machine" (JS):

Rewrite agent_dashboard.js. Stop using static clicks. Make it react to WebSocket messages.

Add SIP.js library. Connect the browser to Asterisk.

Autodialer Logic Refactor:

Implement the "Hopper" in campaigns/tasks.py.

Rewrite the dialing loop to respect the "Adaptive Ratio" (don't dial if no agents are waiting).

Disposition & Wrap-up:

Enforce the "Wrap-up" state in the database and frontend.

Monitoring:

Build the Admin Dashboard using the data flowing through Redis.
