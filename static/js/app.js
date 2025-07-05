/* ===================================== */
/* static/js/app.js */

// Global JavaScript for Autodialer System

class AutoDialerApp {
    constructor() {
        this.init();
        this.setupWebSocket();
        this.setupEventListeners();
    }

    init() {
        console.log('AutoDialer App initialized');
        
        // Setup CSRF token for AJAX requests
        const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
        if (csrfToken) {
            $.ajaxSetup({
                beforeSend: function(xhr, settings) {
                    if (!this.crossDomain) {
                        xhr.setRequestHeader("X-CSRFToken", csrfToken);
                    }
                }
            });
        }
        
        // Initialize tooltips
        const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
        tooltipTriggerList.map(function (tooltipTriggerEl) {
            return new bootstrap.Tooltip(tooltipTriggerEl);
        });
        
        // Auto-refresh dashboard stats every 30 seconds
        if (document.querySelector('.dashboard-stats')) {
            setInterval(() => this.refreshDashboardStats(), 30000);
        }
    }

    setupWebSocket() {
        // WebSocket connection for real-time updates
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/updates/`;
        
        try {
            this.socket = new WebSocket(wsUrl);
            
            this.socket.onopen = (event) => {
                console.log('WebSocket connected');
                this.showConnectionStatus(true);
            };
            
            this.socket.onmessage = (event) => {
                const data = JSON.parse(event.data);
                this.handleWebSocketMessage(data);
            };
            
            this.socket.onclose = (event) => {
                console.log('WebSocket disconnected');
                this.showConnectionStatus(false);
                
                // Attempt to reconnect after 5 seconds
                setTimeout(() => {
                    this.setupWebSocket();
                }, 5000);
            };
            
            this.socket.onerror = (error) => {
                console.error('WebSocket error:', error);
            };
        } catch (error) {
            console.error('Failed to create WebSocket:', error);
        }
    }

    handleWebSocketMessage(data) {
        switch (data.type) {
            case 'campaign_update':
                this.updateCampaignStatus(data.campaign_id, data.status);
                break;
                
            case 'call_update':
                this.updateCallStatus(data);
                break;
                
            case 'agent_update':
                this.updateAgentStatus(data.agent_id, data.status);
                break;
                
            case 'stats_update':
                this.updateDashboardStats(data.stats);
                break;
                
            case 'notification':
                this.showNotification(data.message, data.level || 'info');
                break;
        }
    }

    setupEventListeners() {
        // Global event listeners
        document.addEventListener('DOMContentLoaded', () => {
            // Auto-hide alerts after 5 seconds
            setTimeout(() => {
                $('.alert').fadeOut();
            }, 5000);
            
            // Handle form submissions with loading states
            $('form').on('submit', function() {
                const submitBtn = $(this).find('button[type="submit"]');
                submitBtn.prop('disabled', true);
                submitBtn.html('<span class="loading-spinner"></span> Processing...');
            });
            
            // Handle file upload progress
            $('input[type="file"]').on('change', function() {
                const file = this.files[0];
                if (file) {
                    $(this).next('.file-info').text(`Selected: ${file.name} (${(file.size / 1024 / 1024).toFixed(2)} MB)`);
                }
            });
        });
        
        // Handle HTMX events
        document.body.addEventListener('htmx:beforeRequest', (event) => {
            this.showLoading(true);
        });
        
        document.body.addEventListener('htmx:afterRequest', (event) => {
            this.showLoading(false);
        });
    }

    refreshDashboardStats() {
        fetch('/api/dashboard-stats/')
            .then(response => response.json())
            .then(data => {
                this.updateDashboardStats(data);
            })
            .catch(error => {
                console.error('Error refreshing dashboard stats:', error);
            });
    }

    updateDashboardStats(stats) {
        // Update dashboard statistics
        for (const [key, value] of Object.entries(stats)) {
            const element = document.querySelector(`[data-stat="${key}"]`);
            if (element) {
                element.textContent = value;
            }
        }
    }

    updateCampaignStatus(campaignId, status) {
        const statusElement = document.querySelector(`[data-campaign-id="${campaignId}"] .campaign-status`);
        if (statusElement) {
            statusElement.textContent = status;
            statusElement.className = `campaign-status badge bg-${this.getStatusColor(status)}`;
        }
    }

    updateCallStatus(callData) {
        // Update call status in real-time
        const callElement = document.querySelector(`[data-call-id="${callData.call_id}"]`);
        if (callElement) {
            const statusElement = callElement.querySelector('.call-status');
            if (statusElement) {
                statusElement.textContent = callData.status;
                statusElement.className = `call-status badge bg-${this.getStatusColor(callData.status)}`;
            }
        }
    }

    updateAgentStatus(agentId, status) {
        const agentElement = document.querySelector(`[data-agent-id="${agentId}"]`);
        if (agentElement) {
            const statusIndicator = agentElement.querySelector('.status-indicator');
            if (statusIndicator) {
                statusIndicator.className = `status-indicator status-${status}`;
            }
        }
    }

    showConnectionStatus(connected) {
        const indicator = document.querySelector('.connection-status');
        if (indicator) {
            indicator.className = `connection-status ${connected ? 'text-success' : 'text-danger'}`;
            indicator.textContent = connected ? 'Connected' : 'Disconnected';
        }
    }

    showNotification(message, level = 'info') {
        // Create and show notification
        const alertClass = level === 'error' ? 'danger' : level;
        const alertHtml = `
            <div class="alert alert-${alertClass} alert-dismissible fade show" role="alert">
                ${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
        `;
        
        const container = document.querySelector('.alert-container') || document.querySelector('main');
        if (container) {
            container.insertAdjacentHTML('afterbegin', alertHtml);
            
            // Auto-hide after 5 seconds
            setTimeout(() => {
                const alert = container.querySelector('.alert');
                if (alert) {
                    alert.remove();
                }
            }, 5000);
        }
    }

    showLoading(show) {
        const loader = document.querySelector('.loading-overlay');
        if (loader) {
            loader.style.display = show ? 'flex' : 'none';
        }
    }

    getStatusColor(status) {
        const statusColors = {
            'active': 'success',
            'inactive': 'secondary',
            'paused': 'warning',
            'completed': 'info',
            'error': 'danger',
            'online': 'success',
            'busy': 'warning',
            'offline': 'secondary',
            'ringing': 'info',
            'answered': 'success',
            'hangup': 'secondary'
        };
        
        return statusColors[status?.toLowerCase()] || 'secondary';
    }

    // Utility methods
    formatPhoneNumber(phone) {
        const cleaned = phone.replace(/\D/g, '');
        if (cleaned.length === 10) {
            return `(${cleaned.slice(0, 3)}) ${cleaned.slice(3, 6)}-${cleaned.slice(6)}`;
        }
        return phone;
    }

    formatDuration(seconds) {
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = seconds % 60;
        
        if (hours > 0) {
            return `${hours}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
        }
        return `${minutes}:${secs.toString().padStart(2, '0')}`;
    }

    // API helper methods
    async apiRequest(url, options = {}) {
        const defaultOptions = {
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]')?.value || ''
            }
        };
        
        const mergedOptions = { ...defaultOptions, ...options };
        
        try {
            const response = await fetch(url, mergedOptions);
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            return await response.json();
        } catch (error) {
            console.error('API request failed:', error);
            throw error;
        }
    }
}

// Initialize the app when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.autoDialerApp = new AutoDialerApp();
});

// Agent Interface specific functions
class AgentInterface {
    constructor() {
        this.currentCall = null;
        this.agentStatus = 'offline';
        this.init();
    }

    init() {
        this.setupCallControls();
        this.updateAgentStatus();
    }

    setupCallControls() {
        // Answer call button
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('answer-call-btn')) {
                this.answerCall(e.target.dataset.callId);
            }
            
            if (e.target.classList.contains('hangup-call-btn')) {
                this.hangupCall(e.target.dataset.callId);
            }
            
            if (e.target.classList.contains('transfer-call-btn')) {
                this.transferCall(e.target.dataset.callId);
            }
        });
    }

    async answerCall(callId) {
        try {
            const response = await window.autoDialerApp.apiRequest('/api/calls/answer/', {
                method: 'POST',
                body: JSON.stringify({ call_id: callId })
            });
            
            if (response.success) {
                this.currentCall = response.call;
                this.updateCallInterface();
            }
        } catch (error) {
            console.error('Error answering call:', error);
            window.autoDialerApp.showNotification('Failed to answer call', 'error');
        }
    }

    async hangupCall(callId) {
        try {
            const response = await window.autoDialerApp.apiRequest('/api/calls/hangup/', {
                method: 'POST',
                body: JSON.stringify({ call_id: callId })
            });
            
            if (response.success) {
                this.currentCall = null;
                this.updateCallInterface();
            }
        } catch (error) {
            console.error('Error hanging up call:', error);
            window.autoDialerApp.showNotification('Failed to hangup call', 'error');
        }
    }

    updateCallInterface() {
        const callPanel = document.querySelector('.call-panel');
        if (callPanel) {
            if (this.currentCall) {
                callPanel.innerHTML = this.generateCallPanelHTML(this.currentCall);
            } else {
                callPanel.innerHTML = '<p class="text-center">No active calls</p>';
            }
        }
    }

    generateCallPanelHTML(call) {
        return `
            <div class="card">
                <div class="card-header">
                    <h5>Active Call</h5>
                </div>
                <div class="card-body">
                    <p><strong>Phone:</strong> ${window.autoDialerApp.formatPhoneNumber(call.phone_number)}</p>
                    <p><strong>Lead:</strong> ${call.lead_name}</p>
                    <p><strong>Duration:</strong> <span class="call-duration" data-start="${call.start_time}">00:00</span></p>
                    
                    <div class="call-controls text-center">
                        <button class="btn call-control-btn hangup" data-call-id="${call.id}">
                            <i class="fas fa-phone-slash"></i>
                        </button>
                        <button class="btn call-control-btn" data-bs-toggle="modal" data-bs-target="#transferModal">
                            <i class="fas fa-exchange-alt"></i>
                        </button>
                    </div>
                </div>
            </div>
        `;
    }

    updateAgentStatus() {
        // Update agent status periodically
        setInterval(() => {
            const statusElement = document.querySelector('.agent-status');
            if (statusElement) {
                statusElement.textContent = this.agentStatus;
                statusElement.className = `agent-status badge bg-${window.autoDialerApp.getStatusColor(this.agentStatus)}`;
            }
        }, 1000);
    }
}

// Initialize agent interface if on agent page
if (document.querySelector('.agent-interface')) {
    document.addEventListener('DOMContentLoaded', () => {
        window.agentInterface = new AgentInterface();
    });
}