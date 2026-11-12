#!/bin/bash
#
# Gate Monitor - Raspberry Pi Setup Script
#
# This script installs and configures all dependencies for the Gate Monitor
# server on a Raspberry Pi (or any Debian-based system).
#
# Usage: sudo ./setup-raspberry-pi.sh
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SERVER_DIR="$PROJECT_DIR/server"

echo -e "${GREEN}=== Gate Monitor - Raspberry Pi Setup ===${NC}"
echo "Project directory: $PROJECT_DIR"
echo "Server directory: $SERVER_DIR"
echo ""

# Check if running as root
if [[ $EUID -ne 0 ]]; then
    echo -e "${RED}Error: This script must be run as root (use sudo)${NC}"
    exit 1
fi

# Get the actual user (not root)
ACTUAL_USER="${SUDO_USER:-$USER}"
ACTUAL_HOME=$(getent passwd "$ACTUAL_USER" | cut -d: -f6)

echo -e "${YELLOW}Step 1: Updating package lists...${NC}"
apt-get update

echo -e "${YELLOW}Step 2: Installing system dependencies...${NC}"
apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    mosquitto \
    mosquitto-clients

echo -e "${YELLOW}Step 3: Configuring Mosquitto MQTT broker...${NC}"

# Create mosquitto config for local connections
cat > /etc/mosquitto/conf.d/gate-monitor.conf << 'EOF'
# Gate Monitor MQTT Configuration
# Allow connections on port 1883 from any interface
listener 1883

# Allow anonymous connections (no username/password required)
# For production, consider enabling authentication
allow_anonymous true

# Logging
log_dest file /var/log/mosquitto/mosquitto.log
log_type error
log_type warning
log_type notice
log_type information
EOF

echo "Mosquitto config written to /etc/mosquitto/conf.d/gate-monitor.conf"

# Restart mosquitto to apply config
systemctl restart mosquitto
systemctl enable mosquitto

echo -e "${GREEN}Mosquitto configured and running${NC}"

# Test mosquitto
echo "Testing MQTT broker..."
if mosquitto_pub -h localhost -t test -m "setup-test" 2>/dev/null; then
    echo -e "${GREEN}MQTT broker test passed${NC}"
else
    echo -e "${RED}MQTT broker test failed - check logs with: journalctl -u mosquitto${NC}"
fi

echo -e "${YELLOW}Step 4: Setting up Python virtual environment...${NC}"

cd "$SERVER_DIR"

# Create venv if it doesn't exist
if [[ ! -d ".venv" ]]; then
    sudo -u "$ACTUAL_USER" python3 -m venv .venv
    echo "Virtual environment created"
else
    echo "Virtual environment already exists"
fi

# Install Python dependencies
echo -e "${YELLOW}Step 5: Installing Python dependencies...${NC}"
sudo -u "$ACTUAL_USER" .venv/bin/pip install --upgrade pip
sudo -u "$ACTUAL_USER" .venv/bin/pip install -e .

echo -e "${GREEN}Python dependencies installed${NC}"

echo -e "${YELLOW}Step 6: Creating environment configuration...${NC}"

# Create .env file if it doesn't exist
ENV_FILE="$SERVER_DIR/.env"
if [[ ! -f "$ENV_FILE" ]]; then
    cat > "$ENV_FILE" << 'EOF'
# Gate Monitor Server Configuration

# MQTT Broker settings
MQTT_HOST=localhost
MQTT_PORT=1883
# MQTT_USER=
# MQTT_PASSWORD=

# Web server settings
HOST=0.0.0.0
PORT=8000

# Set to true for development (enables auto-reload)
DEBUG=false
EOF
    chown "$ACTUAL_USER:$ACTUAL_USER" "$ENV_FILE"
    echo "Created $ENV_FILE"
else
    echo ".env file already exists, skipping"
fi

echo -e "${YELLOW}Step 7: Setting up systemd service...${NC}"

# Create systemd service file
cat > /etc/systemd/system/gate-monitor.service << EOF
[Unit]
Description=Gate Monitor Web Server
After=network.target mosquitto.service
Requires=mosquitto.service

[Service]
Type=simple
User=$ACTUAL_USER
WorkingDirectory=$SERVER_DIR
Environment="PATH=$SERVER_DIR/.venv/bin"
ExecStart=$SERVER_DIR/.venv/bin/python -m gate_monitor.main
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable gate-monitor

echo -e "${GREEN}Systemd service created: gate-monitor${NC}"

echo ""
echo -e "${GREEN}=== Setup Complete ===${NC}"
echo ""
echo "Services installed:"
echo "  - mosquitto (MQTT broker) - running on port 1883"
echo "  - gate-monitor (web server) - will run on port 8000"
echo ""
echo "Commands:"
echo "  Start server:    sudo systemctl start gate-monitor"
echo "  Stop server:     sudo systemctl stop gate-monitor"
echo "  View logs:       sudo journalctl -u gate-monitor -f"
echo "  MQTT logs:       sudo journalctl -u mosquitto -f"
echo ""
echo "Test MQTT:"
echo "  mosquitto_sub -h localhost -t 'gate/#' -v"
echo ""
echo "Access the web dashboard at: http://<raspberry-pi-ip>:8000"
echo ""
