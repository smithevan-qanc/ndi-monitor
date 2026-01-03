# NDI Monitor - Raspberry Pi 4 Setup Guide

This guide will help you set up the NDI Monitor on a Raspberry Pi 4 to automatically start on boot and be controllable via web interface.

## Requirements

- Raspberry Pi 4 (2GB RAM minimum, 4GB recommended)
- Raspberry Pi OS (64-bit recommended)
- Network connection (Ethernet or WiFi)
- NDI SDK for Linux ARM

## Installation Steps

### 1. Prepare Your Raspberry Pi

```bash
# Update system
sudo apt-get update
sudo apt-get upgrade -y
```

### 2. Transfer Files to Raspberry Pi

Option A - Using SCP from your Mac:
```bash
cd /Users/evansmith/NDI/RaspberryPi
scp -r * pi@your-pi-ip:/home/pi/ndi-monitor-install/
```

Option B - Using USB drive:
- Copy the RaspberryPi folder to a USB drive
- Insert into Pi and copy files

### 3. Download NDI SDK

On your Raspberry Pi:
1. Visit https://ndi.video/tools/
2. Download "NDI SDK for Linux" (ARM version)
3. Extract and run the installer:
   ```bash
   chmod +x Install_NDI_SDK_v5_Linux.sh
   sudo ./Install_NDI_SDK_v5_Linux.sh
   ```

### 4. Run Installation Script

```bash
cd /home/pi/ndi-monitor-install
chmod +x install.sh
./install.sh
```

The installation script will:
- Install system dependencies
- Create Python virtual environment
- Install Python packages
- Set up systemd service for auto-start
- Configure the service to run on boot

### 5. Start the Service

```bash
# Start immediately
sudo systemctl start ndi-monitor

# Check status
sudo systemctl status ndi-monitor

# View live logs
sudo journalctl -u ndi-monitor -f
```

## Accessing the Web Interface

Find your Pi's IP address:
```bash
hostname -I
```

Then open in your browser:
```
http://YOUR_PI_IP:8000
```

## Remote Management

### View Logs
```bash
sudo journalctl -u ndi-monitor -f
```

### Restart Service
```bash
sudo systemctl restart ndi-monitor
```

### Stop Service
```bash
sudo systemctl stop ndi-monitor
```

### Update Application
```bash
/home/pi/ndi-monitor/update.sh
```

## Remote Update Methods

### Method 1: Using Git (Recommended)

If you want to use Git for updates:

```bash
cd /home/pi/ndi-monitor
git init
git remote add origin YOUR_GIT_REPO_URL
```

Then updates are as simple as:
```bash
./update.sh
```

### Method 2: Manual File Upload

Upload new files via SCP:
```bash
# From your Mac
scp app.py ndi.py index.html pi@YOUR_PI_IP:/home/pi/ndi-monitor/
```

Then restart:
```bash
ssh pi@YOUR_PI_IP
sudo systemctl restart ndi-monitor
```

### Method 3: Web-based Update (Future Enhancement)

You could add a file upload endpoint to the app for updating through the web interface.

## Auto-Start Configuration

The service is configured to:
- Start automatically on boot
- Restart automatically if it crashes
- Wait 10 seconds between restart attempts
- Run as the 'pi' user

Service file location: `/etc/systemd/system/ndi-monitor.service`

## Troubleshooting

### Service won't start
```bash
# Check logs
sudo journalctl -u ndi-monitor -n 50

# Check if NDI library is installed
ldconfig -p | grep ndi
```

### Can't access web interface
```bash
# Check if service is running
sudo systemctl status ndi-monitor

# Check firewall (if enabled)
sudo ufw allow 8000
```

### NDI library not found
Make sure you've installed the NDI SDK. The library should be at:
- `/usr/local/lib/libndi.so`

### Performance issues
For Raspberry Pi 4:
- Use 720p output instead of native resolution
- Lower JPEG quality to 60-70
- Ensure good network connection (Ethernet preferred)

## System Resource Usage

Expected usage on Pi 4:
- CPU: 30-50% (depends on resolution and quality)
- RAM: 200-400MB
- Network: Varies with NDI stream quality

## Network Configuration

### Fixed IP Address (Recommended)

Edit `/etc/dhcpcd.conf`:
```bash
sudo nano /etc/dhcpcd.conf
```

Add:
```
interface eth0
static ip_address=192.168.1.100/24
static routers=192.168.1.1
static domain_name_servers=192.168.1.1 8.8.8.8
```

### Port Forwarding

If you need external access, forward port 8000 on your router to your Pi's IP address.

## Security Recommendations

1. Change default Pi password: `passwd`
2. Enable SSH key authentication
3. Configure firewall:
   ```bash
   sudo apt-get install ufw
   sudo ufw allow 22
   sudo ufw allow 8000
   sudo ufw enable
   ```
4. Keep system updated: `sudo apt-get update && sudo apt-get upgrade`

## Uninstallation

```bash
# Stop and disable service
sudo systemctl stop ndi-monitor
sudo systemctl disable ndi-monitor
sudo rm /etc/systemd/system/ndi-monitor.service
sudo systemctl daemon-reload

# Remove installation
rm -rf /home/pi/ndi-monitor
```

## Support

For issues or questions, check:
- Application logs: `sudo journalctl -u ndi-monitor -f`
- System logs: `dmesg | tail`
- NDI SDK documentation: https://ndi.video/developers/
