#!/bin/bash
# NDI Monitor - Raspberry Pi Installation Script

set -e

echo "=========================================="
echo "NDI Monitor - Raspberry Pi Setup"
echo "=========================================="

# Check if running as root
if [ "$EUID" -eq 0 ]; then 
    echo "Please do not run as root. Run as the 'pi' user."
    exit 1
fi

# Create installation directory
INSTALL_DIR="/home/pi/ndi-monitor"
echo "Installing to: $INSTALL_DIR"

# Create directory if it doesn't exist
mkdir -p "$INSTALL_DIR"

# Copy files to installation directory
echo "Copying application files..."
cp app.py ndi.py display.py index.html requirements.txt "$INSTALL_DIR/"
if [ -f "ndi_mock.py" ]; then
    cp ndi_mock.py "$INSTALL_DIR/"
fi

cd "$INSTALL_DIR"

# Install system dependencies
echo "Installing system dependencies..."
sudo apt-get update
sudo apt-get install -y python3-pip python3-venv python3-dev build-essential \
    libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev \
    libportmidi-dev libfreetype6-dev

# Create virtual environment
echo "Creating Python virtual environment..."
python3 -m venv venv

# Activate virtual environment and install Python packages
echo "Installing Python packages..."
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Download and install NDI SDK for Linux ARM
echo "=========================================="
echo "NDI SDK Installation"
echo "=========================================="
echo "You need to download the NDI SDK for Linux ARM from:"
echo "https://ndi.video/tools/"
echo ""
echo "1. Download 'NDI SDK for Linux'"
echo "2. Extract it and run the installer"
echo "3. The library will typically install to /usr/local/lib/"
echo ""
read -p "Have you installed the NDI SDK? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Please install NDI SDK and run this script again."
    exit 1
fis
echo "Installing systemd services..."
sudo cp "$INSTALL_DIR/../RaspberryPi/ndi-monitor.service" /etc/systemd/system/
sudo cp "$INSTALL_DIR/../RaspberryPi/ndi-display.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable ndi-monitor.service
sudo systemctl enable ndi-displayyPi/ndi-monitor.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable ndi-monitor.service

echo "========================:"
echo "  - Display video feed on HDMI output"
echo "  - Start automatically on boot"
echo "  - Be controllable via web interface"
echo ""
echo "To start now:"
echo "  sudo systemctl start ndi-monitor    # Web server"
echo "  sudo systemctl start ndi-display    # HDMI display"
echo ""
echo "To stop:"
echo "  sudo systemctl stop ndi-display"
echo "  sudo systemctl stop ndi-monitor"
echo ""
echo "View logs:"
echo "  sudo journalctl -u ndi-display -f   # Display logs"
echo "  sudo journalctl -u ndi-monitor -f   # Web server logs"
echo ""
echo "Access the web interface at: http://$(hostname -I | awk '{print $1}'):8000"
echo "  - Select NDI source"
echo "  - It will automatically appear on HDMI
echo "To view logs:     sudo journalctl -u ndi-monitor -f"
echo "To check status:  sudo systemctl status ndi-monitor"
echo ""
echo "Access the web interface at: http://$(hostname -I | awk '{print $1}'):8000"
echo ""
echo "To update remotely, use: /home/pi/ndi-monitor/update.sh"
echo ""
