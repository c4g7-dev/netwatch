#!/bin/bash
# NetWatch Linux Uninstallation Script
# This script removes NetWatch service and optionally removes all data

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
INSTALL_DIR="/opt/netwatch"
SERVICE_USER="netwatch"
SERVICE_FILE="/etc/systemd/system/netwatch.service"
BACKUP_DIR=""  # Will be set if data is backed up

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}Error: This script must be run as root (use sudo)${NC}"
    exit 1
fi

echo -e "${RED}=== NetWatch Uninstallation ===${NC}\n"
echo -e "${YELLOW}This will remove NetWatch from your system.${NC}\n"

# Ask about data removal
echo -e "${BLUE}Do you want to remove all NetWatch data?${NC}"
echo "This includes:"
echo "  - Speed test history and measurements"
echo "  - Device information"
echo "  - Configuration files"
echo "  - Logs"
echo ""
read -p "Remove all data? (y/N): " -n 1 -r
echo
REMOVE_DATA=false
if [[ $REPLY =~ ^[Yy]$ ]]; then
    REMOVE_DATA=true
    echo -e "${YELLOW}All data will be removed${NC}\n"
else
    echo -e "${GREEN}Data will be preserved${NC}\n"
fi

# Confirm uninstallation
echo -e "${YELLOW}This action cannot be undone!${NC}"
read -p "Continue with uninstallation? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${GREEN}Uninstallation cancelled${NC}"
    exit 0
fi

echo ""

# Stop the service
echo "Stopping NetWatch service..."
if systemctl is-active --quiet netwatch.service; then
    systemctl stop netwatch.service
    echo -e "${GREEN}✓ Service stopped${NC}"
else
    echo -e "${YELLOW}Service is not running${NC}"
fi
echo ""

# Disable the service
echo "Disabling NetWatch service..."
if systemctl is-enabled --quiet netwatch.service 2>/dev/null; then
    systemctl disable netwatch.service
    echo -e "${GREEN}✓ Service disabled${NC}"
else
    echo -e "${YELLOW}Service is not enabled${NC}"
fi
echo ""

# Remove systemd service file
echo "Removing systemd service file..."
if [ -f "$SERVICE_FILE" ]; then
    rm -f "$SERVICE_FILE"
    systemctl daemon-reload
    echo -e "${GREEN}✓ Service file removed${NC}"
else
    echo -e "${YELLOW}Service file not found${NC}"
fi
echo ""

# Stop internal speedtest server (if running separately)
echo "Checking for internal speedtest server processes..."
IPERF_PIDS=$(pgrep -f "iperf3.*5201" || true)
if [ -n "$IPERF_PIDS" ]; then
    echo "Stopping iperf3 processes on port 5201..."
    kill $IPERF_PIDS 2>/dev/null || true
    sleep 1
    # Force kill if still running - check if processes still exist
    REMAINING_PIDS=$(pgrep -f "iperf3.*5201" || true)
    if [ -n "$REMAINING_PIDS" ]; then
        kill -9 $REMAINING_PIDS 2>/dev/null || true
    fi
    echo -e "${GREEN}✓ Internal speedtest server stopped${NC}"
fi
echo ""

# Handle data and installation directory
if [ "$REMOVE_DATA" = true ]; then
    echo "Removing NetWatch installation directory and all data..."
    if [ -d "$INSTALL_DIR" ]; then
        rm -rf "$INSTALL_DIR"
        echo -e "${GREEN}✓ All NetWatch files and data removed${NC}"
    else
        echo -e "${YELLOW}Installation directory not found${NC}"
    fi
else
    echo "Preserving data, removing only application files..."
    if [ -d "$INSTALL_DIR" ]; then
        # Create backup of data directory
        if [ -d "$INSTALL_DIR/data" ]; then
            BACKUP_DIR="/tmp/netwatch_data_backup_$(date +%Y%m%d_%H%M%S)"
            cp -r "$INSTALL_DIR/data" "$BACKUP_DIR"
            echo -e "${GREEN}✓ Data backed up to: $BACKUP_DIR${NC}"
        fi
        
        # Remove application files but keep data - safely change directory
        if cd "$INSTALL_DIR" 2>/dev/null; then
            find . -maxdepth 1 -type f -delete 2>/dev/null || true
            rm -rf .venv app bin __pycache__ 2>/dev/null || true
            
            # Keep data, logs, and config.yaml
            echo -e "${GREEN}✓ Application files removed, data preserved in: $INSTALL_DIR/data${NC}"
            echo -e "${BLUE}  To completely remove data later, run: sudo rm -rf $INSTALL_DIR${NC}"
        else
            echo -e "${RED}Failed to access installation directory: $INSTALL_DIR${NC}"
        fi
    else
        echo -e "${YELLOW}Installation directory not found${NC}"
    fi
fi
echo ""

# Ask about user removal
if id "$SERVICE_USER" &>/dev/null; then
    echo -e "${BLUE}Do you want to remove the '$SERVICE_USER' system user?${NC}"
    read -p "Remove user? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        userdel "$SERVICE_USER" 2>/dev/null || true
        echo -e "${GREEN}✓ User '$SERVICE_USER' removed${NC}"
    else
        echo -e "${YELLOW}User '$SERVICE_USER' preserved${NC}"
    fi
fi
echo ""

# Display completion message
echo -e "${GREEN}=== Uninstallation Complete ===${NC}\n"
echo "NetWatch has been removed from your system."
echo ""

if [ "$REMOVE_DATA" = false ]; then
    echo -e "${YELLOW}Data preserved in: $INSTALL_DIR/data${NC}"
    echo "To remove data manually: sudo rm -rf $INSTALL_DIR"
    echo ""
fi

echo "System services cleaned up:"
echo "  ✓ Service stopped and disabled"
echo "  ✓ Systemd service file removed"
echo "  ✓ Internal speedtest server stopped"
echo ""

if [ "$REMOVE_DATA" = false ] && [ -d "$BACKUP_DIR" ]; then
    echo -e "${BLUE}Backup created at: $BACKUP_DIR${NC}"
    echo ""
fi

echo "Thank you for using NetWatch!"
