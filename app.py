import threading
import time
from typing import Optional

import json
import os
import subprocess
from pathlib import Path
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse

from ndi import NDIReceiver, NDISourceFinder
import logging
from collections import deque
from threading import RLock
from datetime import datetime

app = FastAPI()

# WebSocket connection manager for real-time config updates
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self._lock = threading.Lock()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        with self._lock:
            self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)

    async def broadcast_config(self):
        """Broadcast current config to all connected clients."""
        config = _get_config_dict()
        message = json.dumps({"type": "config", "data": config})
        await self._broadcast_message(message)

    async def broadcast_logs(self, logs: list):
        """Broadcast logs to all connected clients."""
        message = json.dumps({"type": "logs", "data": logs})
        await self._broadcast_message(message)

    async def _broadcast_message(self, message: str):
        """Send a message to all connected clients."""
        with self._lock:
            connections = list(self.active_connections)
        
        dead = []
        for conn in connections:
            try:
                await conn.send_text(message)
            except Exception:
                dead.append(conn)
        
        if dead:
            with self._lock:
                for conn in dead:
                    if conn in self.active_connections:
                        self.active_connections.remove(conn)

ws_manager = ConnectionManager()

# Background task to handle broadcasts from sync context
import asyncio
_broadcast_queue: asyncio.Queue = None

async def _broadcast_worker():
    """Background worker that processes broadcast requests."""
    global _broadcast_queue, _log_broadcast_queue
    _broadcast_queue = asyncio.Queue()
    _log_broadcast_queue = asyncio.Queue()
    
    async def config_worker():
        while True:
            await _broadcast_queue.get()
            try:
                await ws_manager.broadcast_config()
            except Exception as e:
                logging.getLogger("app").warning(f"Config broadcast failed: {e}")
    
    async def logs_worker():
        while True:
            await _log_broadcast_queue.get()
            try:
                logs = ring_handler.snapshot()
                await ws_manager.broadcast_logs(logs)
            except Exception as e:
                pass  # Don't log broadcast failures (would cause infinite loop)
    
    await asyncio.gather(config_worker(), logs_worker())

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(_broadcast_worker())

# Serve static assets (e.g., splash image)
app.mount("/static", StaticFiles(directory="static"), name="static")

finder = NDISourceFinder()
receiver_lock = threading.Lock()
receiver: Optional[NDIReceiver] = None
selected_source_name: Optional[str] = None

settings_lock = threading.Lock()
jpeg_quality: int = 80
output_width: int = 0
output_height: int = 0

# Message customization for HDMI display
message_lock = threading.Lock()
no_connection_message: str = "No NDI Source"
no_connection_subtext: str = "Configure via web interface"

# HDMI blanking control
hdmi_lock = threading.Lock()
hdmi_blank: bool = False

# In-memory log buffer (current session)
_log_broadcast_queue: asyncio.Queue = None

class _RingLogHandler(logging.Handler):
    def __init__(self, capacity: int = 200):
        super().__init__()
        self.capacity = capacity
        self.buffer = deque(maxlen=capacity)
        self._id = 0
        self._lock = RLock()

    def emit(self, record: logging.LogRecord):
        try:
            msg = self.format(record)
        except Exception:  # pragma: no cover
            msg = record.getMessage()
        # Skip noisy entries
        if not _should_log(record, msg):
            return
        with self._lock:
            self._id += 1
            self.buffer.append({
                "id": self._id,
                "ts": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                "level": record.levelname,
                "logger": record.name,
                "msg": msg,
            })
        # Trigger log broadcast
        _broadcast_logs()

    def snapshot(self):
        with self._lock:
            return list(self.buffer)


ring_handler = _RingLogHandler(200)
ring_handler.setFormatter(logging.Formatter("%(message)s"))

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(ring_handler)

# Attach to uvicorn loggers as well
for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
    logging.getLogger(name).addHandler(ring_handler)

# Filter noisy access logs in the ring buffer
FILTER_SUBSTRINGS = [
    "/api/sources",
    "/api/logs",
]

def _should_log(record: logging.LogRecord, formatted: str) -> bool:
    if record.name == "uvicorn.access":
        for s in FILTER_SUBSTRINGS:
            if s in formatted:
                return False
    return True

# Persistent config shared with display.py
CONFIG_FILE = Path.home() / ".ndi-monitor-config.json"

def _save_config_fields(update: dict):
    """Atomically update the shared config file with provided fields.
    Preserves existing keys and ensures durability across reboots.
    """
    try:
        current = {}
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                try:
                    current = json.load(f) or {}
                except Exception:
                    current = {}

        current.update(update or {})
        tmp = CONFIG_FILE.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(current, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())

        # Atomic replace
        try:
            os.replace(tmp, CONFIG_FILE)
        finally:
            if tmp.exists():
                try:
                    tmp.unlink()
                except Exception:
                    pass
    except Exception as e:
        logging.getLogger("app").warning(f"Failed to save config: {e}")


def _load_config_file() -> dict:
    """Load the shared config file."""
    try:
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f) or {}
    except Exception as e:
        logging.getLogger("app").warning(f"Failed to load config: {e}")
    return {}


def _get_config_dict() -> dict:
    """Get config as a dictionary for API/WebSocket."""
    config = _load_config_file()
    return {
        "selected_source": config.get("selected_source"),
        "hdmi_blank": config.get("hdmi_blank", False),
        "no_connection_message": config.get("no_connection_message", "No NDI Source"),
        "no_connection_subtext": config.get("no_connection_subtext", "Configure via web interface"),
        "show_fps": config.get("show_fps", True),
        "device_name": config.get("device_name", "")
    }


def _broadcast_config_update():
    """Broadcast config update to all WebSocket clients."""
    global _broadcast_queue
    if _broadcast_queue is not None:
        try:
            _broadcast_queue.put_nowait(True)
        except Exception:
            pass


def _broadcast_logs():
    """Broadcast logs to all WebSocket clients."""
    global _log_broadcast_queue
    if _log_broadcast_queue is not None:
        try:
            _log_broadcast_queue.put_nowait(True)
        except Exception:
            pass


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    # Send initial config and logs on connect
    config = _get_config_dict()
    await websocket.send_text(json.dumps({"type": "config", "data": config}))
    logs = ring_handler.snapshot()
    await websocket.send_text(json.dumps({"type": "logs", "data": logs}))
    try:
        while True:
            # Keep connection alive, handle any incoming messages
            data = await websocket.receive_text()
            # Client can request config refresh
            if data == "refresh":
                config = _get_config_dict()
                await websocket.send_text(json.dumps({"type": "config", "data": config}))
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


@app.get("/api/config")
def get_config():
    """Get all configuration settings for UI sync."""
    return _get_config_dict()


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()


@app.get("/api/sources")
def list_sources():
    sources = finder.list_sources(timeout_ms=500)
    logging.getLogger("app").debug(f"Discovered sources: {len(sources)}")
    return {"sources": sources}


@app.get("/api/selected")
def get_selected():
    return {"selected": selected_source_name}


@app.post("/api/select")
def select_source(payload: dict):
    global receiver, selected_source_name

    name = (payload or {}).get("name")
    if not name or not isinstance(name, str):
        raise HTTPException(status_code=400, detail="Missing 'name'")

    # Always save to config first so display.py picks it up
    # and so selection persists even if receiver creation fails
    _save_config_fields({"selected_source": name})
    selected_source_name = name
    _broadcast_config_update()

    try:
        with receiver_lock:
            if receiver is not None:
                try:
                    receiver.close()
                except Exception:
                    pass
                receiver = None

            receiver = NDIReceiver(source_name=name)
        logging.getLogger("app").info(f"Selected source: {name}")
        return {"ok": True, "selected": selected_source_name}
    except Exception as e:
        logging.getLogger("app").warning(f"Failed to connect to {name}: {e}")
        # Return success anyway - config is saved, display.py will handle it
        return {"ok": True, "selected": selected_source_name, "pending": True}


@app.get("/api/settings")
def get_settings():
    with settings_lock:
        q = int(jpeg_quality)
        w = int(output_width)
        h = int(output_height)
    return {"jpegQuality": q, "outputWidth": w, "outputHeight": h}


@app.post("/api/settings")
def update_settings(payload: dict):
    global jpeg_quality, output_width, output_height
    if payload is None:
        raise HTTPException(status_code=400, detail="Missing payload")

    if "jpegQuality" in payload:
        try:
            q = int(payload["jpegQuality"])
        except Exception:
            raise HTTPException(status_code=400, detail="jpegQuality must be an integer")

        # Pillow generally behaves well in 1..95; clamp to a sane range.
        q = max(20, min(95, q))
        with settings_lock:
            jpeg_quality = q

    # Optional forced output size for MJPEG (0/0 = native)
    if "outputWidth" in payload or "outputHeight" in payload:
        try:
            w = int(payload.get("outputWidth", 0) or 0)
            h = int(payload.get("outputHeight", 0) or 0)
        except Exception:
            raise HTTPException(status_code=400, detail="outputWidth/outputHeight must be integers")

        # Only allow either both set or both zero.
        if (w == 0) != (h == 0):
            raise HTTPException(status_code=400, detail="outputWidth and outputHeight must both be set (or both 0)")

        # Clamp to reasonable values.
        if w != 0:
            w = max(160, min(3840, w))
            h = max(120, min(2160, h))

        with settings_lock:
            output_width = w
            output_height = h
    logging.getLogger("app").info(f"Settings updated: quality={jpeg_quality}, size={output_width}x{output_height}")

    return get_settings()


@app.get("/api/message")
def get_message():
    with message_lock:
        return {
            "noConnectionMessage": no_connection_message,
            "noConnectionSubtext": no_connection_subtext,
        }


@app.post("/api/message")
def update_message(payload: dict):
    global no_connection_message, no_connection_subtext
    if payload is None:
        raise HTTPException(status_code=400, detail="Missing payload")

    msg = str(payload.get("noConnectionMessage", "")).strip()
    sub = str(payload.get("noConnectionSubtext", "")).strip()

    with message_lock:
        if msg:
            no_connection_message = msg
        else:
            no_connection_message = "No NDI Source"
        no_connection_subtext = sub

    # Persist to config file for display.py
    _save_config_fields({
        "no_connection_message": no_connection_message,
        "no_connection_subtext": no_connection_subtext,
    })
    _broadcast_config_update()

    logging.getLogger("app").info("No-connection message updated")
    return get_message()


@app.post("/api/reboot")
def reboot_system():
    try:
        # Requires passwordless sudo for /sbin/reboot
        subprocess.Popen(["sudo", "/sbin/reboot"])  # do not wait; connection will drop
        logging.getLogger("app").warning("Reboot requested via API")
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reboot failed: {e}")


@app.get("/api/blank")
def get_hdmi():
    with hdmi_lock:
        return {"blank": bool(hdmi_blank)}


@app.post("/api/blank")
def set_hdmi(payload: dict):
    global hdmi_blank
    if payload is None or "blank" not in payload:
        raise HTTPException(status_code=400, detail="Missing 'blank'")

    val = bool(payload.get("blank"))
    with hdmi_lock:
        hdmi_blank = val

    # Persist to config for display.py to pick up
    _save_config_fields({"hdmi_blank": hdmi_blank})
    _broadcast_config_update()

    logging.getLogger("app").info(f"HDMI blank set to: {hdmi_blank}")
    return get_hdmi()


@app.get("/api/fps")
def get_fps():
    """Get current show_fps setting"""
    config = _load_config_file()
    return {"show_fps": config.get("show_fps", True)}


@app.post("/api/fps")
def set_fps(payload: dict):
    """Set show_fps setting"""
    if payload is None or "show_fps" not in payload:
        raise HTTPException(status_code=400, detail="Missing 'show_fps'")
    val = bool(payload.get("show_fps"))
    _save_config_fields({"show_fps": val})
    _broadcast_config_update()
    logging.getLogger("app").info(f"Show FPS set to: {val}")
    return {"show_fps": val}


@app.get("/api/device_name")
def get_device_name():
    """Get current device name setting"""
    config = _load_config_file()
    return {"device_name": config.get("device_name", "")}


@app.post("/api/device_name")
def set_device_name(payload: dict):
    """Set device name setting"""
    if payload is None or "device_name" not in payload:
        raise HTTPException(status_code=400, detail="Missing 'device_name'")
    val = str(payload.get("device_name", "")).strip()
    _save_config_fields({"device_name": val})
    _broadcast_config_update()
    logging.getLogger("app").info(f"Device name set to: {val}")
    return {"device_name": val}


@app.get("/api/resolution")
def get_resolution():
    """Get current and available display resolutions via xrandr"""
    try:
        result = subprocess.run(
            ["xrandr"],
            capture_output=True,
            text=True,
            timeout=5,
            env={**os.environ, "DISPLAY": ":0"}
        )
        if result.returncode != 0:
            raise HTTPException(status_code=500, detail="xrandr failed")
        
        lines = result.stdout.strip().split("\n")
        current = None
        resolutions = []
        
        for line in lines:
            # Current resolution line looks like: "Screen 0: ... current 1920 x 1080 ..."
            if "current" in line.lower() and "screen" in line.lower():
                import re
                match = re.search(r'current\s+(\d+)\s*x\s*(\d+)', line, re.IGNORECASE)
                if match:
                    current = f"{match.group(1)}x{match.group(2)}"
            
            # Resolution lines start with whitespace and contain resolution + refresh rate
            if line.startswith("   "):
                parts = line.split()
                if parts and "x" in parts[0].lower():
                    res = parts[0]
                    if res not in resolutions:
                        resolutions.append(res)
        
        return {"current": current, "available": resolutions}
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="xrandr timed out")
    except Exception as e:
        logging.getLogger("app").warning(f"Failed to get resolution: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/resolution")
def set_resolution(payload: dict):
    """Set display resolution via xrandr - requires display service restart"""
    if payload is None or "resolution" not in payload:
        raise HTTPException(status_code=400, detail="Missing 'resolution'")
    
    resolution = str(payload.get("resolution", "")).strip()
    if not resolution or "x" not in resolution.lower():
        raise HTTPException(status_code=400, detail="Invalid resolution format")
    
    try:
        # First get the output name (usually HDMI-A-1 on Pi 5)
        result = subprocess.run(
            ["xrandr"],
            capture_output=True,
            text=True,
            timeout=5,
            env={**os.environ, "DISPLAY": ":0"}
        )
        
        output_name = None
        for line in result.stdout.split("\n"):
            if " connected" in line:
                output_name = line.split()[0]
                break
        
        if not output_name:
            raise HTTPException(status_code=500, detail="No connected display found")
        
        # Stop the display service first so it releases the screen
        subprocess.run(
            ["sudo", "systemctl", "stop", "ndi-display"],
            capture_output=True,
            timeout=10
        )
        
        # Brief pause to let display release
        time.sleep(0.5)
        
        # Set the resolution
        result = subprocess.run(
            ["xrandr", "--output", output_name, "--mode", resolution],
            capture_output=True,
            text=True,
            timeout=10,
            env={**os.environ, "DISPLAY": ":0"}
        )
        
        if result.returncode != 0:
            # Try to restart display service even if xrandr failed
            subprocess.run(["sudo", "systemctl", "start", "ndi-display"], capture_output=True, timeout=10)
            raise HTTPException(status_code=500, detail=f"xrandr failed: {result.stderr}")
        
        # Restart the display service to pick up new resolution
        subprocess.run(
            ["sudo", "systemctl", "start", "ndi-display"],
            capture_output=True,
            timeout=10
        )
        
        logging.getLogger("app").info(f"Resolution set to: {resolution}")
        return {"ok": True, "resolution": resolution}
    except subprocess.TimeoutExpired:
        # Try to restart display service on timeout
        subprocess.run(["sudo", "systemctl", "start", "ndi-display"], capture_output=True, timeout=10)
        raise HTTPException(status_code=500, detail="xrandr timed out")
    except HTTPException:
        raise
    except Exception as e:
        logging.getLogger("app").warning(f"Failed to set resolution: {e}")
        # Try to restart display service on error
        subprocess.run(["sudo", "systemctl", "start", "ndi-display"], capture_output=True, timeout=10)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/logs")
def get_logs():
    return {"logs": ring_handler.snapshot()}


@app.get("/mjpeg")
def mjpeg():
    def gen():
        boundary = b"frame"
        while True:
            with receiver_lock:
                r = receiver

            if r is None:
                time.sleep(0.1)
                continue

            with settings_lock:
                q = int(jpeg_quality)
                w = int(output_width)
                h = int(output_height)

            frame = r.get_jpeg_frame(timeout_ms=1000, jpeg_quality=q, output_width=w, output_height=h)
            if frame is None:
                time.sleep(0.01)
                continue

            yield (
                b"--" + boundary + b"\r\n"
                b"Content-Type: image/jpeg\r\n"
                b"Content-Length: " + str(len(frame)).encode("ascii") + b"\r\n\r\n" +
                frame + b"\r\n"
            )

    return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/health")
def health():
    return JSONResponse({"ok": True})
