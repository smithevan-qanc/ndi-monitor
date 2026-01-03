# NDI Monitor - Quick Start (Raspberry Pi)

## Overview

NDI Monitor displays NDI video sources on an HDMI display with a web-based control panel.

- **Web UI**: `http://YOUR_PI_IP:8000`
- **HDMI Output**: Full-screen NDI video via pygame

## Quick Commands

### Service Management

```bash
# Restart web service (picks up app.py/index.html changes)
sudo systemctl restart ndi-monitor

# Restart HDMI display (picks up display.py changes)
sudo reboot

# Check service status
sudo systemctl status ndi-monitor

# View live logs
sudo journalctl -u ndi-monitor -f
```

### Update Files from Mac

```bash
# Transfer updated files
scp app.py display.py ndi.py index.html \
    nlc-atlantic-media@192.168.1.11:/home/nlc-atlantic-media/ndi-monitor/

# Restart services
ssh nlc-atlantic-media@192.168.1.11 'sudo systemctl restart ndi-monitor'
```

### Check System Health

```bash
# CPU temp
vcgencmd measure_temp

# CPU frequency
vcgencmd measure_clock arm

# Throttling status (0x0 = OK)
vcgencmd get_throttled

# Fan state (0-4)
cat /sys/class/thermal/cooling_device0/cur_state
```

## Web UI Features

| Feature | Description |
|---------|-------------|
| **Source List** | Click to select NDI source |
| **Blank HDMI** | Fade to black (button turns red when active) |
| **Show FPS** | Toggle FPS overlay on HDMI |
| **No Connection Message** | Custom text with variables: `<ip>`, `<hostname>`, `<time>` |
| **Logs** | Real-time log viewer |

## Configuration

Settings are stored in `~/.ndi-monitor-config.json`:

```json
{
  "selected_source": "SOURCE_NAME (IP)",
  "hdmi_blank": false,
  "show_fps": true,
  "no_connection_message": "No NDI Source",
  "no_connection_subtext": "Configure via web interface"
}
```

Both `app.py` (web service) and `display.py` (HDMI) read this file.

## File Locations

| File | Purpose |
|------|---------|
| `/home/nlc-atlantic-media/ndi-monitor/` | Application files |
| `~/.ndi-monitor-config.json` | Runtime configuration |
| `/usr/local/lib/libndi.so` | NDI SDK library |
| `/boot/firmware/config.txt` | Overclock settings |
| `/etc/systemd/system/ndi-monitor.service` | Web service definition |
| `~/.config/autostart/ndi-display.desktop` | HDMI autostart |

## Troubleshooting

### Web UI not loading
```bash
sudo systemctl status ndi-monitor
sudo journalctl -u ndi-monitor -n 50
```

### HDMI not displaying
```bash
pgrep -af display.py
cat ~/.xsession-errors | tail -30
```

### Low frame rate
- Check temperature: `vcgencmd measure_temp` (should be < 70°C)
- Check throttling: `vcgencmd get_throttled` (should be 0x0)
- Verify network: Use Ethernet, not WiFi

### NDI sources not found
- Ensure sources are on same network
- Check firewall: NDI uses TCP 5960 and mDNS
- Verify source is sending (not just receiving)

## Full Documentation

See [RASPBERRY_PI_5_SETUP.md](RASPBERRY_PI_5_SETUP.md) for complete setup instructions.
