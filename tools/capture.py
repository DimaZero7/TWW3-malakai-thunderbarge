"""Grabs the game window to PNG with no dependencies (ctypes + zlib).

Only PrintWindow with PW_RENDERFULLCONTENT: the window paints itself, so nothing else on the desktop can get
into the picture and the game is never brought to the front. Copying from the screen (BitBlt of the screen DC)
is deliberately not used: in battle 7 it saved the user's other windows. A torn or black frame is retried;
the best frame is kept and its share of black pixels is reported.
"""
import ctypes
import ctypes.wintypes as wt
import struct
import time
import zlib

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # per-monitor v2: real pixels

for _f, _r, _a in [
    (user32.GetDC, wt.HDC, [wt.HWND]),
    (user32.ReleaseDC, ctypes.c_int, [wt.HWND, wt.HDC]),
    (user32.GetClientRect, wt.BOOL, [wt.HWND, ctypes.POINTER(wt.RECT)]),
    (user32.IsWindowVisible, wt.BOOL, [wt.HWND]),
    (user32.PrintWindow, wt.BOOL, [wt.HWND, wt.HDC, wt.UINT]),
    (user32.GetWindowThreadProcessId, wt.DWORD, [wt.HWND, ctypes.POINTER(wt.DWORD)]),
    (gdi32.CreateCompatibleDC, wt.HDC, [wt.HDC]),
    (gdi32.CreateCompatibleBitmap, wt.HBITMAP, [wt.HDC, ctypes.c_int, ctypes.c_int]),
    (gdi32.SelectObject, wt.HGDIOBJ, [wt.HDC, wt.HGDIOBJ]),
    (gdi32.DeleteDC, wt.BOOL, [wt.HDC]),
    (gdi32.DeleteObject, wt.BOOL, [wt.HGDIOBJ]),
    (gdi32.GetDIBits, ctypes.c_int, [wt.HDC, wt.HBITMAP, wt.UINT, wt.UINT, ctypes.c_void_p, ctypes.c_void_p, wt.UINT]),
]:
    _f.restype, _f.argtypes = _r, _a

PW_RENDERFULLCONTENT = 3


def find_window(pid):
    """The process's visible top-level window with the largest client area, or None."""
    best = [None, 0]
    proto = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

    def visit(hwnd, _):
        owner = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(hwnd):
            r = wt.RECT()
            user32.GetClientRect(hwnd, ctypes.byref(r))
            area = (r.right - r.left) * (r.bottom - r.top)
            if area > best[1]:
                best[0], best[1] = hwnd, area
        return True
    user32.EnumWindows(proto(visit), 0)
    return best[0]


def _png(w, h, bgra):
    raw = bytearray()
    stride = w * 4
    for y in range(h):
        raw.append(0)
        row = bgra[y * stride:(y + 1) * stride]
        px = bytearray(w * 3)
        px[0::3] = row[2::4]
        px[1::3] = row[1::4]
        px[2::3] = row[0::4]
        raw += px

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw), 6)) + chunk(b"IEND", b""))


def grab(hwnd):
    """(w, h, BGRA bytes) of the client area, painted by the window itself."""
    r = wt.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    screen = user32.GetDC(None)
    mem = gdi32.CreateCompatibleDC(screen)
    bitmap = gdi32.CreateCompatibleBitmap(screen, w, h)
    old = gdi32.SelectObject(mem, bitmap)
    try:
        if not user32.PrintWindow(hwnd, mem, PW_RENDERFULLCONTENT):
            raise OSError(f"PrintWindow failed: {ctypes.get_last_error()}")
        header = struct.pack("<IiiHHIIiiII", 40, w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
        buf = ctypes.create_string_buffer(w * h * 4)
        gdi32.GetDIBits(mem, bitmap, 0, h, buf, header, 0)
        return w, h, buf.raw
    finally:
        gdi32.SelectObject(mem, old)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(mem)
        user32.ReleaseDC(None, screen)


def black_share(bgra):
    """Share of pure black pixels, sampled."""
    n = black = 0
    for i in range(0, len(bgra) - 3, 4 * 211):
        n += 1
        if bgra[i] == 0 and bgra[i + 1] == 0 and bgra[i + 2] == 0:
            black += 1
    return black / max(n, 1)


def crop(w, px, cw, ch):
    """The top-left cw x ch of a w wide BGRA picture."""
    return b"".join(px[y * w * 4:y * w * 4 + cw * 4] for y in range(ch))


def save_shot(hwnd, path, size=None, tries=12):
    """Writes path (.png), the PrintWindow frame with the fewest black pixels. size: the game's own x_res, y_res
    (PrintWindow draws that many pixels into a client area that DPI scaling reports larger).
    Returns the frame's share of black pixels; raises OSError when PrintWindow gives nothing."""
    best = None
    for _ in range(tries):
        w, h, px = grab(hwnd)
        if size and w >= size[0] and h >= size[1]:
            px, w, h = crop(w, px, size[0], size[1]), size[0], size[1]
        share = black_share(px)
        if best is None or share < best[0]:
            best = (share, w, h, px)
        if share < 0.002:
            break
        time.sleep(0.1)
    share, w, h, px = best
    path.write_bytes(_png(w, h, px))
    return round(share, 4)
