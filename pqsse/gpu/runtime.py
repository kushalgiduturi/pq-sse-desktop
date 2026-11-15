"""Packaged GPU build: make the bundled CUDA compiler (NVRTC) findable.

The CUDA kernel is compiled at run time. A normal user has no CUDA Toolkit, so the GPU
build ships a minimal CUDA folder next to the program's libraries:

    cuda_runtime/bin       the NVRTC compiler DLLs and the CUDA runtime DLL
    cuda_runtime/include   the CUDA headers CuPy asks for

``prepare()`` points CUDA_PATH at that folder for this process and adds its bin folder to
the DLL search path, before CuPy is imported. A CUDA Toolkit installed on the PC is then
not used and not needed. The only thing that must exist on the PC is the NVIDIA driver.

From source nothing is changed: CuPy finds the Toolkit or the pip wheels by itself.
"""
from __future__ import annotations

import ctypes
import os
import sys

from .. import paths

RUNTIME_DIR = "cuda_runtime"
_handles: list = []


def bundled_dir() -> str:
    """The bundled CUDA folder, or "" when this build has none."""
    folder = paths.resource(RUNTIME_DIR)
    return str(folder) if paths.frozen() and any((folder / "bin").glob("nvrtc*.dll")) else ""


def prepare() -> str:
    """Call once at start, before CuPy is imported. Returns the bundled folder or ""."""
    if not paths.frozen():
        return ""
    try:
        os.environ.setdefault("CUPY_CACHE_DIR", str(paths.base_dir() / "cupy_cache"))
    except OSError:
        pass
    folder = bundled_dir()
    if not folder:
        return ""
    if not _handles:
        bin_dir = os.path.join(folder, "bin")
        try:
            _handles.append(os.add_dll_directory(bin_dir))
        except (OSError, AttributeError):
            pass
        os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
        os.environ["CUDA_PATH"] = folder
        os.environ.pop("CUDA_HOME", None)
    return folder


CUDA_MODULES = ("nvrtc64_120_0.dll", "nvrtc64_130_0.dll", "nvrtc64_112_0.dll", "cudart64_12.dll", "cudart64_13.dll",
                "cudart64_110.dll", "nvcuda.dll", "cublas64_12.dll")


def loaded_cuda_modules() -> list[str]:
    """Full paths of the NVIDIA libraries this process has loaded right now (Windows)."""
    if sys.platform != "win32":
        return []
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE
    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetModuleFileNameW.argtypes = [wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD]
    found = []
    for name in CUDA_MODULES:
        handle = kernel32.GetModuleHandleW(name)
        if handle:
            buffer = ctypes.create_unicode_buffer(1024)
            if kernel32.GetModuleFileNameW(handle, buffer, 1024):
                found.append(buffer.value)
    return found


def driver_present() -> bool:
    """True when the NVIDIA driver's CUDA library can be loaded (Windows), or on other systems."""
    if sys.platform != "win32":
        return True
    try:
        ctypes.WinDLL("nvcuda.dll")
        return True
    except OSError:
        return False
