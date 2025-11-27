// Simplified agent panel controller with reliable call state handling.
// Keeps current call visible until disposition is done and mirrors events from polling + websocket.

class AgentDashboard {
    constructor(root) {
        this.root = root;
        this.csrfToken = this._getCsrf();

        this.urls = {
            status: root.dataset.statusUrl,
            callStatus: root.dataset.callStatusUrl,
            leadInfo: root.dataset.leadInfoUrl,
            disposition: root.dataset.dispositionUrl,
            manualDial: root.dataset.manualDialUrl,
            hangup: root.dataset.hangupUrl,
            hold: root.dataset.holdUrl,
        };
        this.agentId = root.dataset.agentId || '';

        this.state = {
            activeCall: null,
            lastEndedCall: null,
            phoneRegistered: root.querySelector('[data-phone-registration]')?.dataset.registered === 'true',
            isDisposing: false,
            dispositionComplete: false,
        };

        this.el = {
            callPlaceholder: root.querySelector('[data-call-placeholder]'),
            callDetails: root.querySelector('[data-call-details]'),
            callNumber: root.querySelector('[data-call-number]'),
            callState: root.querySelector('[data-call-state]'),
            callDuration: root.querySelector('[data-call-duration]'),
            dispositionBtn: root.querySelector('[data-open-disposition]'),
            dispositionModal: document.getElementById('disposition-modal'),
            dispositionForm: document.getElementById('disposition-form'),
            dispositionCallInput: document.getElementById('disposition-call-id'),
            dispositionSelect: document.getElementById('disposition-select'),
            dispositionNotes: document.getElementById('disposition-notes'),
            hangupBtn: root.querySelector('[data-hangup-call]'),
            holdBtn: root.querySelector('[data-hold-call]'),
            statusToast: root.querySelector('[data-status-toast]'),
            phoneStatus: root.querySelector('[data-phone-registration]'),
            manualForm: document.getElementById('manual-dial-form'),
            manualInput: root.querySelector('[data-manual-input]'),
            manualCampaign: document.getElementById('manual-dial-campaign'),
        };

        this.timers = { duration: null, startedAt: null };

        this._bindUI();
        this._pollCallStatus();
        this.pollInterval = setInterval(() => this._pollCallStatus(), 5000);
        this._initWebsocket();
    }

    // ------------------------------------------------------------
    // UI Binding
    // ------------------------------------------------------------
    _bindUI() {
        if (this.el.hangupBtn) {
            this.el.hangupBtn.addEventListener('click', () => this._hangup());
            this.el.hangupBtn.disabled = true;
        }
        if (this.el.holdBtn) {
            this.el.holdBtn.addEventListener('click', () => this._toggleHold());
            this.el.holdBtn.disabled = true;
        }
        if (this.el.dispositionBtn) {
            this.el.dispositionBtn.addEventListener('click', () => this._openDisposition());
            this.el.dispositionBtn.disabled = true;
        }
        if (this.el.dispositionForm) {
            this.el.dispositionForm.addEventListener('submit', (e) => {
                e.preventDefault();
                this._submitDisposition();
            });
            const cancel = this.el.dispositionModal?.querySelector('[data-disposition-cancel]');
            cancel?.addEventListener('click', () => this._closeDisposition());
        }
        if (this.el.manualForm) {
            this.el.manualForm.addEventListener('submit', (e) => {
                e.preventDefault();
                this._manualDial();
            });
        }
        this._bindRetroPhone();
        this._bindKeyboardDial();
    }

    _bindRetroPhone() {
        const keys = this.root.querySelectorAll('.phone-key');
        const display = document.getElementById('phone-number-display');
        const callBtn = document.getElementById('phone-call-btn');
        const hangupBtn = document.getElementById('phone-hangup-btn');
        const clearBtn = document.getElementById('phone-clear-btn');
        this.retroCallBtn = callBtn;
        this.retroHangupBtn = hangupBtn;
        this.retroNumber = '';
        keys.forEach((btn) => {
            btn.addEventListener('click', () => {
                this.retroNumber += btn.dataset.key || '';
                display.textContent = this.retroNumber;
            });
        });
        clearBtn?.addEventListener('click', () => {
            this.retroNumber = this.retroNumber.slice(0, -1);
            display.textContent = this.retroNumber;
        });
        callBtn?.addEventListener('click', () => {
            if (this.retroNumber) {
                this._manualDial(this.retroNumber);
            }
        });
        hangupBtn?.addEventListener('click', () => this._hangup());
        // initial state: show call, hide hangup
        if (this.retroHangupBtn) this.retroHangupBtn.style.display = 'none';
        if (this.retroCallBtn) this.retroCallBtn.style.display = 'block';
    }

    _bindKeyboardDial() {
        document.addEventListener('keydown', (evt) => {
            const target = evt.target;
            const tag = target?.tagName;
            if (tag && ['INPUT', 'TEXTAREA', 'SELECT'].includes(tag)) return;
            if (evt.metaKey || evt.ctrlKey || evt.altKey) return;

            const key = evt.key;
            if (/^[0-9]$/.test(key) || key === '*' || key === '#' || key === '+') {
                this.retroNumber += key;
                const display = document.getElementById('phone-number-display');
                if (display) display.textContent = this.retroNumber;
                evt.preventDefault();
                return;
            }
            if (key === 'Backspace') {
                this.retroNumber = this.retroNumber.slice(0, -1);
                const display = document.getElementById('phone-number-display');
                if (display) display.textContent = this.retroNumber;
                evt.preventDefault();
                return;
            }
            if (key === 'Enter') {
                if (this.retroNumber) {
                    this._manualDial(this.retroNumber);
                }
                evt.preventDefault();
                return;
            }
            if (key === 'Escape') {
                this._hangup();
                evt.preventDefault();
            }
        });
    }

    // ------------------------------------------------------------
    // Call State Handling
    // ------------------------------------------------------------
    _applyCall(call) {
        // Normalize status: if we have duration > 0 but status is empty/initiated, treat as in-progress
        let status = (call.status || '').toLowerCase();
        if ((!status || status === 'initiated') && call.duration && call.duration > 0) {
            status = 'in-progress';
        }
        this.state.activeCall = call;
        this.state.lastEndedCall = null;
        this.state.dispositionComplete = false;
        if (this.el.callPlaceholder) this.el.callPlaceholder.hidden = true;
        if (this.el.callDetails) this.el.callDetails.hidden = false;
        if (this.el.callNumber) this.el.callNumber.textContent = call.number || 'Unknown';
        if (this.el.callState) this.el.callState.textContent = status || 'active';
        if (this.el.hangupBtn) this.el.hangupBtn.disabled = false;
        if (this.el.holdBtn) this.el.holdBtn.disabled = !Boolean(this.urls.hold);
        if (this.el.dispositionBtn) this.el.dispositionBtn.disabled = true;
        if (this.retroCallBtn) this.retroCallBtn.style.display = 'none';
        if (this.retroHangupBtn) this.retroHangupBtn.style.display = 'block';
        this._startDurationTimer(call.duration || 0);
    }

    _setIdle() {
        this.state.activeCall = null;
        if (this.el.callPlaceholder) this.el.callPlaceholder.hidden = false;
        if (this.el.callDetails) this.el.callDetails.hidden = true;
        if (this.el.callNumber) this.el.callNumber.textContent = '—';
        if (this.el.callState) this.el.callState.textContent = 'idle';
        if (this.el.callDuration) this.el.callDuration.textContent = '00:00';
        if (this.el.hangupBtn) this.el.hangupBtn.disabled = true;
        if (this.el.holdBtn) this.el.holdBtn.disabled = true;
        if (this.retroCallBtn) this.retroCallBtn.style.display = 'block';
        if (this.retroHangupBtn) this.retroHangupBtn.style.display = 'none';
        this._stopDurationTimer();
    }

    _endCallAndDispose(callId) {
        // Prevent reopening if we already saved disposition for this call
        if (this.state.dispositionComplete) return;
        const id = callId || this.state.activeCall?.id || this.state.lastEndedCall;
        this.state.activeCall = null;
        this.state.lastEndedCall = id;
        this.state.dispositionComplete = false;
        this._setIdle();
        if (this.el.dispositionBtn) this.el.dispositionBtn.disabled = false;
        if (id && !this.state.isDisposing) {
            this.state.isDisposing = true;
            this._openDisposition(id);
        }
    }

    // ------------------------------------------------------------
    // Actions
    // ------------------------------------------------------------
    _manualDial(numberOverride = null) {
        if (!this.urls.manualDial) return;
        const raw = numberOverride || this.el.manualInput?.value || '';
        const digits = raw.replace(/[^\d+#*+]/g, '');
        if (!digits) return;
        const payload = new URLSearchParams();
        payload.append('phone_number', digits);
        if (this.el.manualCampaign) payload.append('campaign_id', this.el.manualCampaign.value || '');
        fetch(this.urls.manualDial, {
            method: 'POST',
            headers: this._formHeaders(),
            body: payload.toString(),
        })
            .then((r) => r.json())
            .then((res) => {
                if (res.success) {
                if (this.el.manualInput) this.el.manualInput.value = '';
                this._applyCall({
                    id: res.call_id,
                    number: digits,
                    status: 'initiated',
                    duration: 0,
                });
            } else if (res.call_id) {
                this._endCallAndDispose(res.call_id);
            }
        })
        .catch(() => { });
    }

    _hangup() {
        const callId = this.state.activeCall?.id || this.state.lastEndedCall;
        if (callId && this.urls.hangup) {
            const payload = new URLSearchParams();
            payload.append('call_id', callId);
            fetch(this.urls.hangup, {
                method: 'POST',
                headers: this._formHeaders(),
                body: payload.toString(),
            }).finally(() => {
                this._endCallAndDispose(callId);
            });
        } else {
            this._endCallAndDispose(callId);
        }
    }

    _toggleHold() {
        const callId = this.state.activeCall?.id;
        if (!callId || !this.urls.hold) return;
        const payload = new URLSearchParams();
        payload.append('call_id', callId);
        fetch(this.urls.hold, {
            method: 'POST',
            headers: this._formHeaders(),
            body: payload.toString(),
        }).catch(() => { });
    }

    // ------------------------------------------------------------
    // Disposition
    // ------------------------------------------------------------
    _openDisposition(callId = null) {
        if (this.state.dispositionComplete) return;
        if (!this.el.dispositionModal) return;
        const targetId = callId || this.state.lastEndedCall;
        if (this.el.dispositionCallInput) this.el.dispositionCallInput.value = targetId || '';
        if (this.el.dispositionSelect) {
            // Only reset if we are opening for a new call
            if (this.el.dispositionSelect.dataset.callId !== String(targetId)) {
                this.el.dispositionSelect.value = '';
                this.el.dispositionSelect.dataset.callId = targetId || '';
            }
            if (!this.el.dispositionSelect.options.length) {
                const opt = document.createElement('option');
                opt.value = '';
                opt.textContent = 'No dispositions configured';
                opt.disabled = true;
                opt.selected = true;
                this.el.dispositionSelect.appendChild(opt);
            }
        }
        if (this.el.dispositionNotes) this.el.dispositionNotes.value = '';
        this.el.dispositionModal.removeAttribute('hidden');
    }

    _closeDisposition() {
        this.el.dispositionModal?.setAttribute('hidden', 'hidden');
        this.state.lastEndedCall = null;
        this.state.isDisposing = false;
        this.state.dispositionComplete = true;
    }

    _submitDisposition() {
        if (!this.urls.disposition || !this.el.dispositionForm) return;
        const fd = new FormData(this.el.dispositionForm);
        const callId = fd.get('call_id');
        const dispId = fd.get('disposition_id');
        if (!callId || !dispId) {
            this._showToast('Select an outcome before saving', true);
            return;
        }
        const payload = new URLSearchParams(fd);
        fetch(this.urls.disposition, {
            method: 'POST',
            headers: this._formHeaders(),
            body: payload.toString(),
        })
            .then((r) => r.json())
            .then((res) => {
                if (res.success) {
                    this._closeDisposition();
                    this.state.lastEndedCall = null;
                    this.state.dispositionComplete = true;
                    this.state.isDisposing = false;
                } else {
                    this._showToast(res.error || 'Failed to save disposition', true);
                }
            })
            .catch(() => { this._showToast('Network error saving disposition', true); });
    }

    // ------------------------------------------------------------
    // Polling + Websocket
    // ------------------------------------------------------------
    _pollCallStatus() {
        if (!this.urls.callStatus) return;
        fetch(this.urls.callStatus, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
            .then((r) => r.json())
            .then((data) => this._handleStatusPayload(data))
            .catch(() => { });
    }

    _initWebsocket() {
        if (!this.agentId) return;
        const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const url = `${proto}//${window.location.host}/ws/agent/${this.agentId}/`;
        try {
            this.ws = new WebSocket(url);
        } catch (e) {
            return;
        }
        this.ws.onmessage = (evt) => {
            try {
                const payload = JSON.parse(evt.data);
                this._handleStatusPayload(payload);
            } catch (e) { }
        };
    }

    _handleStatusPayload(data) {
        if (!data) return;
        // Always keep phone registration updated
        if (Object.prototype.hasOwnProperty.call(data, 'phone_registered')) {
            this._updateRegistration(data.phone_registered);
        }
        // If we are in the middle of disposition, ignore further call updates
        if (this.state.isDisposing || this.state.dispositionComplete) return;
        if (Object.prototype.hasOwnProperty.call(data, 'phone_registered')) {
            this._updateRegistration(data.phone_registered);
        }
        const call = data.call || data.current_call || null;
        if (call && call.id) {
            const status = (call.status || '').toLowerCase();
            const endedStates = ['completed', 'hangup', 'failed', 'busy', 'no_answer', 'congested'];
            if (endedStates.includes(status)) {
                this._endCallAndDispose(call.id);
            } else {
                this._applyCall(call);
            }
            return;
        }
        // Only clear the call when we get an explicit end event or hangup initiated locally
        if (data.type === 'call_ended') {
            this._endCallAndDispose(data.call_id);
        }
    }

    // ------------------------------------------------------------
    // Helpers
    // ------------------------------------------------------------
    _getCsrf() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        if (meta) return meta.content;
        const m = document.cookie.match(/csrftoken=([^;]+)/);
        return m ? m[1] : '';
    }

    _formHeaders() {
        return {
            'X-Requested-With': 'XMLHttpRequest',
            'X-CSRFToken': this.csrfToken,
            'Content-Type': 'application/x-www-form-urlencoded',
        };
    }

    _updateRegistration(registered) {
        this.state.phoneRegistered = !!registered;
        if (this.el.phoneStatus) {
            this.el.phoneStatus.dataset.registered = this.state.phoneRegistered ? 'true' : 'false';
            this.el.phoneStatus.textContent = this.state.phoneRegistered ? 'Softphone registered' : 'Not registered';
        }
        const retroStatus = document.getElementById('phone-status-display');
        if (retroStatus) {
            retroStatus.textContent = this.state.phoneRegistered ? 'READY' : 'NOT REGISTERED';
        }
    }

    _startDurationTimer(initialSeconds) {
        this._stopDurationTimer();
        const start = Date.now() - (initialSeconds || 0) * 1000;
        this.timers.startedAt = start;
        if (this.el.callDuration) {
            this.el.callDuration.textContent = this._formatDuration(initialSeconds || 0);
        }
        this.timers.duration = setInterval(() => {
            const elapsed = Math.floor((Date.now() - this.timers.startedAt) / 1000);
            if (this.el.callDuration) {
                this.el.callDuration.textContent = this._formatDuration(elapsed);
            }
        }, 1000);
    }

    _stopDurationTimer() {
        if (this.timers.duration) {
            clearInterval(this.timers.duration);
            this.timers.duration = null;
        }
        this.timers.startedAt = null;
    }

    _formatDuration(totalSeconds) {
        const mins = Math.floor(totalSeconds / 60).toString().padStart(2, '0');
        const secs = (totalSeconds % 60).toString().padStart(2, '0');
        return `${mins}:${secs}`;
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const root = document.querySelector('[data-agent-dashboard]');
    if (root) {
        window.AgentDashboard = new AgentDashboard(root);
    }
});
