"""
Real NDI module for macOS using the NDI SDK.
This uses the actual libndi.dylib library to discover and receive NDI sources.
"""
import ctypes
import ctypes.util
import os
from pathlib import Path
import threading
import time
from dataclasses import dataclass
from io import BytesIO
from typing import List, Optional

import numpy as np
from PIL import Image

try:
    from numba import njit, prange
    NUMBA_AVAILABLE = True
except ImportError:
    NUMBA_AVAILABLE = False


class NDIError(RuntimeError):
    pass


def _load_ndi_lib() -> ctypes.CDLL:
    """Load the NDI library on macOS"""
    candidates = [
        "/usr/local/lib/libndi.dylib",
        "libndi.dylib",
        "/Library/Application Support/NewTek/NDI/libndi.dylib",
    ]
    
    # Check environment variable override
    override = os.environ.get("NDI_LIB_PATH")
    if override:
        candidates.insert(0, override)
    
    for path in candidates:
        try:
            lib = ctypes.CDLL(path)
            print(f"✅ Loaded NDI library from: {path}")
            return lib
        except OSError as e:
            continue
    
    raise NDIError(
        "Could not load NDI library (libndi.dylib). "
        "Install NDI SDK from https://ndi.video/tools/ or set NDI_LIB_PATH environment variable."
    )


# NDI structures and constants
class NDIlib_source_t(ctypes.Structure):
    _fields_ = [
        ("p_ndi_name", ctypes.c_char_p),
        ("p_url_address", ctypes.c_char_p),
    ]


class NDIlib_video_frame_v2_t(ctypes.Structure):
    _fields_ = [
        ("xres", ctypes.c_int),
        ("yres", ctypes.c_int),
        ("FourCC", ctypes.c_uint),
        ("frame_rate_N", ctypes.c_int),
        ("frame_rate_D", ctypes.c_int),
        ("picture_aspect_ratio", ctypes.c_float),
        ("frame_format_type", ctypes.c_int),
        ("timecode", ctypes.c_int64),
        ("p_data", ctypes.POINTER(ctypes.c_uint8)),
        ("line_stride_in_bytes", ctypes.c_int),
        ("p_metadata", ctypes.c_char_p),
        ("timestamp", ctypes.c_int64),
    ]


# NDI FourCC codes
NDIlib_FourCC_type_UYVY = 0x59565955  # UYVY
NDIlib_FourCC_type_BGRA = 0x41524742  # BGRA
NDIlib_FourCC_type_BGRX = 0x58524742  # BGRX
NDIlib_FourCC_type_RGBA = 0x41424752  # RGBA
NDIlib_FourCC_type_RGBX = 0x58424752  # RGBX

# Frame format types
NDIlib_frame_format_type_progressive = 1
NDIlib_frame_format_type_interleaved = 0


# UYVY to RGB conversion functions
def _uyvy_to_rgb_numpy(active: np.ndarray, height: int, width: int) -> np.ndarray:
    """Numpy-based UYVY to RGB conversion (fallback)"""
    pairs = active.reshape(height, width // 2, 4)
    U = pairs[:, :, 0].astype(np.int32)
    Y0 = pairs[:, :, 1].astype(np.int32)
    V = pairs[:, :, 2].astype(np.int32)
    Y1 = pairs[:, :, 3].astype(np.int32)

    cb = U - 128
    cr = V - 128
    c0 = Y0 - 16
    c1 = Y1 - 16

    r_chroma = (409 * cr + 128) >> 8
    g_chroma = (-100 * cb - 208 * cr + 128) >> 8
    b_chroma = (516 * cb + 128) >> 8
    c0_scaled = (298 * c0) >> 8
    c1_scaled = (298 * c1) >> 8

    rgb = np.empty((height, width, 3), dtype=np.uint8)
    rgb[:, 0::2, 0] = np.clip(c0_scaled + r_chroma, 0, 255)
    rgb[:, 0::2, 1] = np.clip(c0_scaled + g_chroma, 0, 255)
    rgb[:, 0::2, 2] = np.clip(c0_scaled + b_chroma, 0, 255)
    rgb[:, 1::2, 0] = np.clip(c1_scaled + r_chroma, 0, 255)
    rgb[:, 1::2, 1] = np.clip(c1_scaled + g_chroma, 0, 255)
    rgb[:, 1::2, 2] = np.clip(c1_scaled + b_chroma, 0, 255)
    return rgb


if NUMBA_AVAILABLE:
    @njit(parallel=True, cache=True, fastmath=True)
    def _uyvy_to_rgb_numba(active: np.ndarray, height: int, width: int) -> np.ndarray:
        """Numba JIT-compiled UYVY to RGB conversion (~10x faster)"""
        rgb = np.empty((height, width, 3), dtype=np.uint8)
        half_width = width // 2
        
        for y in prange(height):
            for x in range(half_width):
                idx = x * 4
                u = active[y, idx]
                y0 = active[y, idx + 1]
                v = active[y, idx + 2]
                y1 = active[y, idx + 3]
                
                cb = u - 128
                cr = v - 128
                c0 = y0 - 16
                c1 = y1 - 16
                
                r_chroma = (409 * cr + 128) >> 8
                g_chroma = (-100 * cb - 208 * cr + 128) >> 8
                b_chroma = (516 * cb + 128) >> 8
                c0_scaled = (298 * c0) >> 8
                c1_scaled = (298 * c1) >> 8
                
                # Pixel 0
                r0 = c0_scaled + r_chroma
                g0 = c0_scaled + g_chroma
                b0 = c0_scaled + b_chroma
                rgb[y, x * 2, 0] = min(max(r0, 0), 255)
                rgb[y, x * 2, 1] = min(max(g0, 0), 255)
                rgb[y, x * 2, 2] = min(max(b0, 0), 255)
                
                # Pixel 1
                r1 = c1_scaled + r_chroma
                g1 = c1_scaled + g_chroma
                b1 = c1_scaled + b_chroma
                rgb[y, x * 2 + 1, 0] = min(max(r1, 0), 255)
                rgb[y, x * 2 + 1, 1] = min(max(g1, 0), 255)
                rgb[y, x * 2 + 1, 2] = min(max(b1, 0), 255)
        
        return rgb
else:
    _uyvy_to_rgb_numba = _uyvy_to_rgb_numpy
NDIlib_frame_format_type_field_0 = 2
NDIlib_frame_format_type_field_1 = 3


class _NDI:
    """Singleton wrapper for NDI library"""
    _instance = None
    _lock = threading.Lock()
    
    @classmethod
    def get(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = _NDI()
        return cls._instance
    
    def __init__(self):
        self.lib = _load_ndi_lib()
        
        # Initialize NDI
        if not self.lib.NDIlib_initialize():
            raise NDIError("Failed to initialize NDI library")
        
        print("✅ NDI library initialized successfully")
        
        # Set up function signatures
        self._setup_function_signatures()
    
    def _setup_function_signatures(self):
        """Configure ctypes function signatures for NDI API"""
        # NDIlib_find_create_v2
        self.lib.NDIlib_find_create_v2.argtypes = [ctypes.c_void_p]
        self.lib.NDIlib_find_create_v2.restype = ctypes.c_void_p
        
        # NDIlib_find_wait_for_sources
        self.lib.NDIlib_find_wait_for_sources.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        self.lib.NDIlib_find_wait_for_sources.restype = ctypes.c_bool
        
        # NDIlib_find_get_current_sources
        self.lib.NDIlib_find_get_current_sources.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_uint32)
        ]
        self.lib.NDIlib_find_get_current_sources.restype = ctypes.POINTER(NDIlib_source_t)
        
        # NDIlib_recv_create_v3
        self.lib.NDIlib_recv_create_v3.argtypes = [ctypes.c_void_p]
        self.lib.NDIlib_recv_create_v3.restype = ctypes.c_void_p
        
        # NDIlib_recv_connect
        self.lib.NDIlib_recv_connect.argtypes = [ctypes.c_void_p, ctypes.POINTER(NDIlib_source_t)]
        self.lib.NDIlib_recv_connect.restype = None
        
        # NDIlib_recv_capture_v2
        self.lib.NDIlib_recv_capture_v2.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(NDIlib_video_frame_v2_t),
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_uint32
        ]
        self.lib.NDIlib_recv_capture_v2.restype = ctypes.c_int
        
        # NDIlib_recv_free_video_v2
        self.lib.NDIlib_recv_free_video_v2.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(NDIlib_video_frame_v2_t)
        ]
        
        # NDIlib_recv_destroy
        self.lib.NDIlib_recv_destroy.argtypes = [ctypes.c_void_p]
        
        # NDIlib_find_destroy
        self.lib.NDIlib_find_destroy.argtypes = [ctypes.c_void_p]


class NDISourceFinder:
    """Find NDI sources on the network"""
    
    def __init__(self):
        self.ndi = _NDI.get()
        self.finder = self.ndi.lib.NDIlib_find_create_v2(None)
        if not self.finder:
            raise NDIError("Failed to create NDI finder")
    
    def list_sources(self, timeout_ms: int = 1000) -> List[str]:
        """List available NDI sources"""
        # Wait for sources
        self.ndi.lib.NDIlib_find_wait_for_sources(self.finder, timeout_ms)
        
        # Get sources
        num_sources = ctypes.c_uint32(0)
        sources = self.ndi.lib.NDIlib_find_get_current_sources(
            self.finder, 
            ctypes.byref(num_sources)
        )
        
        source_names = []
        for i in range(num_sources.value):
            name = sources[i].p_ndi_name.decode('utf-8') if sources[i].p_ndi_name else ""
            if name:
                source_names.append(name)
        
        return source_names
    
    def __del__(self):
        if hasattr(self, 'finder') and self.finder:
            self.ndi.lib.NDIlib_find_destroy(self.finder)


class NDIReceiver:
    """Receive video from an NDI source"""
    
    def __init__(self, source_name: str):
        self.ndi = _NDI.get()
        self.source_name = source_name
        self._closed = False
        self._lock = threading.Lock()
        
        # Find the source
        finder = self.ndi.lib.NDIlib_find_create_v2(None)
        if not finder:
            raise NDIError("Failed to create finder for receiver")
        
        try:
            # Wait for sources
            self.ndi.lib.NDIlib_find_wait_for_sources(finder, 2000)
            
            # Get sources
            num_sources = ctypes.c_uint32(0)
            sources = self.ndi.lib.NDIlib_find_get_current_sources(
                finder,
                ctypes.byref(num_sources)
            )
            
            # Find matching source
            target_source = None
            for i in range(num_sources.value):
                name = sources[i].p_ndi_name.decode('utf-8') if sources[i].p_ndi_name else ""
                if name == source_name:
                    target_source = sources[i]
                    break
            
            if not target_source:
                raise NDIError(f"Source '{source_name}' not found")
            
            # Create receiver
            self.receiver = self.ndi.lib.NDIlib_recv_create_v3(None)
            if not self.receiver:
                raise NDIError("Failed to create NDI receiver")
            
            # Connect to source
            self.ndi.lib.NDIlib_recv_connect(self.receiver, ctypes.byref(target_source))
            
            print(f"✅ Connected to NDI source: {source_name}")
            
        finally:
            self.ndi.lib.NDIlib_find_destroy(finder)
    
    def _convert_frame_to_rgb(self, video_frame: NDIlib_video_frame_v2_t) -> np.ndarray:
        """Convert NDI video frame to RGB numpy array"""
        width = video_frame.xres
        height = video_frame.yres
        fourcc = video_frame.FourCC
        
        if fourcc == NDIlib_FourCC_type_BGRA or fourcc == NDIlib_FourCC_type_BGRX:
            # BGRA/BGRX format
            frame_data = ctypes.cast(
                video_frame.p_data,
                ctypes.POINTER(ctypes.c_uint8 * (width * height * 4))
            ).contents
            array = np.frombuffer(frame_data, dtype=np.uint8).reshape((height, width, 4))
            # Convert BGRA to RGB
            return array[:, :, [2, 1, 0]]
        
        elif fourcc == NDIlib_FourCC_type_RGBA or fourcc == NDIlib_FourCC_type_RGBX:
            # RGBA/RGBX format
            frame_data = ctypes.cast(
                video_frame.p_data,
                ctypes.POINTER(ctypes.c_uint8 * (width * height * 4))
            ).contents
            array = np.frombuffer(frame_data, dtype=np.uint8).reshape((height, width, 4))
            # Take just RGB
            return array[:, :, :3]
        
        elif fourcc == NDIlib_FourCC_type_UYVY:
            # UYVY format - use numba JIT if available for ~10x speedup
            stride = video_frame.line_stride_in_bytes if video_frame.line_stride_in_bytes else width * 2
            frame_size = stride * height

            frame_data = ctypes.cast(
                video_frame.p_data,
                ctypes.POINTER(ctypes.c_uint8 * frame_size)
            ).contents

            uyvy = np.frombuffer(frame_data, dtype=np.uint8)[:frame_size].reshape((height, stride))
            # Use only the active pixels (ignore padding beyond width*2)
            # Make contiguous for numba performance
            active = np.ascontiguousarray(uyvy[:, :width * 2])
            
            if NUMBA_AVAILABLE:
                rgb = _uyvy_to_rgb_numba(active, height, width)
            else:
                rgb = _uyvy_to_rgb_numpy(active, height, width)
            
            return rgb
        
        else:
            raise NDIError(f"Unsupported FourCC format: 0x{fourcc:08X}")
    
    def get_jpeg_frame(
        self,
        timeout_ms: int = 1000,
        jpeg_quality: int = 85,
        output_width: int = 0,
        output_height: int = 0
    ) -> Optional[bytes]:
        """Capture a frame and return as JPEG bytes"""
        with self._lock:
            if self._closed:
                return None
            
            video_frame = NDIlib_video_frame_v2_t()
            
            # Capture frame (type 1 = video)
            frame_type = self.ndi.lib.NDIlib_recv_capture_v2(
                self.receiver,
                ctypes.byref(video_frame),
                None,  # audio
                None,  # metadata
                timeout_ms
            )
            
            if frame_type != 1:  # 1 = video frame
                return None
            
            try:
                # Convert to RGB
                rgb_array = self._convert_frame_to_rgb(video_frame)
                
                # Convert to PIL Image
                img = Image.fromarray(rgb_array, 'RGB')
                
                # Resize if requested
                if output_width > 0 and output_height > 0:
                    img = img.resize((output_width, output_height), Image.Resampling.LANCZOS)
                
                # Convert to JPEG
                buffer = BytesIO()
                img.save(buffer, format='JPEG', quality=jpeg_quality, optimize=True)
                return buffer.getvalue()
                
            finally:
                # Free the video frame
                self.ndi.lib.NDIlib_recv_free_video_v2(
                    self.receiver,
                    ctypes.byref(video_frame)
                )

    def get_rgb_frame(
        self,
        timeout_ms: int = 30,
        output_width: int = 0,
        output_height: int = 0
    ) -> Optional[tuple]:
        """Capture a frame and return as (RGB ndarray, (width, height)).
        This avoids JPEG encoding for higher throughput.
        """
        with self._lock:
            if self._closed:
                return None

            video_frame = NDIlib_video_frame_v2_t()

            # Capture frame (type 1 = video)
            frame_type = self.ndi.lib.NDIlib_recv_capture_v2(
                self.receiver,
                ctypes.byref(video_frame),
                None,  # audio
                None,  # metadata
                timeout_ms
            )

            if frame_type != 1:  # 1 = video frame
                return None

            try:
                # Convert to RGB ndarray
                rgb_array = self._convert_frame_to_rgb(video_frame)

                # Optionally resize if requested
                if output_width > 0 and output_height > 0:
                    img = Image.fromarray(rgb_array, 'RGB')
                    img = img.resize((output_width, output_height), Image.Resampling.LANCZOS)
                    rgb_array = np.asarray(img)

                h, w = rgb_array.shape[:2]
                return (rgb_array, (w, h))

            finally:
                # Free the video frame
                self.ndi.lib.NDIlib_recv_free_video_v2(
                    self.receiver,
                    ctypes.byref(video_frame)
                )
    
    def close(self):
        """Close the receiver"""
        with self._lock:
            if not self._closed:
                self._closed = True
                if hasattr(self, 'receiver') and self.receiver:
                    self.ndi.lib.NDIlib_recv_destroy(self.receiver)
                    print(f"🔌 Disconnected from: {self.source_name}")
    
    def __del__(self):
        self.close()
