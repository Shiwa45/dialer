/**
 * Enhanced Agent Panel JavaScript with Real-time Updates
 * 
 * This script provides comprehensive real-time functionality for the agent panel:
 * - WebSocket connection management with auto-reconnect
 * - Real-time call events and status updates
 * - Automatic disposition modal display
 * - Enhanced error handling and user feedback
 */

class EnhancedAgentPanel {
    constructor() {
        this.websocket = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 2000;
        this.heartbeatInterval = null;
        this.currentCall = null;
        this.isConnected = false;

        this.init();
    }

    init() {
        console.log('🚀 Initializing Enhanced Agent Panel...');

        // Initialize WebSocket connection
        this.connectWebSocket();

        // Setup UI event listeners
        this.setupUIEventListeners();

        // Setup periodic status refresh
        this.setupStatusRefresh();

        // Setup disposition modal
        this.setupDispositionModal();

        // Setup status update handlers
        this.setupStatusHandlers();

        console.log('✅ Agent Panel initialized successfully');
    }

    connectWebSocket() {
        if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
            return;
        }

        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        // Expect a global AGENT_ID (injected by template) for per-agent channel
        const agentId = window.AGENT_ID || window.agentId || null;
        const wsPath = agentId ? `/ws/agent/${agentId}/` : '/ws/agent/';
        const wsUrl = `${protocol}//${window.location.host}${wsPath}`;

        console.log('🔌 Connecting to WebSocket:', wsUrl);

        try {
            this.websocket = new WebSocket(wsUrl);
            this.setupWebSocketHandlers();
        } catch (error) {
            console.error('❌ WebSocket connection failed:', error);
            this.scheduleReconnect();
        }
    }

    setupWebSocketHandlers() {
        this.websocket.onopen = (event) => {
            console.log('✅ WebSocket connected successfully');
            this.isConnected = true;
            this.reconnectAttempts = 0;
            this.updateConnectionStatus('connected');
            this.startHeartbeat();

            this.sendMessage({
                type: 'request_initial_status'
            });
        };

        this.websocket.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.handleWebSocketMessage(data);
            } catch (error) {
                console.error('❌ Failed to parse WebSocket message:', error);
            }
        };

        this.websocket.onclose = (event) => {
            console.log('🔌 WebSocket connection closed:', event.code);
            this.isConnected = false;
            this.updateConnectionStatus('disconnected');
            this.stopHeartbeat();

            if (event.code !== 1000) {
                this.scheduleReconnect();
            }
        };

        this.websocket.onerror = (error) => {
            console.error('❌ WebSocket error:', error);
            this.updateConnectionStatus('error');
        };
    }

    handleWebSocketMessage(data) {
        console.log('📨 Received message:', data.type, data);

        switch (data.type) {
            case 'connection_established':
                this.handleConnectionEstablished(data);
                break;
            case 'call_connected':
                this.handleCallConnected(data);
                break;
            case 'call_ended':
                this.handleCallEnded(data);
                break;
            case 'status_update':
                this.handleStatusUpdate(data);
                break;
            case 'disposition_completed':
                this.handleDispositionCompleted(data);
                break;
            case 'call_answered':
                this.handleCallAnswered(data);
                break;
            case 'error':
                this.handleError(data);
                break;
        }
    }

    handleConnectionEstablished(data) {
        console.log('🎉 Agent panel connected:', data.username);

        if (data.initial_data) {
            this.updateAgentStatus(data.initial_data.status);
            this.updateCurrentCampaign(data.initial_data.current_campaign);
        }

        this.showNotification('success', 'Connected to dialer system');
    }

    handleCallConnected(data) {
        console.log('📞 Call connected:', data.call);

        this.currentCall = data.call;

        this.updateCallDisplay({
            number: data.call.number,
            status: 'Connected',
            startTime: data.call.start_time || new Date().toISOString(),
            callId: data.call.id
        });

        if (data.lead) {
            this.showLeadInformation(data.lead);
        }

        this.updateAgentStatus('on_call');
        this.startCallTimer(data.call.start_time);
        this.showNotification('info', `Call connected: ${data.call.number}`);
    }

    handleCallEnded(data) {
        console.log('📴 Call ended:', data.call_id);

        this.stopCallTimer();

        if (data.disposition_required) {
            setTimeout(() => {
                this.showDispositionModal(data.call_id, this.currentCall);
            }, 500);
        }

        this.updateCallDisplay({
            number: this.currentCall?.number || '',
            status: 'Call Ended',
            duration: data.talk_duration || 0
        });

        this.updateAgentStatus('wrapup');
        this.showNotification('info', 'Call ended - Please dispose');

        setTimeout(() => {
            this.clearCallDisplay();
            this.currentCall = null;
        }, 2000);
    }

    handleStatusUpdate(data) {
        console.log('📊 Status update:', data);

        if (data.new_status) {
            this.updateAgentStatus(data.new_status);
        }

        if (data.message) {
            this.showNotification('info', data.message);
        }
    }

    handleDispositionCompleted(data) {
        console.log('✅ Disposition completed:', data);

        this.closeDispositionModal();
        this.updateAgentStatus(data.new_status);
        this.showNotification('success', 'Call disposition completed');
        this.clearCallDisplay();
        this.currentCall = null;
    }

    handleError(data) {
        console.error('❌ Server error:', data.message);
        this.showNotification('error', data.message);
    }

    // UI Update Methods
    updateCallDisplay(callData) {
        const callPanel = document.getElementById('callPanel');
        const callNumber = document.getElementById('callNumber');
        const callStatus = document.getElementById('callStatus');

        if (callPanel) {
            callPanel.style.display = callData.number ? 'block' : 'none';
        }

        if (callNumber) {
            callNumber.textContent = callData.number || '';
        }

        if (callStatus) {
            callStatus.textContent = callData.status || '';
            callStatus.className = 'call-status';

            if (callData.status === 'Connected' || callData.status === 'In Progress') {
                callStatus.classList.add('status-active');
            } else if (callData.status === 'Call Ended') {
                callStatus.classList.add('status-ended');
            }
        }
    }

    clearCallDisplay() {
        const callPanel = document.getElementById('callPanel');
        if (callPanel) {
            callPanel.style.display = 'none';
        }
        this.stopCallTimer();
    }

    updateAgentStatus(status) {
        const statusElement = document.getElementById('agentStatus');
        const statusIndicator = document.getElementById('statusIndicator');

        if (statusElement) {
            statusElement.textContent = status.charAt(0).toUpperCase() + status.slice(1);
        }

        if (statusIndicator) {
            statusIndicator.className = 'status-indicator';

            switch (status) {
                case 'available':
                case 'ready':
                    statusIndicator.classList.add('status-available');
                    break;
                case 'on_call':
                    statusIndicator.classList.add('status-busy');
                    break;
                case 'wrapup':
                    statusIndicator.classList.add('status-wrapup');
                    break;
                case 'break':
                case 'lunch':
                    statusIndicator.classList.add('status-break');
                    break;
                default:
                    statusIndicator.classList.add('status-offline');
            }
        }
    }

    updateCurrentCampaign(campaignName) {
        const campaignElement = document.getElementById('currentCampaign');
        if (campaignElement) {
            campaignElement.textContent = campaignName || 'No Campaign';
        }
    }

    updateConnectionStatus(status) {
        const connectionElement = document.getElementById('connectionStatus');
        if (connectionElement) {
            connectionElement.className = `connection-status status-${status}`;
            connectionElement.textContent = status.charAt(0).toUpperCase() + status.slice(1);
        }
    }

    // Lead Information Display
    showLeadInformation(lead) {
        console.log('👤 Showing lead information:', lead);

        const leadPanel = document.getElementById('leadPanel');
        if (leadPanel) {
            leadPanel.style.display = 'block';

            this.updateLeadField('leadName', `${lead.first_name || ''} ${lead.last_name || ''}`.trim());
            this.updateLeadField('leadPhone', lead.phone_number);
            this.updateLeadField('leadEmail', lead.email);
            this.updateLeadField('leadCompany', lead.company);
            this.updateLeadField('leadAddress', this.formatAddress(lead));
            this.updateLeadField('leadNotes', lead.notes);
            this.updateLeadField('leadStatus', lead.status);
            this.updateLeadField('leadCallCount', lead.call_count);
        }
    }

    updateLeadField(elementId, value) {
        const element = document.getElementById(elementId);
        if (element) {
            element.textContent = value || 'N/A';
        }
    }

    formatAddress(lead) {
        const parts = [lead.address, lead.city, lead.state, lead.zip_code];
        return parts.filter(p => p && p.trim()).join(', ');
    }

    // Call Timer
    startCallTimer(startTime) {
        this.stopCallTimer();

        const timerElement = document.getElementById('callTimer');
        if (!timerElement) return;

        const start = startTime ? new Date(startTime) : new Date();

        this.callTimerInterval = setInterval(() => {
            const now = new Date();
            const diff = Math.floor((now - start) / 1000);

            const minutes = Math.floor(diff / 60);
            const seconds = diff % 60;

            timerElement.textContent = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
        }, 1000);
    }

    stopCallTimer() {
        if (this.callTimerInterval) {
            clearInterval(this.callTimerInterval);
            this.callTimerInterval = null;
        }
    }

    // Disposition Modal
    setupDispositionModal() {
        if (!document.getElementById('dispositionModal')) {
            this.createDispositionModal();
        }

        const form = document.getElementById('dispositionForm');
        if (form) {
            form.addEventListener('submit', (e) => {
                e.preventDefault();
                this.submitDisposition();
            });
        }
    }

    createDispositionModal() {
        const modalHTML = `
            <div class="modal fade" id="dispositionModal" tabindex="-1" data-bs-backdrop="static">
                <div class="modal-dialog modal-lg">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title">Call Disposition</h5>
                        </div>
                        <div class="modal-body">
                            <form id="dispositionForm">
                                <div class="row mb-3">
                                    <div class="col-md-6">
                                        <label class="form-label">Call Number:</label>
                                        <span id="dispCallNumber" class="form-text"></span>
                                    </div>
                                    <div class="col-md-6">
                                        <label class="form-label">Call Duration:</label>
                                        <span id="dispCallDuration" class="form-text"></span>
                                    </div>
                                </div>
                                
                                <div class="mb-3">
                                    <label for="dispositionSelect" class="form-label">Disposition <span class="text-danger">*</span></label>
                                    <select class="form-select" id="dispositionSelect" required>
                                        <option value="">Select disposition...</option>
                                    </select>
                                </div>
                                
                                <div class="mb-3">
                                    <label for="agentNotes" class="form-label">Notes</label>
                                    <textarea class="form-control" id="agentNotes" rows="3"></textarea>
                                </div>
                                
                                <div id="callbackSection" class="mb-3" style="display: none;">
                                    <label for="callbackDate" class="form-label">Callback Date & Time</label>
                                    <input type="datetime-local" class="form-control" id="callbackDate">
                                </div>
                                
                                <input type="hidden" id="modalCallId">
                            </form>
                        </div>
                        <div class="modal-footer">
                            <button type="submit" form="dispositionForm" class="btn btn-primary">Submit Disposition</button>
                        </div>
                    </div>
                </div>
            </div>
        `;

        document.body.insertAdjacentHTML('beforeend', modalHTML);
    }

    async showDispositionModal(callId, callData) {
        const modal = document.getElementById('dispositionModal');
        if (!modal) return;

        document.getElementById('modalCallId').value = callId;
        document.getElementById('dispCallNumber').textContent = callData?.number || '';
        document.getElementById('dispCallDuration').textContent = this.formatDuration(callData?.duration || 0);

        await this.loadDispositions();

        const bsModal = new bootstrap.Modal(modal);
        bsModal.show();

        const dispositionSelect = document.getElementById('dispositionSelect');
        dispositionSelect.addEventListener('change', this.handleDispositionChange.bind(this));
    }

    closeDispositionModal() {
        const modal = document.getElementById('dispositionModal');
        if (modal) {
            const bsModal = bootstrap.Modal.getInstance(modal);
            if (bsModal) {
                bsModal.hide();
            }
        }
    }

    async loadDispositions() {
        try {
            const response = await fetch('/agents/api/dispositions/');
            const data = await response.json();

            if (data.success) {
                const select = document.getElementById('dispositionSelect');
                select.innerHTML = '<option value="">Select disposition...</option>';

                data.dispositions.forEach(disp => {
                    const option = document.createElement('option');
                    option.value = disp.id;
                    option.textContent = disp.name;
                    option.dataset.callback = disp.schedule_callback;
                    select.appendChild(option);
                });
            }
        } catch (error) {
            console.error('Error loading dispositions:', error);
        }
    }

    handleDispositionChange(e) {
        const selectedOption = e.target.selectedOptions[0];
        const callbackSection = document.getElementById('callbackSection');

        if (selectedOption && selectedOption.dataset.callback === 'true') {
            callbackSection.style.display = 'block';

            const tomorrow = new Date();
            tomorrow.setDate(tomorrow.getDate() + 1);
            tomorrow.setHours(9, 0, 0, 0);

            document.getElementById('callbackDate').value = tomorrow.toISOString().slice(0, 16);
        } else {
            callbackSection.style.display = 'none';
        }
    }

    async submitDisposition() {
        const callId = document.getElementById('modalCallId').value;
        const dispositionId = document.getElementById('dispositionSelect').value;
        const notes = document.getElementById('agentNotes').value;
        const callbackDate = document.getElementById('callbackDate').value;

        if (!dispositionId) {
            this.showNotification('error', 'Please select a disposition');
            return;
        }

        try {
            const payload = {
                call_id: callId,
                disposition_id: dispositionId,
                notes: notes
            };

            if (callbackDate) {
                payload.call_back_date = new Date(callbackDate).toISOString();
            }

            const response = await fetch('/agents/api/submit-disposition/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                body: JSON.stringify(payload)
            });

            const data = await response.json();

            if (data.success) {
                this.showNotification('success', data.message);
                this.closeDispositionModal();
            } else {
                this.showNotification('error', data.error);
            }

        } catch (error) {
            console.error('Error submitting disposition:', error);
            this.showNotification('error', 'Failed to submit disposition');
        }
    }

    // Status Handlers
    setupStatusHandlers() {
        document.querySelectorAll('[data-status]').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const newStatus = e.target.dataset.status;
                this.changeAgentStatus(newStatus);
            });
        });
    }

    async changeAgentStatus(newStatus, reason = null) {
        try {
            const payload = { status: newStatus };
            if (reason) payload.reason = reason;

            const response = await fetch('/agents/api/update-status/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                body: JSON.stringify(payload)
            });

            const data = await response.json();

            if (data.success) {
                this.showNotification('success', data.message);
            } else {
                this.showNotification('error', data.error);
            }

        } catch (error) {
            console.error('Error changing status:', error);
            this.showNotification('error', 'Failed to update status');
        }
    }

    // UI Event Listeners
    setupUIEventListeners() {
        const dialBtn = document.getElementById('manualDialBtn');
        if (dialBtn) {
            dialBtn.addEventListener('click', () => {
                const number = document.getElementById('dialNumber').value;
                if (number) this.makeManualCall(number);
            });
        }

        const hangupBtn = document.getElementById('hangupBtn');
        if (hangupBtn) {
            hangupBtn.addEventListener('click', () => this.hangupCall());
        }

        const dialInput = document.getElementById('dialNumber');
        if (dialInput) {
            dialInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    this.makeManualCall(dialInput.value);
                }
            });
        }
    }

    async makeManualCall(number) {
        if (!number.trim()) {
            this.showNotification('error', 'Please enter a phone number');
            return;
        }

        try {
            const response = await fetch('/agents/api/make-call/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                body: JSON.stringify({ phone_number: number })
            });

            const data = await response.json();

            if (data.success) {
                this.showNotification('success', `Calling ${number}...`);
                document.getElementById('dialNumber').value = '';
            } else {
                this.showNotification('error', data.error);
            }

        } catch (error) {
            console.error('Error making call:', error);
            this.showNotification('error', 'Failed to make call');
        }
    }

    async hangupCall() {
        if (!this.currentCall) {
            this.showNotification('warning', 'No active call to hangup');
            return;
        }

        try {
            const response = await fetch('/agents/api/hangup-call/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                body: JSON.stringify({ call_id: this.currentCall.id })
            });

            const data = await response.json();

            if (data.success) {
                this.showNotification('info', 'Call ended');
            } else {
                this.showNotification('error', data.error);
            }

        } catch (error) {
            console.error('Error hanging up call:', error);
        }
    }

    setupStatusRefresh() {
        setInterval(() => {
            if (this.isConnected) {
                this.refreshAgentStatus();
            }
        }, 30000);
    }

    async refreshAgentStatus() {
        try {
            const response = await fetch('/agents/api/status/');
            const data = await response.json();

            if (data.success) {
                this.updateAgentStatus(data.agent_status);
                this.updateCurrentCampaign(data.current_campaign);

                if (data.current_call && !this.currentCall) {
                    this.currentCall = data.current_call;
                    this.updateCallDisplay({
                        number: data.current_call.number,
                        status: 'In Progress'
                    });
                }
            }
        } catch (error) {
            console.debug('Status refresh failed:', error);
        }
    }

    // WebSocket Management
    startHeartbeat() {
        this.stopHeartbeat();

        this.heartbeatInterval = setInterval(() => {
            if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
                this.sendMessage({
                    type: 'ping',
                    timestamp: new Date().toISOString()
                });
            }
        }, 30000);
    }

    stopHeartbeat() {
        if (this.heartbeatInterval) {
            clearInterval(this.heartbeatInterval);
            this.heartbeatInterval = null;
        }
    }

    scheduleReconnect() {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.error('❌ Max reconnection attempts reached');
            this.showNotification('error', 'Connection lost. Please refresh the page.');
            return;
        }

        this.reconnectAttempts++;
        const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);

        console.log(`🔄 Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);

        setTimeout(() => {
            this.connectWebSocket();
        }, delay);
    }

    sendMessage(message) {
        if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
            this.websocket.send(JSON.stringify(message));
        }
    }

    // Utilities
    getCSRFToken() {
        return document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
    }

    formatDuration(seconds) {
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    }

    showNotification(type, message) {
        console.log(`🔔 ${type.toUpperCase()}: ${message}`);

        let container = document.getElementById('notificationContainer');
        if (!container) {
            container = document.createElement('div');
            container.id = 'notificationContainer';
            container.className = 'notification-container position-fixed';
            container.style.cssText = 'top: 20px; right: 20px; z-index: 9999;';
            document.body.appendChild(container);
        }

        const notification = document.createElement('div');
        notification.className = `alert alert-${this.getAlertClass(type)} alert-dismissible fade show`;
        notification.innerHTML = `
            <i class="fas fa-${this.getAlertIcon(type)} me-2"></i>
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;

        container.appendChild(notification);

        setTimeout(() => {
            if (notification.parentNode) {
                notification.remove();
            }
        }, 5000);
    }

    getAlertClass(type) {
        const mapping = {
            success: 'success',
            error: 'danger',
            warning: 'warning',
            info: 'info'
        };
        return mapping[type] || 'info';
    }

    getAlertIcon(type) {
        const mapping = {
            success: 'check-circle',
            error: 'exclamation-triangle',
            warning: 'exclamation-triangle',
            info: 'info-circle'
        };
        return mapping[type] || 'info-circle';
    }
}

// Initialize when DOM ready
document.addEventListener('DOMContentLoaded', () => {
    window.agentPanel = new EnhancedAgentPanel();
});

// Global Logout Function
window.logout = function () {
    const form = document.createElement('form');
    form.method = 'POST';
    form.action = '/users/logout/';

    const csrfInput = document.createElement('input');
    csrfInput.type = 'hidden';
    csrfInput.name = 'csrfmiddlewaretoken';
    csrfInput.value = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
    form.appendChild(csrfInput);

    document.body.appendChild(form);
    form.submit();
};

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = EnhancedAgentPanel;
}
