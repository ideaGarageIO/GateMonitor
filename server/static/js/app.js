/**
 * Gate Monitor - Frontend Application
 * Real-time updates via WebSocket
 */

// WebSocket connection
let ws = null;
let reconnectAttempts = 0;
const MAX_RECONNECT_ATTEMPTS = 10;
const RECONNECT_DELAY = 3000;

// DOM Elements
const elements = {
    wsStatus: document.getElementById('ws-status'),
    mqttStatus: document.getElementById('mqtt-status'),
    gatewayStatus: document.getElementById('gateway-status'),
    gateState: document.getElementById('gate-state'),
    gateOnline: document.getElementById('gate-online'),
    batteryValue: document.getElementById('battery-value'),
    batteryLevel: document.getElementById('battery-level'),
    rssiValue: document.getElementById('rssi-value'),
    snrValue: document.getElementById('snr-value'),
    lastUpdate: document.getElementById('last-update'),
    historyList: document.getElementById('history-list'),
    commandFeedback: document.getElementById('command-feedback'),
};

// History storage
let history = [];
const MAX_HISTORY = 20;

/**
 * Initialize the application
 */
function init() {
    connectWebSocket();
    loadHistory();
}

/**
 * Connect to WebSocket server
 */
function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;

    console.log(`Connecting to WebSocket: ${wsUrl}`);

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        console.log('WebSocket connected');
        reconnectAttempts = 0;
        updateConnectionStatus(true);
    };

    ws.onclose = () => {
        console.log('WebSocket disconnected');
        updateConnectionStatus(false);
        scheduleReconnect();
    };

    ws.onerror = (error) => {
        console.error('WebSocket error:', error);
    };

    ws.onmessage = (event) => {
        try {
            const message = JSON.parse(event.data);
            handleMessage(message);
        } catch (e) {
            console.error('Failed to parse message:', e);
        }
    };
}

/**
 * Schedule WebSocket reconnection
 */
function scheduleReconnect() {
    if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
        reconnectAttempts++;
        console.log(`Reconnecting in ${RECONNECT_DELAY}ms (attempt ${reconnectAttempts})`);
        setTimeout(connectWebSocket, RECONNECT_DELAY);
    } else {
        console.error('Max reconnection attempts reached');
    }
}

/**
 * Handle incoming WebSocket message
 */
function handleMessage(message) {
    if (message.type === 'status') {
        updateStatus(message.data);
    }
}

/**
 * Update the UI with new status data
 */
function updateStatus(data) {
    // MQTT connection status
    if (data.mqtt_connected !== undefined) {
        updateMqttStatus(data.mqtt_connected);
    }

    // Gateway connection status
    const gatewayOnline = data.gateway_online !== undefined ? data.gateway_online : false;
    updateGatewayStatus(gatewayOnline);

    // Gate state
    const state = data.state.toLowerCase();
    elements.gateState.className = `gate-state ${state}`;
    elements.gateState.querySelector('.state-text').textContent = data.state;

    // Online status
    elements.gateOnline.className = `gate-online ${data.online ? 'online' : 'offline'}`;
    elements.gateOnline.querySelector('.online-text').textContent =
        data.online ? 'Online' : 'Offline';

    // When gateway is offline, show placeholder values for telemetry
    if (!gatewayOnline) {
        elements.batteryValue.textContent = '--';
        elements.batteryLevel.style.width = '0%';
        elements.batteryLevel.className = 'battery-level';
        elements.rssiValue.textContent = '--';
        elements.snrValue.textContent = '--';
    } else {
        // Battery
        elements.batteryValue.textContent = `${data.battery_v}V`;
        const batteryPercent = calculateBatteryPercent(data.battery_mv);
        elements.batteryLevel.style.width = `${batteryPercent}%`;
        elements.batteryLevel.className = 'battery-level';
        if (batteryPercent < 20) {
            elements.batteryLevel.classList.add('critical');
        } else if (batteryPercent < 40) {
            elements.batteryLevel.classList.add('low');
        }

        // Signal
        elements.rssiValue.textContent = `${data.rssi} dBm`;
        elements.snrValue.textContent = `${data.snr} dB`;
    }

    // Last update - always show when we last heard from the system
    if (data.last_update) {
        const date = new Date(data.last_update);
        elements.lastUpdate.textContent = formatTime(date);
    }

    // Add to history if state changed
    if (history.length === 0 || history[0].state !== data.state) {
        addHistoryEntry({
            state: data.state,
            battery_mv: data.battery_mv,
            timestamp: data.last_update,
        });
    }
}

/**
 * Calculate battery percentage (12V lead-acid: 11.0V = 0%, 12.6V = 100%)
 */
function calculateBatteryPercent(mv) {
    const minV = 11000;
    const maxV = 12600;
    const percent = ((mv - minV) / (maxV - minV)) * 100;
    return Math.max(0, Math.min(100, percent));
}

/**
 * Format time for display
 */
function formatTime(date) {
    const now = new Date();
    const diff = now - date;

    if (diff < 60000) {
        return 'Just now';
    } else if (diff < 3600000) {
        const mins = Math.floor(diff / 60000);
        return `${mins}m ago`;
    } else if (diff < 86400000) {
        const hours = Math.floor(diff / 3600000);
        return `${hours}h ago`;
    } else {
        return date.toLocaleString();
    }
}

/**
 * Update WebSocket connection status indicator
 */
function updateConnectionStatus(connected) {
    elements.wsStatus.className =
        `connection-status ${connected ? 'online' : 'offline'}`;
    elements.wsStatus.querySelector('.status-text').textContent =
        connected ? 'Server' : 'Server';
}

/**
 * Update MQTT connection status indicator
 */
function updateMqttStatus(connected) {
    elements.mqttStatus.className =
        `connection-status ${connected ? 'online' : 'offline'}`;
    elements.mqttStatus.querySelector('.status-text').textContent = 'MQTT';
}

/**
 * Update Gateway connection status indicator
 */
function updateGatewayStatus(connected) {
    elements.gatewayStatus.className =
        `connection-status ${connected ? 'online' : 'offline'}`;
    elements.gatewayStatus.querySelector('.status-text').textContent = 'Gateway';
}

/**
 * Send command to gate
 */
function sendCommand(command) {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
        showFeedback('Not connected to server', 'error');
        return;
    }

    const message = JSON.stringify({
        type: 'command',
        command: command,
    });

    ws.send(message);
    showFeedback(`Sending ${command.toUpperCase()} command...`, 'pending');

    // Clear feedback after delay
    setTimeout(() => {
        showFeedback('', '');
    }, 3000);
}

/**
 * Show command feedback
 */
function showFeedback(message, type) {
    elements.commandFeedback.textContent = message;
    elements.commandFeedback.className = `command-feedback ${type}`;
}

/**
 * Add entry to history
 */
function addHistoryEntry(entry) {
    history.unshift(entry);
    if (history.length > MAX_HISTORY) {
        history.pop();
    }
    renderHistory();
}

/**
 * Load history from API
 */
async function loadHistory() {
    try {
        const response = await fetch('/api/history');
        if (response.ok) {
            const data = await response.json();
            history = data.slice(0, MAX_HISTORY);
            renderHistory();
        }
    } catch (e) {
        console.error('Failed to load history:', e);
    }
}

/**
 * Render history list
 */
function renderHistory() {
    if (history.length === 0) {
        elements.historyList.innerHTML = '<p class="no-history">No activity recorded</p>';
        return;
    }

    const html = history.map(entry => {
        const state = entry.state.toLowerCase();
        const date = new Date(entry.timestamp);
        return `
            <div class="history-item">
                <div class="history-state">
                    <span class="state-badge ${state}">${entry.state}</span>
                </div>
                <span class="history-time">${formatTime(date)}</span>
            </div>
        `;
    }).join('');

    elements.historyList.innerHTML = html;
}

// Initialize on load
document.addEventListener('DOMContentLoaded', init);
