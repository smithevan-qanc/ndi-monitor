# NDI Monitor - Raspberry Pi Edition

**Full-featured NDI display system for Raspberry Pi 5 with HDMI output and web control.**

## Features

- 📺 **HDMI Display** - Full-screen NDI video via pygame with 34-45 FPS
- 🌐 **Web Control Panel** - Responsive UI works on desktop and mobile
- 🔌 **WebSocket Updates** - Real-time config sync across all clients (no polling)
- 🖥️ **Multi-client Support** - Multiple browsers sync instantly
- 🎛️ **HDMI Blanking** - Smooth fade-to-black with visual feedback
- 📊 **FPS Overlay** - Optional FPS counter on HDMI (toggleable via web)
- 💬 **Custom Messages** - Configurable "No Connection" text with variables
- 📋 **Live Logs** - Real-time log streaming via WebSocket
- ⚡ **Optimized** - Numba JIT-compiled UYVY→RGB conversion

## Quick Start

### Web Interface
Open in browser: `http://YOUR_PI_IP:8000`

### Common Commands
```bash
# Restart web service
sudo systemctl restart ndi-monitor

# Restart HDMI display
sudo reboot

# Check status
sudo systemctl status ndi-monitor

# View logs
sudo journalctl -u ndi-monitor -f
```

## Architecture

```
┌─────────────┐     WebSocket      ┌─────────────┐
│   Browser   │◄──────────────────►│   app.py    │
│  (Web UI)   │   Config + Logs    │  (FastAPI)  │
└─────────────┘                    └──────┬──────┘
                                          │
                                   ~/.ndi-monitor-config.json
                                          │
                                   ┌──────┴──────┐
                                   │  display.py │──► HDMI Output
                                   │  (Pygame)   │
                                   └─────────────┘
```

## Files

| File | Purpose |
|------|---------|
| `app.py` | FastAPI server with WebSocket support |
| `display.py` | Pygame HDMI renderer |
| `ndi.py` | NDI SDK wrapper (numba-optimized) |
| `index.html` | Responsive web UI |
| `requirements.txt` | Python dependencies |

## Hardware Requirements

- Raspberry Pi 5 (4GB or 8GB)
- HDMI display
- Ethernet connection (recommended)
- Active cooling (recommended for sustained use)

## Documentation

- [QUICK_START.md](QUICK_START.md) - Common commands and quick reference
- [RASPBERRY_PI_5_SETUP.md](RASPBERRY_PI_5_SETUP.md) - Complete installation guide

## Performance

| Metric | Value |
|--------|-------|
| HDMI FPS (1080p60 source) | 34-45 FPS |
| HDMI FPS (blanked) | 50+ FPS |
| CPU Usage | ~150% (1.5 cores) |
| RAM Usage | ~400MB |

With overclock settings (2.6GHz CPU, 950MHz GPU).

## Web UI

### Display Section
- Source grid with live discovery
- Full-width Blank HDMI button (red when active)

### System Section
- Source selection status
- Reboot button
- FPS toggle checkbox
- Custom "No Connection" message editor
- Real-time logs

### Message Variables
- `<ip>` - Pi's IP address
- `<hostname>` - Pi's hostname
- `<source>` - Selected source name
- `<time>` - Current time

## License

MIT
