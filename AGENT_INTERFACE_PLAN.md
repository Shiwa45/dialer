# Agent Panel Revamp Plan

This document tracks the work required to give agents a purpose-built experience (status control, scripts, dispositions, and mode-aware dialing) while keeping dial-prefix enforcement consistent across the stack.

## 1. Baseline Analysis
- [x] Review existing agent templates (`templates/agents/*`) and JS to understand current capabilities.
- [x] Audit `AgentStatus`, `CallLog`, `Campaign` models and telephony services to map data dependencies.
- [x] Inspect current APIs/endpoints (`agents/urls.py`, `telephony/views.py`) for reuse vs. refactor.

## 2. Agent Workspace UI
- [x] Design dedicated layout (status bar, call panel, lead/script tabs) that is separate from admin views.
- [x] Implement status controls (Available, Break types) wired to `AgentStatus`.
- [x] Add real-time updates via Channels or lightweight polling for call assignments and status changes.

## 3. Call Lifecycle & Disposition
- [x] Ensure lead details + campaign scripts load when a call is assigned.
- [x] After hangup, show blocking disposition modal (dropdown + notes) and persist to `CallLog`.
- [x] Reset agent status per workflow (auto-return to Available or selected break).

## 4. Dialing Modes
- [ ] **Autodial**: When Available, auto-fetch leads and originate via ARI; only surface UI when connected.
- [ ] **Predictive**: Integrate pacing logic (calls per available agent) and manage overflow/idle scenarios.
- [x] **Manual**: Provide keypad/search interface; restrict based on campaign permissions.
- [ ] Expose mode metadata from `Campaign` to the agent UI so it adapts dynamically.

## 5. Dial Prefix Enforcement
- [ ] Store/confirm `dial_prefix` on Campaigns and Carriers.
- [ ] Before every originate, prepend the prefix server-side (never rely on agent input).
- [ ] Validate prefixes in UI (read-only) and backend (sanity checks to avoid cross-context dialing).

## 6. Backend Services
- [ ] Extend `telephony/services.AsteriskService` to support the new dialing flows.
- [ ] Add APIs for status updates, dispositions, and manual originate requests with prefix injection.
- [ ] Build/extend a worker (Celery or management command) that schedules autodial/predictive calls.

## 7. Testing & QA
- [ ] Unit tests for new services/endpoints (status changes, dispositions, originate prefixing).
- [ ] End-to-end dry runs for each mode using sample campaigns/leads.
- [ ] Verify dialplan originations hit the correct prefix context and that UI reflects call states accurately.

## 8. Rollout
- [ ] Document agent workflow (login → status → call handling → disposition).
- [ ] Provide admin checklist for configuring campaigns/carriers with required prefixes.
- [ ] Monitor logs/metrics after deployment to ensure no dropped calls or misrouted prefixes.

> **Note:** Before implementing each section, review the relevant files and project structure to avoid regressions and ensure compatibility with the existing telephony stack.
