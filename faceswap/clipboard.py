"""Clipboard-Zugriff für Oxx' FaceSwap (Bilder kopieren und einfügen)."""

from __future__ import annotations

import ctypes
import io
from ctypes import wintypes
from pathlib import Path
from typing import Literal

from PIL import Image, ImageGrab

from .engine import SUPPORTED_EXTENSIONS

CF_DIB = 8
GMEM_MOVEABLE = 0x0002

ClipboardContent = tuple[Literal["image", "path"], Image.Image | Path] | None


def clipboard_content() -> ClipboardContent:
    """Liest ein Bild oder eine Bilddatei aus der Zwischenablage.

    Rückgabe: ("image", PIL.Image), ("path", Path) oder None.
    """
    try:
        data = ImageGrab.grabclipboard()
    except Exception:  # noqa: BLE001 – Clipboard kann gesperrt sein
        return None

    if isinstance(data, Image.Image):
        return "image", data.convert("RGB")

    # Im Explorer kopierte Dateien landen als Dateiliste im Clipboard.
    if isinstance(data, list):
        for entry in data:
            path = Path(entry)
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
                return "path", path
    return None


def copy_image_to_clipboard(image: Image.Image) -> None:
    """Legt ein PIL-Bild als CF_DIB in die Windows-Zwischenablage."""
    if not hasattr(ctypes, "windll"):
        raise RuntimeError("Das Kopieren in die Zwischenablage wird nur unter Windows unterstützt.")

    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, "BMP")
    # BITMAPFILEHEADER (14 Byte) entfernen -> reines DIB
    payload = buffer.getvalue()[14:]
    buffer.close()

    kernel32 = ctypes.windll.kernel32
    user32 = ctypes.windll.user32

    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.restype = wintypes.BOOL
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    user32.CloseClipboard.restype = wintypes.BOOL

    if not user32.OpenClipboard(None):
        raise RuntimeError("Die Zwischenablage ist gerade von einem anderen Programm belegt.")

    try:
        user32.EmptyClipboard()
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(payload))
        if not handle:
            raise RuntimeError("Nicht genug Speicher für das Bild in der Zwischenablage.")
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            raise RuntimeError("Zwischenablage-Speicher konnte nicht gesperrt werden.")
        try:
            ctypes.memmove(pointer, payload, len(payload))
        finally:
            kernel32.GlobalUnlock(handle)

        if not user32.SetClipboardData(CF_DIB, handle):
            raise RuntimeError("Das Bild konnte nicht in die Zwischenablage gelegt werden.")
        # Ab hier gehört das Handle Windows, nicht mehr uns.
    finally:
        user32.CloseClipboard()
