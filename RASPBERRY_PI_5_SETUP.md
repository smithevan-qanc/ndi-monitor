# NDI Monitor - Raspberry Pi 5 Complete Setup Guide

This guide documents the complete configuration for replicating the NDI Monitor setup on a Raspberry Pi 5 with HDMI output and web control interface.

## Features

- **HDMI Display**: Full-screen NDI video output via pygame
- **Web Control Panel**: Real-time configuration via WebSocket
- **Source Selection**: Browse and select NDI sources on your network
- **HDMI Blanking**: Fade-to-black with smooth transitions
- **FPS Overlay**: Optional FPS counter on HDMI display
- **Custom Messages**: Configurable "No Connection" text with variable substitution
- **Live Logs**: Real-time log streaming via WebSocket
- **Multi-client Sync**: Changes sync instantly across all connected browsers
- **Responsive UI**: Works on desktop and mobile devices

## Hardware Requirements

- **Raspberry Pi 5** (4GB or 8GB RAM recommended)
- **MicroSD Card** (32GB+ Class 10 or better)
- **Power Supply** (USB-C 5V/5A official Pi 5 PSU recommended)
- **HDMI Cable** (for display output)
- **Ethernet** (recommended) or WiFi
- **Optional:** Active cooling (heatsink + fan) for sustained performance

## Software Requirements

- Raspberry Pi OS (64-bit, Bookworm or later)
- NDI SDK for Linux ARM64
- Python 3.11+

---

## Part 1: Base System Setup

### 1.1 Flash Raspberry Pi OS

1. Download [Raspberry Pi Imager](https://www.raspberrypi.com/software/)
2. Select **Raspberry Pi OS (64-bit)** with Desktop
3. Click gear icon for advanced options:
   - Set hostname: `ndi-monitor` (or your preference)
   - Enable SSH with password authentication
   - Set username: `nlc-atlantic-media` (or your preference)
   - Set password
   - Configure WiFi if needed
   - Set locale/timezone
4. Flash to SD card and boot the Pi

### 1.2 Initial System Update

```bash
sudo apt-get update
sudo apt-get upgrade -y
sudo reboot
```

### 1.3 Install System Dependencies

```bash
sudo apt-get install -y \
    python3-pip \
    python3-venv \
    python3-dev \
    python3-pygame \
    libavahi-client-dev \
    avahi-daemon \
    git \
    htop \
    build-essential \
    llvm
```

---

## Part 2: NDI SDK Installation

### 2.1 Download NDI SDK

```bash
cd ~
wget https://downloads.ndi.tv/SDK/NDI_SDK_Linux/Install_NDI_SDK_v6_Linux.tar.gz
tar -xzf Install_NDI_SDK_v6_Linux.tar.gz
```

### 2.2 Install NDI SDK

```bash
cd NDI\ SDK\ for\ Linux/
sudo ./Install_NDI_SDK_v6_Linux.sh
# Accept the license agreement
```

### 2.3 Install NDI Library System-Wide

```bash
# Find and copy the ARM64 library
sudo cp ~/NDI\ SDK\ for\ Linux/lib/aarch64-rpi4-linux-gnueabi/libndi.so.6 /usr/local/lib/libndi.so
sudo ldconfig
```

### 2.4 Verify Installation

```bash
ldconfig -p | grep ndi
# Should show: libndi.so (libc6,AArch64) => /usr/local/lib/libndi.so
```

---

## Part 3: Application Installation

### 3.1 Create Project Directory

```bash
mkdir -p ~/ndi-monitor
cd ~/ndi-monitor
```

### 3.2 Transfer Application Files

From your Mac (adjust paths as needed):
```bash
scp app.py display.py ndi.py index.html requirements.txt \
    nlc-atlantic-media@YOUR_PI_IP:~/ndi-monitor/
```

### 3.3 Create Python Virtual Environment

```bash
cd ~/ndi-monitor
python3 -m venv venv
source venv/bin/activate
```

### 3.4 Install Python Dependencies

```bash
pip install --upgrade pip
pip install uvicorn fastapi pillow numpy pygame numba llvmlite
```

### 3.5 Verify Installation

```bash
# Test NDI library loads
python3 -c "from ndi import NDISourceFinder; print('NDI OK')"

# Test numba
python3 -c "from numba import njit; print('Numba OK')"
```

---

## Part 4: Performance Tuning (config.txt)

### 4.1 Edit Boot Configuration

```bash
sudo nano /boot/firmware/config.txt
```

### 4.2 Add Performance Settings

Add these lines at the end of the file:

```ini
# NDI Monitor Performance Tuning
gpu_mem=256
arm_freq=2600
gpu_freq=950
over_voltage=4
force_turbo=0
```

**Settings Explained:**
| Setting | Value | Description |
|---------|-------|-------------|
| `gpu_mem` | 256 | GPU memory (ignored on Pi 5, uses unified memory) |
| `arm_freq` | 2600 | CPU overclock to 2.6GHz (default 2.4GHz) |
| `gpu_freq` | 950 | GPU overclock to 950MHz (default ~500MHz) |
| `over_voltage` | 4 | Voltage boost for stability (+0.2V) |
| `force_turbo` | 0 | Don't force max clocks when idle (saves power) |

### 4.3 Reboot to Apply

```bash
sudo reboot
```

### 4.4 Verify Overclock

```bash
vcgencmd measure_clock arm    # Should show ~2600000000
vcgencmd measure_clock core   # Should show ~950000000
vcgencmd measure_temp         # Monitor temperature
vcgencmd get_throttled        # 0x0 = no throttling
```

---

## Part 5: Web Service Setup (systemd)

### 5.1 Create Service File

```bash
sudo nano /etc/systemd/system/ndi-monitor.service
```

### 5.2 Service Configuration

```ini
[Unit]
Description=NDI Monitor Web Service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=nlc-atlantic-media
WorkingDirectory=/home/nlc-atlantic-media/ndi-monitor
Environment="PATH=/home/nlc-atlantic-media/ndi-monitor/venv/bin:/usr/local/bin:/usr/bin:/bin"
Environment="NDI_LIB_PATH=/usr/local/lib/libndi.so"
ExecStart=/home/nlc-atlantic-media/ndi-monitor/venv/bin/uvicorn app:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### 5.3 Enable and Start Service

```bash
sudo systemctl daemon-reload
sudo systemctl enable ndi-monitor
sudo systemctl start ndi-monitor
```

### 5.4 Verify Service

```bash
sudo systemctl status ndi-monitor
curl http://localhost:8000/health
# Should return: {"ok":true}
```

---

## Part 6: HDMI Display Autostart

### 6.1 Configure Desktop Autologin

```bash
sudo raspi-config nonint do_boot_behaviour B4
```

### 6.2 Configure LightDM

```bash
sudo mkdir -p /etc/lightdm/lightdm.conf.d
sudo nano /etc/lightdm/lightdm.conf.d/11-autologin.conf
```

Add:
```ini
[Seat:*]
autologin-user=nlc-atlantic-media
autologin-user-timeout=0
user-session=LXDE-pi
```

### 6.3 Enable Display Manager

```bash
sudo systemctl enable lightdm
sudo systemctl set-default graphical.target
```

### 6.4 Create Autostart Directory

```bash
mkdir -p ~/.config/autostart
```

### 6.5 Create Desktop Autostart Entry

```bash
nano ~/.config/autostart/ndi-display.desktop
```

Add:
```ini
[Desktop Entry]
Type=Application
Name=NDI Display
Comment=Start NDI HDMI display on login
Exec=env SDL_VIDEODRIVER=x11 NDI_LIB_PATH=/usr/local/lib/libndi.so /home/nlc-atlantic-media/ndi-monitor/venv/bin/python3 /home/nlc-atlantic-media/ndi-monitor/display.py
X-GNOME-Autostart-enabled=true
Terminal=false
```

### 6.6 Create LXDE Session Autostart (Backup)

```bash
mkdir -p ~/.config/lxsession/LXDE-pi
nano ~/.config/lxsession/LXDE-pi/autostart
```

Add:
```
@env SDL_VIDEODRIVER=x11 NDI_LIB_PATH=/usr/local/lib/libndi.so /home/nlc-atlantic-media/ndi-monitor/venv/bin/python3 /home/nlc-atlantic-media/ndi-monitor/display.py
```

### 6.7 Disable Conflicting Services

If you previously had a headless HDMI service:
```bash
sudo systemctl disable ndi-display.service 2>/dev/null || true
sudo rm /etc/systemd/system/ndi-display.service 2>/dev/null || true
sudo systemctl daemon-reload
```

### 6.8 Reboot and Test

```bash
sudo reboot
```

After reboot, the HDMI should show the NDI display automatically.

---

## Part 7: Verification Checklist

### System Status

```bash
# Check CPU frequency
vcgencmd measure_clock arm

# Check temperature
vcgencmd measure_temp

# Check throttling (0x0 = none)
vcgencmd get_throttled

# Check web service
systemctl is-active ndi-monitor

# Check HDMI display process
pgrep -af display.py

# Check display manager
systemctl is-active display-manager
```

### Expected Output

| Check | Expected Value |
|-------|----------------|
| CPU Frequency | ~2600 MHz |
| Temperature | < 70°C under load |
| Throttling | 0x0 |
| ndi-monitor service | active |
| display.py process | Running |
| display-manager | active |
| FPS on HDMI | 30-45 FPS |

### Web Interface

Open in browser: `http://YOUR_PI_IP:8000`

---

## Part 8: Troubleshooting

### HDMI Display Not Starting

```bash
# Check if display.py is running
pgrep -af display.py

# Check for errors
cat ~/.xsession-errors | tail -30

# Manual test (run from SSH with DISPLAY set)
DISPLAY=:0 SDL_VIDEODRIVER=x11 NDI_LIB_PATH=/usr/local/lib/libndi.so \
  ~/ndi-monitor/venv/bin/python3 ~/ndi-monitor/display.py
```

### Web Service Not Starting

```bash
# Check service status
sudo systemctl status ndi-monitor

# Check logs
sudo journalctl -u ndi-monitor -n 50 --no-pager
```

### NDI Library Not Found

```bash
# Verify library exists
ls -la /usr/local/lib/libndi.so

# Update linker cache
sudo ldconfig

# Test load
python3 -c "import ctypes; ctypes.CDLL('/usr/local/lib/libndi.so'); print('OK')"
```

### Low Frame Rate

1. Check network connection (use Ethernet)
2. Verify overclock settings took effect
3. Check CPU temperature for throttling
4. Ensure numba is installed: `pip show numba`

### Colors Wrong or Corrupted

The UYVY→RGB conversion requires `int32`. Verify `ndi.py` has:
```python
U = pairs[:, :, 0].astype(np.int32)
```

---

## Part 9: Maintenance Commands

### Update Application Files

```bash
# From Mac
scp app.py display.py ndi.py index.html \
    nlc-atlantic-media@YOUR_PI_IP:~/ndi-monitor/

# On Pi - restart services
sudo systemctl restart ndi-monitor
sudo reboot  # To restart HDMI display
```

### View Live Logs

```bash
# Web service logs
sudo journalctl -u ndi-monitor -f

# HDMI display logs
tail -f ~/.xsession-errors
```

### Check Resource Usage

```bash
htop  # Interactive process viewer
top -bn1 | head -20  # Quick snapshot
```

### Monitor Temperature

```bash
watch -n 1 vcgencmd measure_temp
```

---

## Part 10: Configuration File Locations

| File | Location | Purpose |
|------|----------|---------|
| Boot config | `/boot/firmware/config.txt` | Overclock, GPU settings |
| Web service | `/etc/systemd/system/ndi-monitor.service` | Web API autostart |
| Autologin | `/etc/lightdm/lightdm.conf.d/11-autologin.conf` | Desktop autologin |
| HDMI autostart | `~/.config/autostart/ndi-display.desktop` | HDMI display autostart |
| LXDE autostart | `~/.config/lxsession/LXDE-pi/autostart` | Backup HDMI autostart |
| App config | `~/.ndi-monitor-config.json` | Runtime settings (source, messages) |
| Python venv | `~/ndi-monitor/venv/` | Python dependencies |
| NDI library | `/usr/local/lib/libndi.so` | NDI SDK library |

---

## Quick Install Script

For convenience, here's a one-shot script that configures everything after the base files are transferred:

```bash
#!/bin/bash
# Run as the target user (not root)

set -e

USER=$(whoami)
HOME_DIR=$(eval echo ~$USER)
PROJECT_DIR="$HOME_DIR/ndi-monitor"

echo "=== NDI Monitor Pi 5 Setup ==="

# Create venv and install deps
cd "$PROJECT_DIR"
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install uvicorn fastapi pillow numpy pygame numba llvmlite

# Create autostart
mkdir -p ~/.config/autostart
cat > ~/.config/autostart/ndi-display.desktop << EOF
[Desktop Entry]
Type=Application
Name=NDI Display
Exec=env SDL_VIDEODRIVER=x11 NDI_LIB_PATH=/usr/local/lib/libndi.so $PROJECT_DIR/venv/bin/python3 $PROJECT_DIR/display.py
X-GNOME-Autostart-enabled=true
Terminal=false
EOF

mkdir -p ~/.config/lxsession/LXDE-pi
echo "@env SDL_VIDEODRIVER=x11 NDI_LIB_PATH=/usr/local/lib/libndi.so $PROJECT_DIR/venv/bin/python3 $PROJECT_DIR/display.py" > ~/.config/lxsession/LXDE-pi/autostart

# Create systemd service (needs sudo)
sudo tee /etc/systemd/system/ndi-monitor.service > /dev/null << EOF
[Unit]
Description=NDI Monitor Web Service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$PROJECT_DIR/venv/bin:/usr/local/bin:/usr/bin:/bin"
Environment="NDI_LIB_PATH=/usr/local/lib/libndi.so"
ExecStart=$PROJECT_DIR/venv/bin/uvicorn app:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable ndi-monitor
sudo systemctl start ndi-monitor

# Configure autologin
sudo raspi-config nonint do_boot_behaviour B4
sudo mkdir -p /etc/lightdm/lightdm.conf.d
sudo tee /etc/lightdm/lightdm.conf.d/11-autologin.conf > /dev/null << EOF
[Seat:*]
autologin-user=$USER
autologin-user-timeout=0
user-session=LXDE-pi
EOF

sudo systemctl enable lightdm
sudo systemctl set-default graphical.target

# Add performance tuning to config.txt
if ! grep -q "NDI Monitor Performance" /boot/firmware/config.txt; then
    sudo tee -a /boot/firmware/config.txt > /dev/null << EOF

# NDI Monitor Performance Tuning
gpu_mem=256
arm_freq=2600
gpu_freq=950
over_voltage=4
force_turbo=0
EOF
fi

echo "=== Setup Complete ==="
echo "Reboot to apply all changes: sudo reboot"
```

---

## Current Performance Benchmarks

On Raspberry Pi 5 (8GB) with these settings:

| Metric | Value |
|--------|-------|
| CPU Frequency | 2600 MHz |
| GPU Frequency | 950 MHz |
| Temperature (idle) | ~48°C |
| Temperature (load) | ~55°C |
| CPU Usage | ~150% (1.5 cores) |
| RAM Usage | ~400MB |
| HDMI FPS (1080p60 source) | 34-45 FPS |
| HDMI FPS (blanked) | 50+ FPS |

---

## Web Interface Features

### Display Section
- **Source List**: Grid of available NDI sources (auto-refreshes every 10s)
- **Refresh Sources**: Manual source discovery
- **Blank HDMI**: Full-width button at bottom, turns red when active

### System Section  
- **Selected Source**: Shows currently connected source
- **Health Status**: Connection state
- **Reboot Pi**: Restart the Raspberry Pi
- **Show FPS**: Toggle FPS overlay on HDMI display
- **No Connection Message**: Custom text shown when no source (supports variables)
- **Subtitle**: Secondary message line
- **Logs**: Real-time log viewer (pushed via WebSocket)

### Message Variables
Use these in the "No Connection" message:
- `<ip>` - Pi's IP address
- `<hostname>` - Pi's hostname  
- `<source>` - Selected source name
- `<time>` - Current time (HH:MM:SS)
- `<resolution>` - Display resolution
- `<width>` / `<height>` - Display dimensions

---

## Architecture

### Files

| File | Purpose |
|------|---------|
| `app.py` | FastAPI web server with WebSocket support |
| `display.py` | Pygame HDMI renderer |
| `ndi.py` | NDI SDK wrapper with numba-optimized UYVY conversion |
| `index.html` | Responsive web UI |
| `~/.ndi-monitor-config.json` | Shared configuration (both services read/write) |

### Communication Flow

```
┌─────────────┐     WebSocket      ┌─────────────┐
│   Browser   │◄──────────────────►│   app.py    │
│  (Web UI)   │   Config + Logs    │  (FastAPI)  │
└─────────────┘                    └──────┬──────┘
                                          │
                                   Config File
                                   (JSON on disk)
                                          │
                                   ┌──────┴──────┐
                                   │  display.py │
                                   │  (Pygame)   │
                                   └──────┬──────┘
                                          │
                                       HDMI
                                          │
                                   ┌──────┴──────┐
                                   │   Monitor   │
                                   └─────────────┘
```

### WebSocket Events

The web UI connects to `/ws` and receives:
- `{"type": "config", "data": {...}}` - Configuration updates
- `{"type": "logs", "data": [...]}` - Log entries

No polling required - all updates are pushed in real-time.

---

## Fan Control

The Pi 5 has configurable fan control:

### Check Current State
```bash
# Fan state (0-4, 0=off)
cat /sys/class/thermal/cooling_device0/cur_state

# Current temperature (millidegrees)
cat /sys/class/thermal/thermal_zone0/temp
```

### Configure Temperature Thresholds

Add to `/boot/firmware/config.txt`:
```ini
# Fan speed thresholds (temp in millidegrees, speed 0-255)
dtparam=fan_temp0=50000
dtparam=fan_temp0_hyst=5000
dtparam=fan_temp0_speed=75
dtparam=fan_temp1=60000
dtparam=fan_temp1_hyst=5000
dtparam=fan_temp1_speed=125
dtparam=fan_temp2=67500
dtparam=fan_temp2_hyst=5000
dtparam=fan_temp2_speed=175
dtparam=fan_temp3=75000
dtparam=fan_temp3_hyst=5000
dtparam=fan_temp3_speed=250
```

### Always-On Max Speed
```ini
dtparam=fan_temp0=0
dtparam=fan_temp0_speed=255
```

---

*Last updated: January 2026*
