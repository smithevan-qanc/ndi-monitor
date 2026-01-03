"""
Mock NDI module for macOS testing.
This simulates NDI functionality without requiring the Windows DLL.
Generates test patterns and simulated video sources.
"""
import threading
import time
from io import BytesIO
from typing import List, Optional
from dataclasses import dataclass
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFont


class NDIError(RuntimeError):
    pass


@dataclass
class MockNDISource:
    """Simulates an NDI source"""
    name: str
    width: int = 1920
    height: int = 1080
    fps: int = 30


class NDISourceFinder:
    """Mock NDI source finder that returns simulated sources"""
    
    def __init__(self):
        # Simulate some NDI sources that might be on a network
        self._mock_sources = [
            MockNDISource("Camera 1 (Simulated)", 1920, 1080, 30),
            MockNDISource("Camera 2 (Simulated)", 1280, 720, 30),
            MockNDISource("Desktop Capture (Simulated)", 1920, 1080, 60),
        ]
    
    def list_sources(self, timeout_ms: int = 1000) -> List[str]:
        """
        List available NDI sources.
        In this mock version, we return simulated sources.
        """
        # Simulate network delay
        time.sleep(timeout_ms / 2000.0)
        
        # Return source names
        return [source.name for source in self._mock_sources]


class NDIReceiver:
    """Mock NDI receiver that generates test video frames"""
    
    def __init__(self, source_name: str):
        self.source_name = source_name
        self._closed = False
        self._frame_count = 0
        self._start_time = time.time()
        
        # Find the matching source
        self._source = None
        for src in [
            MockNDISource("Camera 1 (Simulated)", 1920, 1080, 30),
            MockNDISource("Camera 2 (Simulated)", 1280, 720, 30),
            MockNDISource("Desktop Capture (Simulated)", 1920, 1080, 60),
        ]:
            if src.name == source_name:
                self._source = src
                break
        
        if not self._source:
            raise NDIError(f"Source '{source_name}' not found")
        
        self._lock = threading.Lock()
    
    def _generate_test_frame(self, width: int, height: int) -> np.ndarray:
        """Generate a test pattern frame with animated elements"""
        # Create a gradient background
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        
        # Animated color shift
        elapsed = time.time() - self._start_time
        hue_shift = int((elapsed * 20) % 360)
        
        # Create gradient
        for y in range(height):
            for x in range(width):
                r = int((x / width) * 255)
                g = int((y / height) * 255)
                b = int(((x + y) / (width + height)) * 255)
                
                # Apply hue shift
                r = (r + hue_shift) % 256
                g = (g + hue_shift // 2) % 256
                
                frame[y, x] = [r, g, b]
        
        return frame
    
    def _add_overlays(self, img: Image.Image) -> Image.Image:
        """Add text overlays and animated elements to the frame"""
        draw = ImageDraw.Draw(img)
        
        # Try to use a default font, fall back to default if unavailable
        try:
            font_large = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 60)
            font_small = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 30)
        except:
            font_large = ImageFont.load_default()
            font_small = ImageFont.load_default()
        
        # Draw source name
        draw.text((40, 40), self.source_name, fill=(255, 255, 255, 200), font=font_large)
        
        # Draw frame counter
        elapsed = time.time() - self._start_time
        fps = self._frame_count / elapsed if elapsed > 0 else 0
        info_text = f"Frame: {self._frame_count} | FPS: {fps:.1f} | {self._source.width}x{self._source.height}"
        draw.text((40, 120), info_text, fill=(255, 255, 255, 180), font=font_small)
        
        # Draw timestamp
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        draw.text((40, 160), f"Time: {timestamp}", fill=(255, 255, 255, 180), font=font_small)
        
        # Draw animated bouncing circle
        circle_x = int(abs(np.sin(elapsed * 2)) * (img.width - 100) + 50)
        circle_y = int(abs(np.cos(elapsed * 2)) * (img.height - 100) + 50)
        draw.ellipse([circle_x - 30, circle_y - 30, circle_x + 30, circle_y + 30], 
                     fill=(255, 0, 0, 128), outline=(255, 255, 255))
        
        # Draw "SIMULATED" watermark
        watermark_x = img.width // 2
        watermark_y = img.height - 80
        draw.text((watermark_x, watermark_y), "🎬 SIMULATED NDI SOURCE", 
                  fill=(255, 255, 0, 150), font=font_small, anchor="mm")
        
        return img
    
    def get_jpeg_frame(
        self, 
        timeout_ms: int = 1000, 
        jpeg_quality: int = 85,
        output_width: int = 0,
        output_height: int = 0
    ) -> Optional[bytes]:
        """
        Get a frame as JPEG bytes.
        
        Args:
            timeout_ms: Timeout in milliseconds (simulated)
            jpeg_quality: JPEG quality (1-100)
            output_width: Desired output width (0 = native)
            output_height: Desired output height (0 = native)
        
        Returns:
            JPEG bytes or None if no frame available
        """
        with self._lock:
            if self._closed:
                return None
            
            # Simulate frame timing based on FPS
            frame_delay = 1.0 / self._source.fps
            time.sleep(frame_delay)
            
            # Determine output dimensions
            width = output_width if output_width > 0 else self._source.width
            height = output_height if output_height > 0 else self._source.height
            
            # Generate test frame
            frame_array = self._generate_test_frame(width, height)
            
            # Convert to PIL Image
            img = Image.fromarray(frame_array, 'RGB')
            
            # Add overlays
            img = self._add_overlays(img)
            
            # Resize if needed
            if (output_width > 0 and output_height > 0 and 
                (output_width != self._source.width or output_height != self._source.height)):
                img = img.resize((output_width, output_height), Image.Resampling.LANCZOS)
            
            # Convert to JPEG
            buffer = BytesIO()
            img.save(buffer, format='JPEG', quality=jpeg_quality, optimize=True)
            jpeg_bytes = buffer.getvalue()
            
            self._frame_count += 1
            
            return jpeg_bytes
    
    def close(self):
        """Close the receiver"""
        with self._lock:
            self._closed = True
    
    def __del__(self):
        self.close()
