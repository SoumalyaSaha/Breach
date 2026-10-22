"""Copy text to the system clipboard (best effort, never raises)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys


def copy_to_clipboard(text: str) -> bool:
    """Put `text` on the clipboard. Returns True on success."""
    if not text:
        return False
    try:
        if sys.platform.startswith("win"):
            return _copy_windows(text)
        if sys.platform == "darwin":
            if not shutil.which("pbcopy"):
                return False
            proc = subprocess.run(
                ["pbcopy"], input=text.encode("utf-8"), capture_output=True, timeout=5
            )
            return proc.returncode == 0
        for tool in ("wl-copy", "xclip", "xsel"):
            if shutil.which(tool):
                if tool == "xclip":
                    cmd = [tool, "-selection", "clipboard"]
                elif tool == "xsel":
                    cmd = [tool, "--clipboard", "--input"]
                else:
                    cmd = [tool]
                proc = subprocess.run(
                    cmd, input=text.encode("utf-8"), capture_output=True, timeout=5
                )
                return proc.returncode == 0
    except Exception:
        return False
    return False


def _copy_windows(text: str) -> bool:
    try:
        import ctypes
        from ctypes import wintypes
    except Exception:
        return False
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        CF_UNICODETEXT = 13
        GMEM_MOVEABLE = 0x0002

        user32.OpenClipboard.argtypes = [wintypes.HWND]
        user32.OpenClipboard.restype = wintypes.BOOL
        user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
        user32.SetClipboardData.restype = wintypes.HANDLE
        kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
        kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
        kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalLock.restype = wintypes.LPVOID
        kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalUnlock.restype = wintypes.BOOL

        if not user32.OpenClipboard(None):
            return False
        try:
            user32.EmptyClipboard()
            data = text + "\0"
            size = len(data) * ctypes.sizeof(ctypes.c_wchar)
            handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
            if not handle:
                return False
            locked = kernel32.GlobalLock(handle)
            if not locked:
                kernel32.GlobalFree(handle)
                return False
            try:
                ctypes.memmove(
                    locked,
                    ctypes.create_unicode_buffer(data),
                    size,
                )
            finally:
                kernel32.GlobalUnlock(handle)
            if not user32.SetClipboardData(CF_UNICODETEXT, handle):
                kernel32.GlobalFree(handle)
                return False
            return True
        finally:
            user32.CloseClipboard()
    except Exception:
        return False
