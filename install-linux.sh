#!/bin/bash
# NetWatch Linux Installation Script
# This script installs NetWatch as a systemd service

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
INSTALL_DIR="/opt/netwatch"
SERVICE_USER="netwatch"
SERVICE_FILE="/etc/systemd/system/netwatch.service"

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}Error: This script must be run as root (use sudo)${NC}"
    exit 1
fi

echo -e "${GREEN}=== NetWatch Linux Installation ===${NC}\n"

# Check for Python 3.10+
echo "Checking Python version..."
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: Python 3 is not installed${NC}"
    echo "Install Python 3.10+ and try again"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
REQUIRED_VERSION="3.10"
if ! python3 -c "import sys; exit(0 if sys.version_info >= (3, 10) else 1)" 2>/dev/null; then
    echo -e "${RED}Error: Python 3.10+ required (found $PYTHON_VERSION)${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Python $PYTHON_VERSION detected${NC}\n"

# Install system dependencies
echo "Installing system dependencies..."
if command -v apt-get &> /dev/null; then
    apt-get update
    apt-get install -y python3-venv python3-pip iperf3 curl
elif command -v yum &> /dev/null; then
    yum install -y python3-venv python3-pip iperf3 curl
elif command -v dnf &> /dev/null; then
    dnf install -y python3-venv python3-pip iperf3 curl
else
    echo -e "${YELLOW}Warning: Could not detect package manager. Please install python3-venv, python3-pip, and iperf3 manually${NC}"
fi
echo -e "${GREEN}✓ System dependencies installed${NC}\n"

# Create service user
echo "Creating service user..."
if ! id "$SERVICE_USER" &>/dev/null; then
    useradd -r -s /bin/false -d "$INSTALL_DIR" "$SERVICE_USER"
    echo -e "${GREEN}✓ User '$SERVICE_USER' created${NC}"
else
    echo -e "${YELLOW}User '$SERVICE_USER' already exists${NC}"
fi
echo ""

# Create installation directory
echo "Creating installation directory..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR"/{data,logs,bin}

# Copy application files
echo "Copying application files..."
cp -r . "$INSTALL_DIR/"

# Set proper ownership
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
# Ensure data directory is writable
chmod 755 "$INSTALL_DIR/data"
chmod 755 "$INSTALL_DIR/logs"
echo -e "${GREEN}✓ Files copied to $INSTALL_DIR${NC}\n"

# Create virtual environment
echo "Creating Python virtual environment..."
cd "$INSTALL_DIR"
sudo -u "$SERVICE_USER" python3 -m venv .venv
echo -e "${GREEN}✓ Virtual environment created${NC}\n"

# Install Python dependencies
echo "Installing Python dependencies..."
sudo -u "$SERVICE_USER" .venv/bin/pip install --upgrade pip
sudo -u "$SERVICE_USER" .venv/bin/pip install -r requirements.txt
echo -e "${GREEN}✓ Python dependencies installed${NC}\n"

# Download Ookla Speedtest CLI
echo "Downloading Ookla Speedtest CLI..."
sudo -u "$SERVICE_USER" .venv/bin/python installer.py
echo -e "${GREEN}✓ Ookla binary downloaded${NC}\n"

# Check if port 5201 is available for internal speedtest server
echo "Checking if port 5201 is available for internal speedtest server..."
if lsof -Pi :5201 -sTCP:LISTEN -t >/dev/null 2>&1 || netstat -tuln 2>/dev/null | grep -q ":5201 "; then
    echo -e "${YELLOW}⚠ Warning: Port 5201 is already in use${NC}"
    echo -e "${YELLOW}  The internal homenet speedtest feature may not work${NC}"
    echo -e "${YELLOW}  You can check what's using it with: sudo lsof -i :5201${NC}"
else
    echo -e "${GREEN}✓ Port 5201 is available${NC}"
fi
echo ""

# Install systemd service
echo "Installing systemd service..."
cp netwatch.service "$SERVICE_FILE"
systemctl daemon-reload
systemctl enable netwatch.service
echo -e "${GREEN}✓ Systemd service installed${NC}\n"

# Start service
echo "Starting NetWatch service..."
systemctl start netwatch.service
sleep 2

if systemctl is-active --quiet netwatch.service; then
    echo -e "${GREEN}✓ NetWatch service is running${NC}\n"
else
    echo -e "${RED}✗ Failed to start NetWatch service${NC}"
    echo "Check logs with: journalctl -u netwatch.service -n 50"
    exit 1
fi

# Display status
echo -e "${GREEN}=== Installation Complete! ===${NC}\n"
echo "NetWatch is now running as a systemd service"
echo ""
echo "Features enabled:"
echo "  ✓ Internet speedtest (Ookla)"
echo "  ✓ Internet bufferbloat testing (iperf3)"
echo "  ✓ Homenet speedtest server (port 5201)"
echo "  ✓ Automatic scheduler (check dashboard to configure)"
echo ""
echo "Useful commands:"
echo "  - View status:       systemctl status netwatch"
echo "  - View logs:         journalctl -u netwatch -f"
echo "  - Restart service:   systemctl restart netwatch"
echo "  - Stop service:      systemctl stop netwatch"
echo "  - Check config:      nano $INSTALL_DIR/config.yaml"
echo ""
echo "Dashboard URL: http://$(hostname -I | awk '{print $1}'):8000"
echo ""
echo -e "${YELLOW}Note: Make sure port 8000 is open in your firewall${NC}"
echo -e "${YELLOW}      For homenet speedtest, port 5201 should also be accessible on your LAN${NC}"
echo ""
echo "To verify everything is working:"
echo "  1. Open the dashboard in your browser"
echo "  2. Check the scheduler status in the top right"
echo "  3. Try a manual speedtest"
echo "  4. Check the Homenet tab to verify internal speedtest server is running"
echo ""
echo "If you encounter issues, check the logs with:"
echo "  journalctl -u netwatch -n 100 --no-pager"
