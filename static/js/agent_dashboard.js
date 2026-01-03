class RetroPhoneController {
    constructor(container, options = {}) {
        this.container = container;
        this.options = options;
        this.toast = typeof options.toast === 'function' ? options.toast : () => { };
        this.onRegistrationChange =
            typeof options.onRegistrationChange === 'function' ? options.onRegistrationChange : () => { };
        this.manualDialHandler =
            typeof options.manualDialHandler === 'function' ? options.manualDialHandler : null;
        this.webrtcEnabled = !!options.webrtcEnabled;
        this.webrtcConfig = options.webrtcConfig || {};
        this.softphoneRegistered = !!options.softphoneRegistered;
        this.phoneNumber = '';
        this.callTimer = null;
        this.callDuration = 0;
        this.isMuted = false;
        this.isOnHold = false;
        this.ua = null;
        this.uaRegistered = false;
        this.currentSession = null;
        this.remoteAudio =
            this.container.querySelector('[data-webrtc-audio]') ||
            document.querySelector('[data-webrtc-audio]') ||
            null;

        this.displayEl = this.container.querySelector('#phone-number-display');
        this.statusEl = this.container.querySelector('#phone-status-display');
        this.timerEl = this.container.querySelector('#phone-timer');
        this.callBtn = this.container.querySelector('#phone-call-btn');
        this.hangupBtn = this.container.querySelector('#phone-hangup-btn');
        this.muteBtn = this.container.querySelector('#phone-mute-btn');
        this.holdBtn = this.container.querySelector('#phone-hold-btn');
        this.clearBtn = this.container.querySelector('#phone-clear-btn');
        this.keyButtons = Array.from(this.container.querySelectorAll('.phone-key'));

        this._bindUI();

        if (this.webrtcEnabled && this._hasValidWebRTCConfig()) {
            this._initWebRTC();
        } else {
            this.webrtcEnabled = false;
            this._updateIdleStatus();
        }
    }

    _hasValidWebRTCConfig() {
        if (!this.webrtcEnabled || !this.webrtcConfig || this.webrtcConfig.success === false) {
            return false;
        }
        const cfg = this.webrtcConfig;
        return Boolean(cfg.username || cfg.extension) && Boolean(cfg.password) && Boolean(cfg.server);
    }

    _bindUI() {
        this._updateIdleStatus();
        this._updateNumberDisplay();
        this._toggleCallButtons(false);
        this._bindKeyboard();
        if (this.callBtn) {
            this.callBtn.addEventListener('click', () => this._handleCall());
        }
        if (this.hangupBtn) {
            this.hangupBtn.addEventListener('click', () => this._handleHangup());
        }
        if (this.clearBtn) {
            this.clearBtn.addEventListener('click', () => this._handleClear());
        }
        if (this.muteBtn) {
            this.muteBtn.addEventListener('click', () => this._toggleMute());
        }
        if (this.holdBtn) {
            this.holdBtn.addEventListener('click', () => this._toggleHold());
        }
        this.keyButtons.forEach((btn) => {
            btn.addEventListener('click', () => {
                const digit = btn.dataset.key || '';
                this._handleDigit(digit, btn);
            });
        });
        this._updateCallButtonState();
    }

    _bindKeyboard() {
        this._keyboardHandler = (evt) => {
            if (this._shouldIgnoreKeyEvent(evt)) {
                return;
            }
            const key = evt.key;
            if (/^[0-9]$/.test(key)) {
                evt.preventDefault();
                this._handleDigit(key);
                return;
            }
            if (key === '*' || key === '#') {
                evt.preventDefault();
                this._handleDigit(key);
                return;
            }
            if (key === '+' || (key === '=' && evt.shiftKey)) {
                evt.preventDefault();
                this._handleDigit('+');
                return;
            }
            if (key === 'Backspace') {
                evt.preventDefault();
                this._handleClear();
                return;
            }
            if (key === 'Enter') {
                evt.preventDefault();
                this._handleCall();
                return;
            }
            if (key === 'Escape') {
                evt.preventDefault();
                this._handleHangup();
            }
        };
        window.addEventListener('keydown', this._keyboardHandler);
    }

    _shouldIgnoreKeyEvent(evt) {
        if (evt.metaKey || evt.ctrlKey || evt.altKey) return true;
        const target = evt.target;
        if (!target) return false;
        const tag = target.tagName;
        if (!tag) return false;
        const interactiveTags = ['INPUT', 'TEXTAREA', 'SELECT'];
        if (interactiveTags.includes(tag)) return true;
        if (target.isContentEditable) return true;
        return false;
    }

    _handleDigit(digit, buttonEl) {
        if (!digit) return;
        if (this.currentSession && this.webrtcEnabled && this.currentSession.isEstablished()) {
            try {
                this.currentSession.sendDTMF(digit);
            } catch (err) {
                console.warn('Failed to send DTMF', err);
            }
            this._flashButton(buttonEl);
            return;
        }
        if (this.phoneNumber.length >= 32) return;
        this.phoneNumber += digit;
        this._updateNumberDisplay();
        this._updateCallButtonState();
        this._flashButton(buttonEl);
    }

    _handleClear() {
        if (!this.phoneNumber) return;
        this.phoneNumber = this.phoneNumber.slice(0, -1);
        this._updateNumberDisplay();
        this._updateCallButtonState();
    }

    _handleCall() {
        const digits = this._getNormalizedNumber();
        if (!digits) {
            this.toast('Enter a phone number', true);
            return;
        }
        if (this.webrtcEnabled && this.ua && this.uaRegistered) {
            this._dialViaWebRTC(digits);
        } else if (this.webrtcEnabled && (!this.ua || !this.uaRegistered)) {
            this._setStatus('WEBRTC NOT REGISTERED');
            this.toast('WebRTC phone is not registered yet. Please wait or reload.', true);
        } else {
            this._dialViaManual(digits);
        }
    }

    _handleHangup() {
        if (this.currentSession) {
            try {
                this.currentSession.terminate();
            } catch (err) {
                console.warn('Failed to terminate WebRTC session', err);
            }
        }
        if (typeof this.options.onHangup === 'function') {
            this.options.onHangup();
        } else if (!this.currentSession) {
            this.toast('Hang up from your softphone client', false);
            this._resetPhone();
        }
    }

    _toggleMute() {
        if (!this.currentSession || !this.webrtcEnabled) {
            this.toast('Mute control is only available for WebRTC calls', true);
            return;
        }
        this.isMuted = !this.isMuted;
        if (this.isMuted) {
            this.currentSession.mute({ audio: true });
            this._setStatus('MUTED');
            if (this.muteBtn) {
                this.muteBtn.innerHTML = '<i class="fa-solid fa-microphone-slash"></i> UNMUTE';
            }
        } else {
            this.currentSession.unmute({ audio: true });
            this._setStatus('CONNECTED');
            if (this.muteBtn) {
                this.muteBtn.innerHTML = '<i class="fa-solid fa-microphone"></i> MUTE';
            }
        }
    }

    _toggleHold() {
        if (!this.currentSession || !this.webrtcEnabled) {
            this.toast('Hold control is only available for WebRTC calls', true);
            return;
        }
        this.isOnHold = !this.isOnHold;
        try {
            if (this.isOnHold) {
                this.currentSession.hold({ useUpdate: true });
                this._setStatus('ON HOLD');
                if (this.holdBtn) {
                    this.holdBtn.innerHTML = '<i class="fa-solid fa-play"></i> RESUME';
                }
            } else {
                this.currentSession.unhold({ useUpdate: true });
                this._setStatus('CONNECTED');
                if (this.holdBtn) {
                    this.holdBtn.innerHTML = '<i class="fa-solid fa-pause"></i> HOLD';
                }
            }
        } catch (err) {
            console.warn('Hold toggle failed', err);
        }
    }

    _toggleHoldApi() {
        if (!this.holdUrl || !this.activeCallId) {
            this._showToast('No active call to hold', true);
            return;
        }

        // Determine action based on current button state
        const isCurrentlyOnHold = (this.callElements.holdBtn?.dataset.state === 'hold-on');
        const action = isCurrentlyOnHold ? 'unhold' : 'hold';

        const payload = new URLSearchParams();
        payload.append('call_id', this.activeCallId);
        payload.append('action', action);

        fetch(this.holdUrl, {
            method: 'POST',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
                'X-CSRFToken': this.csrfToken,
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: payload.toString(),
        })
            .then((res) => res.json())
            .then((data) => {
                if (data.success) {
                    const isOnHold = data.is_on_hold;
                    if (this.callElements.holdBtn) {
                        this.callElements.holdBtn.dataset.state = isOnHold ? 'hold-on' : 'hold-off';
                        this.callElements.holdBtn.innerHTML = isOnHold
                            ? '<i class="fa-solid fa-play"></i> Resume'
                            : '<i class="fa-solid fa-pause"></i> Hold';
                    }
                    // Also update retro phone state if present
                    if (this.retroPhone) {
                        this.retroPhone.isOnHold = isOnHold;
                        if (isOnHold) this.retroPhone._setStatus('ON HOLD');
                        else this.retroPhone._setStatus('CONNECTED');
                    }
                    this._showToast(data.message || (isOnHold ? 'Call on hold' : 'Call resumed'));
                } else {
                    this._showToast(data.error || 'Hold action failed', true);
                }
            })
            .catch(() => this._showToast('Network error toggling hold', true));
    }

    _dialViaManual(digits) {
        if (!this.manualDialHandler) {
            this.toast('Manual dialing is unavailable', true);
            return;
        }
        this._setStatus('REQUESTING CALL…');
        this._toggleCallButtons(true);
        this.manualDialHandler(digits)
            .then((res) => {
                if (res && res.success) {
                    this._setStatus('CHECK YOUR PHONE');
                    setTimeout(() => this._resetPhone(), 4000);
                } else {
                    const error = (res && res.error) || 'Dial failed';
                    this._setStatus('CALL FAILED');
                    this.toast(error, true);
                    this._toggleCallButtons(false);
                }
            })
            .catch((err) => {
                const message = err && err.message ? err.message : 'Dial failed';
                this._setStatus('CALL FAILED');
                this.toast(message, true);
                this._toggleCallButtons(false);
            });
    }

    _dialViaWebRTC(digits) {
        if (typeof JsSIP === 'undefined') {
            this.toast('WebRTC library missing', true);
            return;
        }
        try {
            const cfg = this.webrtcConfig;
            const target = this._buildTargetUri(digits);
            const options = {
                mediaConstraints: { audio: true, video: false },
                rtcOfferConstraints: { offerToReceiveAudio: true, offerToReceiveVideo: false },
            };
            if (cfg.ice_servers && cfg.ice_servers.length) {
                options.pcConfig = { iceServers: cfg.ice_servers };
            }
            this.ua.call(target, options);
            this._toggleCallButtons(true);
            this._setStatus('CALLING…');
        } catch (err) {
            console.error('WebRTC call failed', err);
            this._setStatus('CALL FAILED');
            this._toggleCallButtons(false);
            this.toast('Failed to start WebRTC call', true);
        }
    }

    _buildTargetUri(number) {
        const cfg = this.webrtcConfig || {};
        const domain = cfg.from_domain || cfg.server;
        return `sip:${number}@${domain}`;
    }

    _flashButton(buttonEl) {
        if (!buttonEl) return;
        buttonEl.style.transform = 'scale(0.96)';
        setTimeout(() => {
            buttonEl.style.transform = '';
        }, 120);
    }

    _setStatus(text) {
        if (this.statusEl) {
            this.statusEl.textContent = text;
        }
    }

    _updateNumberDisplay() {
        if (this.displayEl) {
            this.displayEl.textContent = this.phoneNumber;
        }
    }

    _toggleCallButtons(inCall) {
        if (this.callBtn) {
            this.callBtn.style.display = inCall ? 'none' : 'block';
        }
        if (this.hangupBtn) {
            this.hangupBtn.style.display = inCall ? 'block' : 'none';
        }
        if (!inCall) {
            this._updateCallButtonState();
        }
    }

    _updateCallButtonState() {
        if (!this.callBtn) return;
        const hasDigits = this.phoneNumber.length > 0;
        this.callBtn.disabled = !hasDigits;
    }

    _getNormalizedNumber() {
        return (this.phoneNumber || '').replace(/[^\d*#\+]/g, '');
    }

    _resetPhone() {
        this.phoneNumber = '';
        this._updateNumberDisplay();
        this._toggleCallButtons(false);
        this._stopTimer();
        this.isMuted = false;
        this.isOnHold = false;
        if (this.muteBtn) {
            this.muteBtn.innerHTML = '<i class="fa-solid fa-microphone"></i> MUTE';
        }
        if (this.holdBtn) {
            this.holdBtn.innerHTML = '<i class="fa-solid fa-pause"></i> HOLD';
        }
        if (this.timerEl) {
            this.timerEl.style.display = 'none';
            this.timerEl.textContent = '00:00';
        }
        this._updateIdleStatus();
    }

    _startTimer() {
        if (!this.timerEl) return;
        this._stopTimer();
        this.callDuration = 0;
        this.timerEl.style.display = 'block';
        this.timerEl.textContent = '00:00';
        this.callTimer = setInterval(() => {
            this.callDuration += 1;
            const minutes = Math.floor(this.callDuration / 60)
                .toString()
                .padStart(2, '0');
            const seconds = (this.callDuration % 60).toString().padStart(2, '0');
            this.timerEl.textContent = `${minutes}:${seconds}`;
        }, 1000);
    }

    _stopTimer() {
        if (this.callTimer) {
            clearInterval(this.callTimer);
            this.callTimer = null;
        }
    }

    _initWebRTC() {
        if (typeof JsSIP === 'undefined') {
            console.warn('JsSIP not available');
            this.webrtcEnabled = false;
            this._setStatus('WebRTC script missing');
            this._updateIdleStatus();
            return;
        }
        const cfg = this.webrtcConfig;
        const protocol = cfg.protocol || 'wss';
        const port = cfg.port || 8089;
        const socketUrl = `${protocol}://${cfg.server}:${port}/ws`;
        let socket;
        try {
            socket = new JsSIP.WebSocketInterface(socketUrl);
        } catch (err) {
            console.error('Failed to create WebSocketInterface', err);
            this.webrtcEnabled = false;
            this._setStatus('WebRTC socket error');
            return;
        }
        const uriUser = cfg.username || cfg.extension;
        const domain = cfg.from_domain || cfg.server;
        const uaConfig = {
            sockets: [socket],
            uri: `sip:${uriUser}@${domain}`,
            password: cfg.password,
            authorization_user: uriUser,
            display_name: cfg.display_name || uriUser,
            registrar_server: domain,
            session_timers: false,
            trace_sip: false,
        };
        this.ua = new JsSIP.UA(uaConfig);
        this.ua.on('connected', () => this._setStatus('CONNECTING…'));
        this.ua.on('disconnected', () => this._handleWebRTCDrop('SOCKET CLOSED'));
        this.ua.on('registered', () => {
            this.uaRegistered = true;
            this._setStatus('WEBRTC READY');
            this.onRegistrationChange(true);
        });
        this.ua.on('unregistered', () => this._handleWebRTCDrop('WEBRTC UNREGISTERED'));
        this.ua.on('registrationFailed', (evt) => {
            this.uaRegistered = false;
            console.error('WebRTC registration failed', evt.cause);
            this.toast('WebRTC registration failed. Check credentials.', true);
            this._handleWebRTCDrop('REGISTRATION FAILED');
        });
        this.ua.on('newRTCSession', (evt) => this._handleRTCSession(evt));
        this.ua.start();
    }

    _handleRTCSession(evt) {
        const session = evt.session;
        const originator = evt.originator;
        if (this.currentSession && originator === 'local') {
            session.terminate();
            return;
        }
        this.currentSession = session;
        this._attachSessionEvents(session);
        this._toggleCallButtons(true);
        if (originator === 'local') {
            this._setStatus('CALLING…');
        } else {
            this._setStatus('INCOMING CALL');
        }
    }

    _attachSessionEvents(session) {
        session.on('progress', () => this._setStatus('RINGING…'));
        session.on('accepted', () => {
            this._setStatus('CONNECTED');
            this._startTimer();
        });
        session.on('confirmed', () => {
            this._setStatus('CONNECTED');
            this._startTimer();
        });
        session.on('ended', () => this._handleSessionEnd('CALL ENDED'));
        session.on('failed', (evt) => {
            const reason = evt && evt.cause ? String(evt.cause) : 'CALL FAILED';
            this._handleSessionEnd(reason, true);
        });
        session.on('hold', () => {
            this.isOnHold = true;
            this._setStatus('ON HOLD');
            if (this.holdBtn) {
                this.holdBtn.innerHTML = '<i class="fa-solid fa-play"></i> RESUME';
            }
        });
        session.on('unhold', () => {
            this.isOnHold = false;
            this._setStatus('CONNECTED');
            if (this.holdBtn) {
                this.holdBtn.innerHTML = '<i class="fa-solid fa-pause"></i> HOLD';
            }
        });
        session.on('muted', () => {
            this.isMuted = true;
            if (this.muteBtn) {
                this.muteBtn.innerHTML = '<i class="fa-solid fa-microphone-slash"></i> UNMUTE';
            }
        });
        session.on('unmuted', () => {
            this.isMuted = false;
            if (this.muteBtn) {
                this.muteBtn.innerHTML = '<i class="fa-solid fa-microphone"></i> MUTE';
            }
        });
        if (session.connection) {
            session.connection.addEventListener('track', (event) => {
                if (!this.remoteAudio || !event.streams || !event.streams.length) return;
                this.remoteAudio.srcObject = event.streams[0];
            });
        }
    }

    _handleSessionEnd(statusText, isError = false) {
        this._stopTimer();
        this._setStatus(statusText);
        this._toggleCallButtons(false);
        this.currentSession = null;
        this.isMuted = false;
        this.isOnHold = false;
        if (this.muteBtn) {
            this.muteBtn.innerHTML = '<i class="fa-solid fa-microphone"></i> MUTE';
        }
        if (this.holdBtn) {
            this.holdBtn.innerHTML = '<i class="fa-solid fa-pause"></i> HOLD';
        }
        if (isError) {
            this.toast(statusText || 'Call failed', true);
        }
        setTimeout(() => this._resetPhone(), 1200);
    }

    _handleWebRTCDrop(message) {
        this.uaRegistered = false;
        if (message) {
            this._setStatus(message);
        }
        this.onRegistrationChange(false);
        this._updateIdleStatus();
    }

    _updateIdleStatus() {
        const statusText = this.hasActiveWebRTC()
            ? 'READY'
            : this.softphoneRegistered
                ? 'READY (SOFTPHONE)'
                : 'SOFTPHONE OFFLINE';
        this._setStatus(statusText);
    }

    hasActiveWebRTC() {
        return this.webrtcEnabled && this.uaRegistered;
    }

    setSoftphoneRegistration(isRegistered) {
        this.softphoneRegistered = !!isRegistered;
        if (!this.hasActiveWebRTC()) {
            this._updateIdleStatus();
        }
    }
}

class AgentDashboardUI {
    constructor(root) {
        this.root = root;
        this.statusUrl = root.dataset.statusUrl;
        this.currentStatus = root.dataset.status || 'offline';
        this.statusDisplay = root.querySelector('[data-current-status]');
        this.statusToast = root.querySelector('[data-status-toast]');
        this.statusOptions = this._parseJSON('agent-status-options') || [];
        this.breakCodes = this._parseJSON('agent-break-codes-data') || [];
        this.callStatusData = this._parseJSON('agent-call-status-data') || {};
        this.dispositions = this._parseJSON('agent-dispositions-data') || [];
        this.callStatusUrl = root.dataset.callStatusUrl || '';
        this.leadInfoUrl = root.dataset.leadInfoUrl || '';
        this.dispositionUrl = root.dataset.dispositionUrl || '';
        this.manualDialUrl = root.dataset.manualDialUrl || '';
        this.webrtcEnabled = root.dataset.webrtcEnabled === 'true';
        this.csrfToken = this._getCsrfToken();
        this.phoneStatusEl = root.querySelector('[data-phone-registration]');
        this.webrtcConfig = this._parseJSON('agent-webrtc-config') || {};
        this.hangupUrl = root.dataset.hangupUrl || '';
        this.holdUrl = root.dataset.holdUrl || '';
        this.agentId = root.dataset.agentId || '';
        this.isDisposing = false;
        this.pendingDispositionCallId = null;


        this.breakModal = document.getElementById('break-modal');
        this.breakList = document.getElementById('break-code-list');
        this.breakNotesInput = document.getElementById('break-notes-input');

        this.callElements = {
            placeholder: root.querySelector('[data-call-placeholder]'),
            details: root.querySelector('[data-call-details]'),
            number: root.querySelector('[data-call-number]'),
            state: root.querySelector('[data-call-state]'),
            duration: root.querySelector('[data-call-duration]'),
            leadCard: root.querySelector('[data-lead-card]'),
            leadName: root.querySelector('[data-lead-name]'),
            leadStatus: root.querySelector('[data-lead-status]'),
            leadPhone: root.querySelector('[data-lead-phone]'),
            leadEmail: root.querySelector('[data-lead-email]'),
            leadCompany: root.querySelector('[data-lead-company]'),
            leadLocation: root.querySelector('[data-lead-location]'),
            dispositionBtn: root.querySelector('[data-open-disposition]'),
            hangupBtn: root.querySelector('[data-hangup-call]'),
            holdBtn: root.querySelector('[data-hold-call]'),
        };
        if (this.callElements.dispositionBtn) {
            this.callElements.dispositionBtn.disabled = !this.dispositions.length;
        }

        this.dispositionModal = document.getElementById('disposition-modal');
        this.dispositionForm = document.getElementById('disposition-form');
        this.dispositionCallInput = document.getElementById('disposition-call-id');
        this.dispositionSelect = document.getElementById('disposition-select');
        this.dispositionNotes = document.getElementById('disposition-notes');

        this.manualDialForm = document.getElementById('manual-dial-form');
        this.manualDialInput = document.querySelector('[data-manual-input]');
        this.manualDialCampaign = document.getElementById('manual-dial-campaign');
        this.manualDialButton = document.querySelector('[data-manual-submit]');
        this.manualDialLoading = false;
        this.manualDialDisabledByRegistration = false;
        this.transferUrl = root.dataset.transferUrl || '';
        this.transferForm = document.getElementById('transfer-call-form');
        this.transferSelect = document.querySelector('[data-transfer-target]');
        this.transferButton = document.querySelector('[data-transfer-submit]');
        this.transferButtonLabel = this.transferButton ? this.transferButton.textContent.trim() : 'Transfer Call';
        this.transferLoading = false;

        this._bindStatusButtons();
        this._bindModalEvents();
        const initialPhoneRegistered = typeof this.callStatusData.phone_registered !== 'undefined'
            ? this.callStatusData.phone_registered
            : this.phoneStatusEl?.dataset.registered === 'true';
        this.lastKnownSoftphoneRegistered = !!initialPhoneRegistered;

        this._bindManualDial();
        this._bindTransferForm();
        this._bindDispositionEvents();
        this._bindCallControlButtons();
        this._updateStatusUI(this.currentStatus);
        this._initCallState();
        this._initRetroPhone(this.lastKnownSoftphoneRegistered);
        this._updatePhoneRegistration(initialPhoneRegistered);
        this._initRealtimeChannel();
        this._initRealtimeChannel();
    }

    _getCsrfToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        if (meta) return meta.getAttribute('content');
        // fallback to cookie
        const match = document.cookie.match(/csrftoken=([^;]+)/);
        return match ? match[1] : '';
    }

    _parseJSON(id) {
        const el = document.getElementById(id);
        if (!el) return null;
        try {
            return JSON.parse(el.textContent);
        } catch {
            return null;
        }
    }

    _bindStatusButtons() {
        const buttons = this.root.querySelectorAll('[data-status-trigger]');
        buttons.forEach((btn) => {
            btn.addEventListener('click', () => {
                const status = btn.dataset.statusTrigger;
                if (!status) return;
                if (['break', 'lunch'].includes(status) && this.breakCodes.length) {
                    this._openBreakModal(status);
                } else {
                    const reason = btn.dataset.statusReason || '';
                    this._sendStatus(status, reason);
                }
            });
        });
    }

    _bindModalEvents() {
        if (!this.breakModal) return;
        const closeBtn = this.breakModal.querySelector('[data-break-cancel]');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => this._closeBreakModal());
        }
        this.breakModal.addEventListener('click', (evt) => {
            if (evt.target === this.breakModal) {
                this._closeBreakModal();
            }
        });
    }

    _openBreakModal(targetStatus) {
        if (!this.breakModal || !this.breakList) {
            const note = prompt('Enter break reason (optional):') || '';
            this._sendStatus(targetStatus, note);
            return;
        }

        this.breakModal.dataset.targetStatus = targetStatus;
        this.breakList.innerHTML = '';
        this.breakCodes.forEach((code) => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'break-chip';
            btn.textContent = `${code.name}`;
            btn.style.setProperty('--chip-color', code.color_code || '#6c757d');
            btn.addEventListener('click', () => {
                const notes = this.breakNotesInput ? this.breakNotesInput.value.trim() : '';
                const reason = code.description || code.name;
                this._sendStatus(targetStatus, notes || reason);
                this._closeBreakModal();
            });
            this.breakList.appendChild(btn);
        });

        if (this.breakNotesInput) {
            this.breakNotesInput.value = '';
        }

        this.breakModal.removeAttribute('hidden');
    }

    _closeBreakModal() {
        if (this.breakModal) {
            this.breakModal.setAttribute('hidden', 'hidden');
        }
    }

    _sendStatus(status, reason) {
        if (!this.statusUrl) return;
        const payload = new URLSearchParams();
        payload.append('status', status);
        if (reason) {
            payload.append('break_reason', reason);
        }

        fetch(this.statusUrl, {
            method: 'POST',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
                'X-CSRFToken': this.csrfToken,
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: payload.toString(),
        })
            .then((res) => res.json())
            .then((data) => {
                if (data.success) {
                    this.currentStatus = status;
                    if (status === 'available') {
                        this.clearedCallId = this.activeCallId;
                        this._setCallIdle();
                        this.lastCompletedCallId = null;
                    }
                    this._updateStatusUI(status, reason);
                    this._showToast(data.message || 'Status updated');
                } else {
                    this._showToast(data.error || 'Failed to update status', true);
                }
            })
            .catch(() => this._showToast('Network error updating status', true));
    }

    _updateStatusUI(status, reason = '') {
        if (this.statusDisplay) {
            const label = this._lookupStatusLabel(status);
            this.statusDisplay.textContent = label;
            this.statusDisplay.dataset.status = status;
            if (reason) {
                this.statusDisplay.setAttribute('title', reason);
            } else {
                this.statusDisplay.removeAttribute('title');
            }
        }

        this.root.dataset.status = status;
        const buttons = this.root.querySelectorAll('[data-status-trigger]');
        buttons.forEach((btn) => {
            btn.classList.toggle('is-active', btn.dataset.statusTrigger === status);
        });
    }

    _lookupStatusLabel(value) {
        const match = this.statusOptions.find((opt) => opt.value === value);
        return match ? match.label : value;
    }

    _showToast(message, isError = false) {
        if (!this.statusToast) return;
        this.statusToast.textContent = message;
        this.statusToast.classList.toggle('is-error', isError);
        this.statusToast.classList.add('is-visible');
        clearTimeout(this.toastTimer);
        this.toastTimer = setTimeout(() => {
            this.statusToast.classList.remove('is-visible');
        }, 4000);
    }

    _bindDispositionEvents() {
        if (this.callElements.dispositionBtn) {
            this.callElements.dispositionBtn.addEventListener('click', () => {
                const callId = this.activeCallId || this.lastCompletedCallId;
                if (callId && this.dispositions.length) {
                    this._openDispositionModal(callId);
                } else if (!this.dispositions.length) {
                    this._showToast('No dispositions configured for this campaign', true);
                }
            });
        }

        if (this.dispositionModal) {
            const cancelBtn = this.dispositionModal.querySelector('[data-disposition-cancel]');
            if (cancelBtn) {
                cancelBtn.addEventListener('click', () => {
                    this.isDisposing = false;
                    this.pendingDispositionCallId = null;
                    this._closeDispositionModal();
                });
            }
            this.dispositionModal.addEventListener('click', (evt) => {
                if (evt.target === this.dispositionModal) {
                    this._closeDispositionModal();
                }
            });
        }

        if (this.dispositionForm) {
            this.dispositionForm.addEventListener('submit', (evt) => {
                evt.preventDefault();
                this._submitDisposition();
            });
        }
    }

    _bindCallControlButtons() {
        if (this.callElements.hangupBtn) {
            this.callElements.hangupBtn.addEventListener('click', () => this._requestHangup());
        }
        if (this.callElements.holdBtn) {
            this.callElements.holdBtn.addEventListener('click', () => this._toggleHoldApi());
        }
    }

    _initCallState() {
        const initialCall = this.callStatusData.current_call;
        if (initialCall) {
            this._applyCallState(initialCall);
        } else {
            this._setCallIdle();
        }

        if (this.callStatusUrl) {
            this._pollCallStatus();
            this.callPollInterval = setInterval(() => this._pollCallStatus(), 5000);
        }
    }

    _pollCallStatus() {
        fetch(this.callStatusUrl, {
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
        })
            .then((res) => res.json())
            .then((data) => this._handleCallStatus(data))
            .catch(() => { });
    }

    _handleCallStatus(data) {
        if (this.isDisposing) return; // Ignore updates while user is disposing
        if (!data || data.success === false) {
            // If polling fails but we had a call in progress, assume it ended
            if (this.activeCallId) {
                const completedCallId = this.activeCallId;
                this._setCallIdle();
                this.lastCompletedCallId = completedCallId;
                if (this.dispositions.length) {
                    this._openDispositionModal(completedCallId);
                }
            }
            return;
        }
        if (Object.prototype.hasOwnProperty.call(data, 'phone_registered')) {
            this._updatePhoneRegistration(data.phone_registered);
        }
        const newCall = data.current_call || null;
        if (newCall && newCall.id) {
            if (this.clearedCallId === newCall.id) {
                return; // Ignore stale call that was manually cleared
            }
            if (this.activeCallId !== newCall.id) {
                this._applyCallState(newCall);
            } else {
                this._updateCallDuration(newCall.duration || 0);
                this._updateCallStateLabel(newCall.status);
            }
        } else if (this.activeCallId) {
            // If backend didn't return a call but we have one locally, keep showing it
            // to allow hangup/disposition without forcing a refresh.
            this._updateCallStateLabel('initiated');
            if (this.callElements.hangupBtn) {
                this.callElements.hangupBtn.disabled = false;
            }
            if (this.callElements.dispositionBtn && !this.dispositions.length) {
                this.callElements.dispositionBtn.disabled = true;
            }
        }
    }

    _applyCallState(call) {
        this.activeCallId = call.id;
        this.lastCompletedCallId = null;
        this._updateTransferButtonState();
        this._setCallDisplay(true);
        if (this.callElements.number) {
            this.callElements.number.textContent = call.number || 'Unknown';
        }
        this._updateCallStateLabel(call.status);
        this._startDurationTimer(call.duration || 0);
        if (this.callElements.dispositionBtn) {
            this.callElements.dispositionBtn.disabled = true; // Lock dispose during call
        }
        if (this.retroPhone) {
            this.retroPhone._toggleCallButtons(true);
        } else if (this.callElements.hangupBtn) {
            this.callElements.hangupBtn.style.display = 'block';
            if (this.callElements.callBtn) this.callElements.callBtn.style.display = 'none';
        }
        if (this.callElements.hangupBtn) {
            this.callElements.hangupBtn.disabled = false;
        }
        if (this.callElements.holdBtn) {
            this.callElements.holdBtn.disabled = false;
        }
        if (call.lead_id && this.leadInfoUrl) {
            this._fetchLeadInfo(call.lead_id);
        } else {
            this._clearLeadCard();
        }
    }

    _setCallDisplay(hasCall) {
        if (this.callElements.placeholder) {
            this.callElements.placeholder.toggleAttribute('hidden', hasCall);
        }
        if (this.callElements.details) {
            this.callElements.details.toggleAttribute('hidden', !hasCall);
        }
    }

    _setCallIdle() {
        this.activeCallId = null;
        this._updateTransferButtonState();
        this._stopDurationTimer();
        if (this.callElements.number) this.callElements.number.textContent = '—';
        this._updateCallStateLabel('idle');
        if (this.callElements.duration) this.callElements.duration.textContent = '00:00';
        if (this.callElements.dispositionBtn) {
            this.callElements.dispositionBtn.disabled = !this.dispositions.length; // Unlock if dispositions exist
        }
        if (this.callElements.hangupBtn) {
            this.callElements.hangupBtn.disabled = true;
        }
        if (this.retroPhone) {
            this.retroPhone._toggleCallButtons(false);
        } else if (this.callElements.hangupBtn) {
            this.callElements.hangupBtn.style.display = 'none';
            if (this.callElements.callBtn) this.callElements.callBtn.style.display = 'block';
        }
        if (this.callElements.holdBtn) {
            this.callElements.holdBtn.disabled = true;
            this.callElements.holdBtn.dataset.state = 'hold-off';
            this.callElements.holdBtn.innerHTML = '<i class="fa-solid fa-pause"></i> Hold';
        }
        this._clearLeadCard();
        this._setCallDisplay(false);
    }

    _updateCallStateLabel(state) {
        if (this.callElements.state) {
            const normalized = state || 'idle';
            this.callElements.state.dataset.state = normalized;
            this.callElements.state.textContent = normalized;
        }
    }

    _startDurationTimer(initialSeconds) {
        this._stopDurationTimer();
        this.durationBase = Date.now() - initialSeconds * 1000;
        if (this.callElements.duration) {
            this.callElements.duration.textContent = this._formatDuration(initialSeconds);
        }
        this.durationTimer = setInterval(() => {
            const elapsed = Math.floor((Date.now() - this.durationBase) / 1000);
            if (this.callElements.duration) {
                this.callElements.duration.textContent = this._formatDuration(elapsed);
            }
        }, 1000);
    }

    _updateCallDuration(seconds) {
        if (this.durationBase) return;
        if (this.callElements.duration) {
            this.callElements.duration.textContent = this._formatDuration(seconds);
        }
    }

    _stopDurationTimer() {
        if (this.durationTimer) {
            clearInterval(this.durationTimer);
            this.durationTimer = null;
            this.durationBase = null;
        }
    }

    _formatDuration(seconds) {
        const mins = Math.floor(seconds / 60)
            .toString()
            .padStart(2, '0');
        const secs = (seconds % 60).toString().padStart(2, '0');
        return `${mins}:${secs}`;
    }

    _fetchLeadInfo(leadId) {
        const url = new URL(this.leadInfoUrl, window.location.origin);
        url.searchParams.set('lead_id', leadId);
        fetch(url, {
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
        })
            .then((res) => res.json())
            .then((res) => {
                if (res.success && res.lead) {
                    this._populateLeadCard(res.lead);
                } else {
                    this._clearLeadCard();
                }
            })
            .catch(() => {
                this._clearLeadCard();
            });
    }

    _populateLeadCard(lead) {
        if (!this.callElements.leadCard) return;
        this.callElements.leadCard.removeAttribute('hidden');
        this.callElements.leadName.textContent = `${lead.first_name || ''} ${lead.last_name || ''}`.trim() || 'Lead';
        this.callElements.leadStatus.textContent = lead.status || 'Unknown';
        this.callElements.leadPhone.textContent = lead.phone_number || '—';
        this.callElements.leadEmail.textContent = lead.email || '—';
        this.callElements.leadCompany.textContent = lead.company || '—';
        const location = [lead.city, lead.state].filter(Boolean).join(', ');
        this.callElements.leadLocation.textContent = location || '—';
    }

    _clearLeadCard() {
        if (!this.callElements.leadCard) return;
        this.callElements.leadCard.setAttribute('hidden', 'hidden');
        ['leadName', 'leadStatus', 'leadPhone', 'leadEmail', 'leadCompany', 'leadLocation'].forEach((key) => {
            if (this.callElements[key]) {
                this.callElements[key].textContent = key === 'leadStatus' ? 'Unknown' : '—';
            }
        });
    }

    _openDispositionModal(callId) {
        if (!this.dispositionModal || !this.dispositions.length) return;
        if (callId) {
            this.pendingDispositionCallId = callId;
        }
        this.isDisposing = true;
        if (this.dispositionCallInput) {
            this.dispositionCallInput.value = callId || this.pendingDispositionCallId || '';
        }
        if (this.dispositionSelect) {
            this.dispositionSelect.value = '';
        }
        if (this.dispositionNotes) {
            this.dispositionNotes.value = '';
        }
        this.dispositionModal.removeAttribute('hidden');
    }

    _closeDispositionModal() {
        if (this.dispositionModal) {
            this.dispositionModal.setAttribute('hidden', 'hidden');
        }
        this.isDisposing = false;
        this.pendingDispositionCallId = null;
    }

    _submitDisposition() {
        if (!this.dispositionUrl || !this.dispositionForm) return;
        const callId =
            this.pendingDispositionCallId ||
            this.dispositionCallInput?.value ||
            this.activeCallId ||
            this.lastCompletedCallId;
        const dispositionId = this.dispositionSelect?.value;
        const notes = this.dispositionNotes?.value || '';
        if (!callId || !dispositionId) {
            this._showToast('Select a disposition before saving', true);
            return;
        }

        // Helper to save disposition
        const saveDisposition = () => {
            const payload = new URLSearchParams();
            payload.append('call_id', callId);
            payload.append('disposition_id', dispositionId);
            payload.append('notes', notes);
            return fetch(this.dispositionUrl, {
                method: 'POST',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRFToken': this.csrfToken,
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: payload.toString(),
            }).then(res => res.json());
        };

        // Helper to hangup backend
        const performHangup = () => {
            if (!this.hangupUrl || !callId) return Promise.resolve({ success: true });
            const payload = new URLSearchParams();
            payload.append('call_id', callId);
            return fetch(this.hangupUrl, {
                method: 'POST',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRFToken': this.csrfToken,
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: payload.toString(),
            }).then(res => res.json()).catch(() => ({ success: true }));
        };

        // Chain: Disposition -> Hangup
        saveDisposition()
            .then((data) => {
                if (!data.success) {
                    throw new Error(data.error || 'Failed to save disposition');
                }
                return performHangup();
            })
            .then(() => {
                this._showToast('Disposition saved');
                this._closeDispositionModal();
                this.pendingDispositionCallId = null;
                this.lastCompletedCallId = null;
                this.isDisposing = false;
                this._setCallIdle();
                this._sendStatus('available');
            })
            .catch((err) => {
                const message = err?.message || 'Network error saving disposition';
                this._showToast(message, true);
                this.isDisposing = false;
            });
    }

    _bindManualDial() {
        if (!this.manualDialForm) return;
        this.manualDialForm.addEventListener('submit', (evt) => {
            evt.preventDefault();
            this._manualDial().catch(() => { });
        });
    }

    _manualDial(numberOverride = null) {
        if (!this.manualDialUrl) {
            this._showToast('Manual dialing disabled', true);
            return Promise.reject(new Error('Manual dialing disabled'));
        }
        const rawInput =
            numberOverride !== null && numberOverride !== undefined
                ? String(numberOverride)
                : (this.manualDialInput?.value || '').trim();
        const sanitized = rawInput.replace(/[^\d\+\#\*]/g, '');
        if (!sanitized) {
            this._showToast('Enter a phone number', true);
            return Promise.reject(new Error('Invalid number'));
        }
        const payload = new URLSearchParams();
        payload.append('phone_number', sanitized);
        if (this.manualDialCampaign) {
            payload.append('campaign_id', this.manualDialCampaign.value || '');
        }
        this._setManualDialLoading(true);
        return fetch(this.manualDialUrl, {
            method: 'POST',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
                'X-CSRFToken': this.csrfToken,
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: payload.toString(),
        })
            .then((res) => res.json())
            .then((data) => {
                if (data.success && (!numberOverride && this.manualDialInput)) {
                    this.manualDialInput.value = '';
                }
                if (data.success) {
                    if (data.call_id) {
                        this.activeCallId = data.call_id;
                    }
                    if (!numberOverride) {
                        this._showToast(data.message || 'Dial requested');
                    }
                } else {
                    this._showToast(data.error || 'Dial failed', true);
                    if (data.call_id) {
                        this.lastCompletedCallId = data.call_id;
                        if (this.callElements.dispositionBtn) {
                            this.callElements.dispositionBtn.disabled = false;
                        }
                        this._openDispositionModal(data.call_id);
                    }
                }
                return data;
            })
            .catch(() => {
                this._showToast('Network error requesting dial', true);
                throw new Error('Network error');
            })
            .finally(() => this._setManualDialLoading(false));
    }

    _setManualDialLoading(isLoading) {
        if (this.manualDialButton) {
            this.manualDialLoading = isLoading;
            this.manualDialButton.disabled = isLoading || (this.manualDialDisabledByRegistration ?? false);
            this.manualDialButton.textContent = isLoading ? 'Dialing…' : 'Dial Now';
        }
    }

    _bindTransferForm() {
        if (!this.transferForm || !this.transferButton) return;
        this.transferForm.addEventListener('submit', (evt) => {
            evt.preventDefault();
            this._submitTransfer();
        });
        if (this.transferSelect) {
            this.transferSelect.addEventListener('change', () => this._updateTransferButtonState());
        }
        this._updateTransferButtonState();
    }

    _updateTransferButtonState() {
        if (!this.transferButton) return;
        const hasTarget = !!(this.transferSelect && this.transferSelect.value);
        const hasCall = !!this.activeCallId;
        const disabled = !hasTarget || !hasCall || this.transferLoading;
        this.transferButton.disabled = disabled;
    }

    _setTransferLoading(isLoading) {
        if (!this.transferButton) return;
        this.transferLoading = isLoading;
        if (isLoading) {
            this.transferButton.textContent = 'Transferring…';
        } else if (this.transferButtonLabel) {
            this.transferButton.textContent = this.transferButtonLabel;
        }
        this._updateTransferButtonState();
    }

    _submitTransfer() {
        if (!this.transferUrl) {
            this._showToast('Transfer unavailable', true);
            return;
        }
        if (!this.activeCallId) {
            this._showToast('No active call to transfer', true);
            return;
        }
        const transferTo = this.transferSelect?.value;
        if (!transferTo) {
            this._showToast('Select an agent to transfer to', true);
            return;
        }
        this._setTransferLoading(true);
        const payload = new URLSearchParams();
        payload.append('call_id', this.activeCallId);
        payload.append('transfer_to', transferTo);
        payload.append('transfer_type', 'warm');
        fetch(this.transferUrl, {
            method: 'POST',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
                'X-CSRFToken': this.csrfToken,
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: payload.toString(),
        })
            .then((res) => res.json())
            .then((data) => {
                if (data.success) {
                    this._showToast(data.message || 'Transfer initiated');
                } else {
                    this._showToast(data.error || 'Transfer failed', true);
                }
            })
            .catch(() => this._showToast('Network error transferring call', true))
            .finally(() => this._setTransferLoading(false));
    }

    _updatePhoneRegistration(isRegistered) {
        this.lastKnownSoftphoneRegistered = !!isRegistered;
        if (this.retroPhone && typeof this.retroPhone.setSoftphoneRegistration === 'function') {
            this.retroPhone.setSoftphoneRegistration(this.lastKnownSoftphoneRegistered);
        }
        this._applyRegistrationState();
    }

    _applyRegistrationState() {
        const registered = !!this.lastKnownSoftphoneRegistered;
        const webRtcReady = typeof this.retroPhone?.hasActiveWebRTC === 'function'
            ? this.retroPhone.hasActiveWebRTC()
            : false;
        const effectiveRegistered = registered || webRtcReady;
        if (this.phoneStatusEl) {
            this.phoneStatusEl.dataset.registered = effectiveRegistered ? 'true' : 'false';
            if (effectiveRegistered) {
                this.phoneStatusEl.textContent = webRtcReady
                    ? 'WebRTC registered'
                    : 'Softphone registered';
            } else {
                this.phoneStatusEl.textContent = 'Not registered — open your softphone client';
            }
        }
        if (this.manualDialButton) {
            this.manualDialDisabledByRegistration = !effectiveRegistered;
            if (!this.manualDialLoading) {
                this.manualDialButton.disabled = !effectiveRegistered;
            }
        }
        this._updateTransferButtonState();
    }

    _requestHangup() {
        if (!this.hangupUrl || !this.activeCallId) {
            this._setCallIdle();
            return;
        }
        const callId = this.activeCallId;

        // Terminate WebRTC if active (UI update handled by RetroPhone events)
        if (this.retroPhone && this.retroPhone.currentSession) {
            try {
                this.retroPhone.currentSession.terminate();
            } catch (e) { console.warn(e); }
        }

        // Always notify backend to clear the call, then open disposition locally
        const payload = new URLSearchParams();
        payload.append('call_id', callId);
        fetch(this.hangupUrl, {
            method: 'POST',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
                'X-CSRFToken': this.csrfToken,
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: payload.toString(),
        })
            .catch(() => ({}))
            .finally(() => {
                this._setCallIdle();
                if (this.dispositions.length) {
                    this.isDisposing = true;
                    this.pendingDispositionCallId = callId;
                    this.lastCompletedCallId = callId;
                    this._openDispositionModal(callId);
                } else {
                    this.lastCompletedCallId = null;
                }
            });
    }

    _initRealtimeChannel() {
        if (!this.agentId) return;
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/agent/${this.agentId}/`;
        try {
            this.realtimeSocket = new WebSocket(wsUrl);
        } catch (err) {
            console.warn('Failed to open realtime socket', err);
            return;
        }
        this.realtimeSocket.onmessage = (evt) => {
            try {
                const payload = JSON.parse(evt.data);
                this._handleRealtimeEvent(payload);
            } catch (e) {
                console.warn('Invalid realtime payload', e);
            }
        };
        this.realtimeSocket.onclose = () => {
            setTimeout(() => this._initRealtimeChannel(), 5000);
        };
    }

    _handleRealtimeEvent(payload) {
        const type = payload.type || '';

        if (type === 'call_started' && payload.call) {
            this._applyCallState(payload.call);
            return;
        }

        if (type === 'call_connected') {
            if (payload.call) {
                this._applyCallState(payload.call);
            }
            if (payload.lead) {
                this._populateLeadCard(payload.lead);
            }
            return;
        }

        if (type === 'call_ended') {
            const completedCallId = payload.call_id || this.activeCallId;
            this._setCallIdle();
            if (completedCallId && this.dispositions.length) {
                this.lastCompletedCallId = completedCallId;
                if (payload.disposition_needed !== false) {
                    this._openDispositionModal(completedCallId);
                }
            }
            return;
        }

        if (type === 'call_update' && payload.call) {
            this._applyCallState(payload.call);
            return;
        }

        if (type === 'status_update') {
            if (payload.status) {
                this._updateStatusUI(payload.status, payload.message);
                this.currentStatus = payload.status;
            }
            return;
        }

        if (type === 'registration' && typeof payload.registered !== 'undefined') {
            this._updatePhoneRegistration(payload.registered);
        }
    }

    _initRetroPhone(initialRegistered) {
        const retroPhone = document.querySelector('[data-retro-phone]');
        if (!retroPhone) return;
        this.retroPhone = new RetroPhoneController(retroPhone, {
            manualDialHandler: (number) => this._manualDial(number),
            toast: (message, isError) => this._showToast(message, isError),
            webrtcEnabled: this.webrtcEnabled,
            webrtcConfig: this.webrtcConfig,
            softphoneRegistered: initialRegistered,
            onRegistrationChange: () => this._applyRegistrationState(),
            onHangup: () => this._requestHangup(),
        });

        // Sync state if we have an active call
        if (this.activeCallId) {
            this.retroPhone._toggleCallButtons(true);
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const root = document.querySelector('[data-agent-dashboard]');
    if (root) {
        window.AgentDashboardUI = new AgentDashboardUI(root);
    }
});
