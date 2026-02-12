/**
 * WebRTC Phone Class - Phase 3.1
 * 
 * Browser-based SIP phone using JsSIP library.
 * Handles registration, calling, and audio management.
 * 
 * Dependencies:
 * - JsSIP (https://jssip.net/) - Include via CDN or npm
 * 
 * Usage:
 *   const phone = new WebRTCPhone(config);
 *   phone.register();
 *   phone.call('1001');
 */

class WebRTCPhone {
    constructor(config) {
        this.config = {
            wsServer: config.wsServer || 'wss://asterisk.example.com:8089/ws',
            sipUri: config.sipUri || 'sip:1001@asterisk.example.com',
            password: config.password || '',
            displayName: config.displayName || 'Agent',
            stunServers: config.stunServers || ['stun:stun.l.google.com:19302'],
            debug: config.debug || false,
            autoAnswer: config.autoAnswer || false,
            ringtonePath: config.ringtonePath || '/static/sounds/ringtone.mp3',
            ...config
        };

        // State
        this.ua = null;
        this.currentSession = null;
        this.isRegistered = false;
        this.isMuted = false;
        this.isHeld = false;
        this.callStartTime = null;
        this.durationTimer = null;

        // Audio elements
        this.localAudio = null;
        this.remoteAudio = null;
        this.ringtoneAudio = null;

        // Callbacks
        this.onRegistered = config.onRegistered || (() => {});
        this.onUnregistered = config.onUnregistered || (() => {});
        this.onRegistrationFailed = config.onRegistrationFailed || (() => {});
        this.onIncomingCall = config.onIncomingCall || (() => {});
        this.onOutgoingCall = config.onOutgoingCall || (() => {});
        this.onCallConnected = config.onCallConnected || (() => {});
        this.onCallEnded = config.onCallEnded || (() => {});
        this.onCallFailed = config.onCallFailed || (() => {});
        this.onDTMF = config.onDTMF || (() => {});
        this.onError = config.onError || ((error) => console.error('WebRTC Error:', error));

        this._initAudioElements();
    }

    /**
     * Initialize audio elements for media playback
     */
    _initAudioElements() {
        // Remote audio (caller's voice)
        this.remoteAudio = document.getElementById('remoteAudio');
        if (!this.remoteAudio) {
            this.remoteAudio = document.createElement('audio');
            this.remoteAudio.id = 'remoteAudio';
            this.remoteAudio.autoplay = true;
            document.body.appendChild(this.remoteAudio);
        }

        // Local audio (for echo testing, usually not played)
        this.localAudio = document.getElementById('localAudio');
        if (!this.localAudio) {
            this.localAudio = document.createElement('audio');
            this.localAudio.id = 'localAudio';
            this.localAudio.muted = true;
            document.body.appendChild(this.localAudio);
        }

        // Ringtone
        this.ringtoneAudio = document.getElementById('ringtoneAudio');
        if (!this.ringtoneAudio) {
            this.ringtoneAudio = document.createElement('audio');
            this.ringtoneAudio.id = 'ringtoneAudio';
            this.ringtoneAudio.loop = true;
            this.ringtoneAudio.src = this.config.ringtonePath;
            document.body.appendChild(this.ringtoneAudio);
        }
    }

    /**
     * Initialize and register with SIP server
     */
    register() {
        if (typeof JsSIP === 'undefined') {
            this.onError(new Error('JsSIP library not loaded'));
            return false;
        }

        try {
            // Configure JsSIP
            const socket = new JsSIP.WebSocketInterface(this.config.wsServer);

            const configuration = {
                sockets: [socket],
                uri: this.config.sipUri,
                password: this.config.password,
                display_name: this.config.displayName,
                register: true,
                session_timers: false,
                use_preloaded_route: false,
            };

            // Create User Agent
            this.ua = new JsSIP.UA(configuration);

            // Set up event handlers
            this._setupEventHandlers();

            // Enable debug if configured
            if (this.config.debug) {
                JsSIP.debug.enable('JsSIP:*');
            }

            // Start the UA
            this.ua.start();

            console.log('WebRTC Phone: Starting registration...');
            return true;

        } catch (error) {
            this.onError(error);
            return false;
        }
    }

    /**
     * Unregister from SIP server
     */
    unregister() {
        if (this.ua) {
            this.ua.unregister();
            this.ua.stop();
            this.isRegistered = false;
        }
    }

    /**
     * Set up JsSIP event handlers
     */
    _setupEventHandlers() {
        // Registration events
        this.ua.on('registered', (e) => {
            console.log('WebRTC Phone: Registered');
            this.isRegistered = true;
            this.onRegistered(e);
        });

        this.ua.on('unregistered', (e) => {
            console.log('WebRTC Phone: Unregistered');
            this.isRegistered = false;
            this.onUnregistered(e);
        });

        this.ua.on('registrationFailed', (e) => {
            console.error('WebRTC Phone: Registration failed', e.cause);
            this.isRegistered = false;
            this.onRegistrationFailed(e);
        });

        // Incoming call
        this.ua.on('newRTCSession', (e) => {
            const session = e.session;

            if (session.direction === 'incoming') {
                this._handleIncomingCall(session);
            }
        });

        // Connection events
        this.ua.on('connected', () => {
            console.log('WebRTC Phone: WebSocket connected');
        });

        this.ua.on('disconnected', () => {
            console.log('WebRTC Phone: WebSocket disconnected');
        });
    }

    /**
     * Handle incoming call
     */
    _handleIncomingCall(session) {
        console.log('WebRTC Phone: Incoming call from', session.remote_identity.uri.user);

        // Store session
        this.currentSession = session;

        // Play ringtone
        this._playRingtone();

        // Set up session handlers
        this._setupSessionHandlers(session);

        // Get caller info
        const callerInfo = {
            number: session.remote_identity.uri.user,
            displayName: session.remote_identity.display_name || session.remote_identity.uri.user,
            session: session
        };

        // Auto-answer if configured
        if (this.config.autoAnswer) {
            setTimeout(() => this.answer(), 500);
        }

        this.onIncomingCall(callerInfo);
    }

    /**
     * Make an outgoing call
     */
    call(number, options = {}) {
        if (!this.isRegistered) {
            this.onError(new Error('Not registered'));
            return false;
        }

        if (this.currentSession) {
            this.onError(new Error('Already in a call'));
            return false;
        }

        try {
            const callOptions = {
                mediaConstraints: {
                    audio: true,
                    video: false
                },
                pcConfig: {
                    iceServers: this.config.stunServers.map(server => ({ urls: server }))
                },
                ...options
            };

            // Make the call
            this.currentSession = this.ua.call(`sip:${number}@${this._getDomain()}`, callOptions);

            // Set up session handlers
            this._setupSessionHandlers(this.currentSession);

            console.log('WebRTC Phone: Calling', number);

            this.onOutgoingCall({
                number: number,
                session: this.currentSession
            });

            return true;

        } catch (error) {
            this.onError(error);
            return false;
        }
    }

    /**
     * Answer incoming call
     */
    answer() {
        if (!this.currentSession) {
            this.onError(new Error('No incoming call to answer'));
            return false;
        }

        try {
            this._stopRingtone();

            const answerOptions = {
                mediaConstraints: {
                    audio: true,
                    video: false
                },
                pcConfig: {
                    iceServers: this.config.stunServers.map(server => ({ urls: server }))
                }
            };

            this.currentSession.answer(answerOptions);
            console.log('WebRTC Phone: Answered call');
            return true;

        } catch (error) {
            this.onError(error);
            return false;
        }
    }

    /**
     * Hangup current call
     */
    hangup() {
        if (!this.currentSession) {
            return false;
        }

        try {
            this._stopRingtone();
            this.currentSession.terminate();
            console.log('WebRTC Phone: Hangup');
            return true;

        } catch (error) {
            this.onError(error);
            return false;
        }
    }

    /**
     * Reject incoming call
     */
    reject() {
        if (!this.currentSession) {
            return false;
        }

        try {
            this._stopRingtone();
            this.currentSession.terminate({
                status_code: 486,
                reason_phrase: 'Busy Here'
            });
            return true;

        } catch (error) {
            this.onError(error);
            return false;
        }
    }

    /**
     * Send DTMF tone
     */
    sendDTMF(tone) {
        if (!this.currentSession) {
            return false;
        }

        try {
            this.currentSession.sendDTMF(tone);
            console.log('WebRTC Phone: Sent DTMF', tone);
            this.onDTMF(tone);
            return true;

        } catch (error) {
            this.onError(error);
            return false;
        }
    }

    /**
     * Mute/unmute microphone
     */
    toggleMute() {
        if (!this.currentSession) {
            return false;
        }

        try {
            if (this.isMuted) {
                this.currentSession.unmute({ audio: true });
                this.isMuted = false;
            } else {
                this.currentSession.mute({ audio: true });
                this.isMuted = true;
            }
            console.log('WebRTC Phone: Mute', this.isMuted);
            return this.isMuted;

        } catch (error) {
            this.onError(error);
            return this.isMuted;
        }
    }

    /**
     * Hold/unhold call
     */
    toggleHold() {
        if (!this.currentSession) {
            return false;
        }

        try {
            if (this.isHeld) {
                this.currentSession.unhold();
                this.isHeld = false;
            } else {
                this.currentSession.hold();
                this.isHeld = true;
            }
            console.log('WebRTC Phone: Hold', this.isHeld);
            return this.isHeld;

        } catch (error) {
            this.onError(error);
            return this.isHeld;
        }
    }

    /**
     * Transfer call (blind transfer)
     */
    transfer(target) {
        if (!this.currentSession) {
            return false;
        }

        try {
            this.currentSession.refer(`sip:${target}@${this._getDomain()}`);
            console.log('WebRTC Phone: Transferring to', target);
            return true;

        } catch (error) {
            this.onError(error);
            return false;
        }
    }

    /**
     * Set up session event handlers
     */
    _setupSessionHandlers(session) {
        // Call progress
        session.on('progress', (e) => {
            console.log('WebRTC Phone: Call progress');
        });

        // Call confirmed (connected)
        session.on('confirmed', (e) => {
            console.log('WebRTC Phone: Call confirmed');
            this._stopRingtone();
            this.callStartTime = new Date();
            this._startDurationTimer();
            this.onCallConnected({
                session: session,
                startTime: this.callStartTime
            });
        });

        // Call ended
        session.on('ended', (e) => {
            console.log('WebRTC Phone: Call ended', e.cause);
            this._handleCallEnded(e);
        });

        // Call failed
        session.on('failed', (e) => {
            console.log('WebRTC Phone: Call failed', e.cause);
            this._handleCallEnded(e, true);
        });

        // Handle media (audio stream)
        session.on('peerconnection', (e) => {
            const peerconnection = e.peerconnection;

            peerconnection.ontrack = (event) => {
                console.log('WebRTC Phone: Received remote track');
                this.remoteAudio.srcObject = event.streams[0];
            };
        });

        // ICE connection state
        session.on('icecandidate', (e) => {
            if (e.candidate) {
                console.log('WebRTC Phone: ICE candidate', e.candidate.candidate);
            }
        });
    }

    /**
     * Handle call ended
     */
    _handleCallEnded(event, failed = false) {
        this._stopRingtone();
        this._stopDurationTimer();

        const duration = this.callStartTime
            ? Math.floor((new Date() - this.callStartTime) / 1000)
            : 0;

        const callInfo = {
            cause: event.cause,
            duration: duration,
            startTime: this.callStartTime,
            endTime: new Date()
        };

        // Reset state
        this.currentSession = null;
        this.callStartTime = null;
        this.isMuted = false;
        this.isHeld = false;

        // Stop audio
        if (this.remoteAudio.srcObject) {
            this.remoteAudio.srcObject.getTracks().forEach(track => track.stop());
            this.remoteAudio.srcObject = null;
        }

        if (failed) {
            this.onCallFailed(callInfo);
        } else {
            this.onCallEnded(callInfo);
        }
    }

    /**
     * Play ringtone
     */
    _playRingtone() {
        try {
            this.ringtoneAudio.play().catch(e => {
                console.log('Cannot play ringtone:', e);
            });
        } catch (e) {
            console.log('Ringtone error:', e);
        }
    }

    /**
     * Stop ringtone
     */
    _stopRingtone() {
        try {
            this.ringtoneAudio.pause();
            this.ringtoneAudio.currentTime = 0;
        } catch (e) {
            // Ignore
        }
    }

    /**
     * Start duration timer
     */
    _startDurationTimer() {
        this.durationTimer = setInterval(() => {
            if (this.callStartTime) {
                const duration = Math.floor((new Date() - this.callStartTime) / 1000);
                document.dispatchEvent(new CustomEvent('webrtc-duration', {
                    detail: { duration: duration }
                }));
            }
        }, 1000);
    }

    /**
     * Stop duration timer
     */
    _stopDurationTimer() {
        if (this.durationTimer) {
            clearInterval(this.durationTimer);
            this.durationTimer = null;
        }
    }

    /**
     * Get domain from SIP URI
     */
    _getDomain() {
        const match = this.config.sipUri.match(/@(.+)$/);
        return match ? match[1] : 'localhost';
    }

    /**
     * Get current call duration in seconds
     */
    getCallDuration() {
        if (!this.callStartTime) return 0;
        return Math.floor((new Date() - this.callStartTime) / 1000);
    }

    /**
     * Get registration status
     */
    getStatus() {
        return {
            registered: this.isRegistered,
            inCall: !!this.currentSession,
            muted: this.isMuted,
            held: this.isHeld,
            duration: this.getCallDuration()
        };
    }

    /**
     * Format duration as HH:MM:SS
     */
    static formatDuration(seconds) {
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        const s = seconds % 60;

        if (h > 0) {
            return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
        }
        return `${m}:${String(s).padStart(2, '0')}`;
    }
}

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = WebRTCPhone;
}
