"""
Direct HDMI display for NDI streams on Raspberry Pi
Renders video frames directly to the framebuffer without browser overhead
"""
import os
import socket
import time
import json
import signal
import sys
from pathlib import Path
from typing import Optional

import pygame
import numpy as np

from ndi import NDIReceiver, NDISourceFinder

# Configuration file for persistence
CONFIG_FILE = Path.home() / ".ndi-monitor-config.json"


class NDIDisplay:
    def __init__(self):
        self.running = True
        self.receiver: Optional[NDIReceiver] = None
        self.finder = NDISourceFinder()
        self.screen = None
        self.selected_source = None
        self.no_connection_message = "No NDI Source"
        self.no_connection_subtext = "Configure via web interface"
        self.hdmi_blank = False
        self._prev_hdmi_blank = False
        self.blank_alpha = 0.0  # 0..255
        self.show_fps = True  # Toggle for FPS overlay
        self.blank_transition_ms = 400
        self.overlay = None
        self._last_alpha_ts = time.time()
        self._fade_full_emitted = False
        self._fade_clear_emitted = False
        # FPS tracking
        self._fps_count = 0
        self._fps_last_ts = time.time()
        self._fps_value = 0.0
        self._fps_font = None
        self.last_config_check = 0
        self.config_check_interval = 1.00  # Check config ~1x/sec for responsiveness
        
        # Frame buffer caching for performance
        self._cached_frame_size = (0, 0)
        self._cached_scaled_size = (0, 0)
        self._frame_surface = None
        self._scaled_surface = None
        
        # Load saved configuration
        self.load_config()
        
        # Initialize pygame display
        self.init_display()
        
        # Set up signal handlers for clean shutdown
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
    def init_display(self):
        """Initialize pygame display for direct framebuffer rendering"""
        # Prefer X11 for consistent alpha and performance unless overridden
        driver = os.environ.get('SDL_VIDEODRIVER') or 'x11'
        os.environ['SDL_VIDEODRIVER'] = driver
        
        pygame.init()
        
        # Force 1080p rendering for performance - display will upscale
        # This dramatically reduces CPU usage compared to 4K rendering
        self.width = 1920
        self.height = 1080
        
        self.screen = pygame.display.set_mode(
            (self.width, self.height),
            pygame.FULLSCREEN | pygame.HWSURFACE | pygame.DOUBLEBUF | pygame.SCALED
        )
        
        # Prepare overlay for fade-to-black using constant alpha
        try:
            self.overlay = pygame.Surface((self.width, self.height))
            self.overlay.fill((0, 0, 0))
            print("🟦 Overlay surface ready for fade")
        except Exception as e:
            print(f"⚠️  Overlay init failed: {e}")
            self.overlay = None
        
        pygame.mouse.set_visible(False)
        pygame.display.set_caption("NDI Monitor")
        try:
            self._fps_font = pygame.font.Font(None, 28)
        except Exception:
            self._fps_font = None
        
        print(f"✅ Display initialized: {self.width}x{self.height} (driver={driver})")

    def get_local_ip(self) -> str:
        """Best-effort to get the primary local IP address"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            try:
                return socket.gethostbyname(socket.gethostname())
            except Exception:
                return "127.0.0.1"

    def format_template(self, template: str) -> str:
        """Replace variable tokens in the message template"""
        if not template:
            return template
        context = {
            "ip": self.get_local_ip(),
            "hostname": socket.gethostname(),
            "source": self.selected_source or "",
            "width": str(getattr(self, 'width', 0)),
            "height": str(getattr(self, 'height', 0)),
            "resolution": f"{getattr(self, 'width', 0)}x{getattr(self, 'height', 0)}",
            "time": time.strftime("%H:%M:%S"),
        }
        msg = str(template)
        for k, v in context.items():
            msg = msg.replace(f"<{k}>", v)
        return msg
    
    def load_config(self):
        try:
            if CONFIG_FILE.exists():
                with open(CONFIG_FILE, 'r') as f:
                    config = json.load(f)
                    self.selected_source = config.get('selected_source')
                    self.no_connection_message = config.get('no_connection_message', self.no_connection_message)
                    self.no_connection_subtext = config.get('no_connection_subtext', self.no_connection_subtext)
                    self.hdmi_blank = bool(config.get('hdmi_blank', self.hdmi_blank))
                    self.show_fps = config.get('show_fps', True)
                    print(f"📋 Loaded config: source={self.selected_source}")
                    # Connect to source on startup if one is configured
                    if self.selected_source:
                        self.connect_to_source()
        except Exception as e:
            print(f"⚠️  Could not load config: {e}")

    def check_config_update(self):
        """Check if configuration has been updated via web interface"""
        current_time = time.time()
        if current_time - self.last_config_check < self.config_check_interval:
            return
        
        self.last_config_check = current_time
        
        try:
            if CONFIG_FILE.exists():
                with open(CONFIG_FILE, 'r') as f:
                    config = json.load(f)
                    new_source = config.get('selected_source')
                    self.no_connection_message = config.get('no_connection_message', self.no_connection_message)
                    self.no_connection_subtext = config.get('no_connection_subtext', self.no_connection_subtext)
                    self.show_fps = config.get('show_fps', True)
                    new_blank = bool(config.get('hdmi_blank', self.hdmi_blank))
                    if new_blank != self.hdmi_blank:
                        self.hdmi_blank = new_blank
                        self._prev_hdmi_blank = new_blank
                        # Reset fade completion flags when state changes
                        self._fade_full_emitted = False
                        self._fade_clear_emitted = False
                        print(f"🌓 HDMI blank changed: {self.hdmi_blank}")
                    
                    if new_source != self.selected_source:
                        print(f"🔄 Source changed to: {new_source}")
                        self.selected_source = new_source
                        self.connect_to_source()
        except Exception as e:
            pass  # Ignore config read errors
    
    def connect_to_source(self):
        """Connect to the selected NDI source"""
        if self.receiver:
            self.receiver.close()
            self.receiver = None
        
        if not self.selected_source:
            return
        
        try:
            self.receiver = NDIReceiver(source_name=self.selected_source)
            print(f"✅ Connected to: {self.selected_source}")
        except Exception as e:
            print(f"❌ Failed to connect to {self.selected_source}: {e}")
            self.receiver = None
    
    def auto_connect(self):
        """Automatically connect to available source if none selected"""
        if self.selected_source:
            return
        
        try:
            sources = self.finder.list_sources(timeout_ms=2000)
            if sources:
                self.selected_source = sources[0]
                print(f"🔍 Auto-connecting to: {self.selected_source}")
                self.connect_to_source()
        except Exception as e:
            print(f"⚠️  Auto-connect failed: {e}")
    
    def render_text(self, text: str, y_offset: int = 0, font_size: int = 56, color: tuple = (80, 80, 80)):
        """Render centered text on screen"""
        try:
            font = pygame.font.Font(None, font_size)
            text_surface = font.render(text, True, color)
            text_rect = text_surface.get_rect(center=(self.width // 2, self.height // 2 + y_offset))
            self.screen.blit(text_surface, text_rect)
        except Exception:
            pass
    
    def render_frame(self):
        """Get and render a frame from NDI receiver (optimized)"""
        # If fully blanked, skip expensive frame processing but maintain frame rate
        fully_blanked = self.hdmi_blank and self.blank_alpha >= 255.0
        
        if fully_blanked:
            # Just fill black, skip NDI frame processing
            self.screen.fill((0, 0, 0))
            time.sleep(0.002)  # Minimal sleep, let vsync handle timing
        elif not self.receiver:
            # No connection - show message
            self.screen.fill((0, 0, 0))
            self.render_text(self.format_template(self.no_connection_message) or "No NDI Source", 0, font_size=45, color=(80, 80, 80))
            if self.no_connection_subtext:
                self.render_text(self.format_template(self.no_connection_subtext), 50, font_size=32, color=(60, 60, 60))
        else:
            try:
                # Get raw RGB frame for higher throughput
                result = self.receiver.get_rgb_frame(timeout_ms=16)
                if result is None:
                    # No frame available; light sleep to avoid busy-wait
                    time.sleep(0.002)
                else:
                    rgb_array, (fw, fh) = result
                    frame_size = (fw, fh)
                    
                    # Recalculate scaled size if frame size changed
                    if self._cached_frame_size != frame_size:
                        self._cached_frame_size = frame_size
                        scale = min(self.width / fw, self.height / fh)
                        self._cached_scaled_size = (int(fw * scale), int(fh * scale))
                    
                    # Create surface from RGB buffer (pygame handles format correctly)
                    pygame_img = pygame.image.frombuffer(rgb_array.tobytes(), frame_size, "RGB")
                    
                    # Scale to cached size
                    if self._cached_scaled_size != frame_size:
                        scaled_img = pygame.transform.scale(pygame_img, self._cached_scaled_size)
                    else:
                        scaled_img = pygame_img
                    
                    # Center on screen
                    x = (self.width - self._cached_scaled_size[0]) // 2
                    y = (self.height - self._cached_scaled_size[1]) // 2
                    
                    # Render
                    self.screen.fill((0, 0, 0))
                    self.screen.blit(scaled_img, (x, y))
            except Exception as e:
                print(f"⚠️  Frame render error: {e}")
                time.sleep(0.01)

        # Apply fade-to-black overlay
        try:
            now = time.time()
            dt = max(0.0, now - (self._last_alpha_ts or now))
            self._last_alpha_ts = now
            step = 255.0 * dt / (self.blank_transition_ms / 1000.0)
            if self.hdmi_blank:
                self.blank_alpha = min(255.0, self.blank_alpha + step)
                if self.blank_alpha >= 254.0 and not self._fade_full_emitted:
                    self.blank_alpha = 255.0
                    self._fade_full_emitted = True
                    self._fade_clear_emitted = False
                    print("🌑 Fade complete: black")
            else:
                self.blank_alpha = max(0.0, self.blank_alpha - step)
                if self.blank_alpha <= 1.0 and not self._fade_clear_emitted:
                    self.blank_alpha = 0.0
                    self._fade_clear_emitted = True
                    self._fade_full_emitted = False
                    print("🌕 Fade cleared: video visible")

            if self.overlay is not None:
                a = int(self.blank_alpha)
                if a > 0:
                    self.overlay.set_alpha(a)
                    self.screen.blit(self.overlay, (0, 0))
            elif self.hdmi_blank:
                # Fallback if overlay isn't supported
                self.screen.fill((0, 0, 0))
        except Exception as e:
            print(f"⚠️  Fade error: {e}")
            if self.hdmi_blank:
                self.screen.fill((0, 0, 0))

        # Update and draw FPS overlay (before flip)
        try:
            self._fps_count += 1
            now = time.time()
            if now - self._fps_last_ts >= 1.0:
                elapsed = now - self._fps_last_ts
                self._fps_value = self._fps_count / max(elapsed, 1e-3)
                self._fps_last_ts = now
                self._fps_count = 0
            if self.show_fps and self._fps_font:
                fps_text = f"FPS: {int(self._fps_value)}"
                surf = self._fps_font.render(fps_text, True, (180, 180, 180))
                self.screen.blit(surf, (12, 10))
        except Exception:
            pass
        
        pygame.display.flip()
    
    def run(self):
        """Main display loop"""
        print("🎬 Starting NDI Display...")
        
        # Try to connect on startup
        if self.selected_source:
            self.connect_to_source()
        else:
            self.auto_connect()
        
        clock = pygame.time.Clock()
        
        while self.running:
            # Handle pygame events
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE or event.key == pygame.K_q:
                        self.running = False
            
            # Check for configuration updates from web interface
            self.check_config_update()
            
            # Render current frame
            self.render_frame()
            
            # No artificial frame rate limit - run as fast as source provides
        
        self.cleanup()
    
    def signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        print(f"\n⚠️  Received signal {signum}, shutting down...")
        self.running = False
    
    def cleanup(self):
        """Clean up resources"""
        print("🧹 Cleaning up...")
        if self.receiver:
            self.receiver.close()
        pygame.quit()
        print("👋 Display stopped")


if __name__ == "__main__":
    display = NDIDisplay()
    display.run()
