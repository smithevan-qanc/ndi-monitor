#!/bin/bash
# NDI Monitor - Remote Update Script

set -e

INSTALL_DIR="/home/pi/ndi-monitor"
BACKUP_DIR="/home/pi/ndi-monitor-backup-$(date +%Y%m%d-%H%M%S)"

echo "=========================================="
echo "NDI Monitor - Update Script"
echo "=========================================="

# Check if running as pi user
if [ "$USER" != "pi" ]; then
    echo "Please run as 'pi' user"
    exit 1
fi

# Backup current installation
echo "Creating backup at: $BACKUP_DIR"
cp -r "$INSTALL_DIR" "$BACKUP_DIR"

# Stop the services
echo "Stopping NDI Monitor services..."
sudo systemctl stop ndi-display
sudo systemctl stop ndi-monitor

cd "$INSTALL_DIR"

# If this is a git repository, pull latest
if [ -d ".git" ]; then
    echo "Pulling latest changes from git..."
    git pull
else
    echo "Not a git repository. Manual file update required."
    echo "Upload new files to $INSTALL_DIR and they will be used."
fi

# Update Python dependencies
echo "Updating Python dependencies..."
source venv/bin/activate
pip install --upgrade -r requirements.txt
s
echo "Starting NDI Monitor services..."
sudo systemctl start ndi-monitor
sudo systemctl start ndi-displayce..."
sudo systemctl start ndi-monitor

echo "=========================================="
echo "Update Complete!"
echo "=========================================="
echo ""
echo "Service status:"
echo "Web server:"
sudo systemctl status ndi-monitor --no-pager
echo ""
echo "HDMI Display:"
sudo systemctl status ndi-display --no-pager
echo ""
echo "To view logs:"
echo "  sudo journalctl -u ndi-display -f   # Display"
echo "  sudo journalctl -u ndi-monitor -f   # Web server
echo ""
echo "To view logs: sudo journalctl -u ndi-monitor -f"
echo ""
