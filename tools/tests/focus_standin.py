"""A stand-in for the game's window, for tools/tests/focus_guard_test.py (no game needed).

  py -3.14 tools/tests/focus_standin.py --role game --events out.jsonl [--takes 1.5,4,6.5] [--recreate 5.2] [--seconds 9] [--hang 1]
  py -3.14 tools/tests/focus_standin.py --role user --events out.jsonl [--seconds 60]

game: the first ShowWindow honours the launcher's STARTUPINFO (SW_SHOWNOACTIVATE), as Warhammer3.exe does; then at each --takes
second it activates itself the way an ordinary app can: SetForegroundWindow + BringWindowToTop on its own window, three times 150 ms
apart, and when Windows refuses, the aggressive way some games use (its input attached to the foreground thread). At --recreate it
destroys its window and shows a new one with SW_SHOW, as a game does when it recreates the window or swap chain. It repaints every
30 ms with a colour that changes every frame (never black), so PrintWindow pictures prove it renders; frames painted per half second,
WM_SIZE minimised/restored and WM_ACTIVATEAPP go to --events with time.perf_counter() (system-wide, comparable across processes).
user: a plain window that activates itself once at start: the "user's" window. No keys or mouse are sent by either role.
"""
import argparse
import ctypes
import ctypes.wintypes as wt
import json
import time

u = ctypes.WinDLL("user32", use_last_error=True)
g = ctypes.WinDLL("gdi32")
k = ctypes.WinDLL("kernel32")
LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wt.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON), ("hCursor", wt.HANDLE), ("hbrBackground", wt.HBRUSH),
                ("lpszMenuName", wt.LPCWSTR), ("lpszClassName", wt.LPCWSTR)]


class PAINTSTRUCT(ctypes.Structure):
    _fields_ = [("hdc", wt.HDC), ("fErase", wt.BOOL), ("rcPaint", wt.RECT), ("fRestore", wt.BOOL), ("fIncUpdate", wt.BOOL),
                ("rgbReserved", ctypes.c_byte * 32)]


for f, res, args in [
    (u.DefWindowProcW, LRESULT, [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]), (u.RegisterClassW, wt.ATOM, [ctypes.POINTER(WNDCLASSW)]),
    (u.CreateWindowExW, wt.HWND, [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                  wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID]),
    (u.ShowWindow, wt.BOOL, [wt.HWND, ctypes.c_int]), (u.DestroyWindow, wt.BOOL, [wt.HWND]),
    (u.SetTimer, ctypes.c_size_t, [wt.HWND, ctypes.c_size_t, wt.UINT, ctypes.c_void_p]),
    (u.InvalidateRect, wt.BOOL, [wt.HWND, ctypes.c_void_p, wt.BOOL]),
    (u.BeginPaint, wt.HDC, [wt.HWND, ctypes.POINTER(PAINTSTRUCT)]), (u.EndPaint, wt.BOOL, [wt.HWND, ctypes.POINTER(PAINTSTRUCT)]),
    (u.FillRect, ctypes.c_int, [wt.HDC, ctypes.POINTER(wt.RECT), wt.HBRUSH]), (u.GetClientRect, wt.BOOL, [wt.HWND, ctypes.POINTER(wt.RECT)]),
    (u.GetForegroundWindow, wt.HWND, []), (u.SetForegroundWindow, wt.BOOL, [wt.HWND]), (u.BringWindowToTop, wt.BOOL, [wt.HWND]),
    (u.GetWindowThreadProcessId, wt.DWORD, [wt.HWND, ctypes.c_void_p]), (u.AttachThreadInput, wt.BOOL, [wt.DWORD, wt.DWORD, wt.BOOL]),
    (u.GetMessageW, wt.BOOL, [ctypes.c_void_p, wt.HWND, wt.UINT, wt.UINT]), (u.TranslateMessage, wt.BOOL, [ctypes.c_void_p]),
    (u.DispatchMessageW, LRESULT, [ctypes.c_void_p]), (u.PostQuitMessage, None, [ctypes.c_int]),
    (g.CreateSolidBrush, wt.HBRUSH, [wt.COLORREF]), (g.DeleteObject, wt.BOOL, [wt.HGDIOBJ]),
    (g.SetBkMode, ctypes.c_int, [wt.HDC, ctypes.c_int]), (g.TextOutW, wt.BOOL, [wt.HDC, ctypes.c_int, ctypes.c_int, wt.LPCWSTR, ctypes.c_int]),
    (k.GetModuleHandleW, wt.HMODULE, [wt.LPCWSTR]), (k.GetCurrentThreadId, wt.DWORD, []),
]:
    f.restype, f.argtypes = res, args

WM_DESTROY, WM_PAINT, WM_SIZE, WM_TIMER, WM_ACTIVATEAPP, WM_CLOSE = 0x2, 0xF, 0x5, 0x113, 0x1C, 0x10
SW_SHOWDEFAULT, SW_SHOW = 10, 5
PAINT_TIMER, SCHEDULE_TIMER = 1, 2


class StandIn:
    def __init__(self, args):
        self.args = args
        self.out = open(args.events, "a", encoding="utf-8")
        self.t0 = time.perf_counter()
        self.frames = self.frames_logged = 0
        self.hwnd = None
        self.pending = []           # (time, action)
        self.proc = WNDPROC(self.wndproc)
        cls = WNDCLASSW(lpfnWndProc=self.proc, hInstance=k.GetModuleHandleW(None), lpszClassName="mtb_focus_standin",
                        hCursor=None, hbrBackground=None)
        u.RegisterClassW(ctypes.byref(cls))
        self.title = f"mtb focus test: {args.role}"

    def log(self, event, **kw):
        self.out.write(json.dumps(dict(t=time.perf_counter(), e=event, **kw)) + "\n")
        self.out.flush()

    def create(self, show):
        x = 60 if self.args.role == "user" else 140
        self.hwnd = u.CreateWindowExW(0, "mtb_focus_standin", self.title, 0x00CF0000, x, x, 640, 400, None, None, None, None)
        u.ShowWindow(self.hwnd, show)
        u.SetTimer(self.hwnd, PAINT_TIMER, 30, None)
        u.SetTimer(self.hwnd, SCHEDULE_TIMER, 10, None)
        self.log("window", hwnd=int(self.hwnd), fg=u.GetForegroundWindow() == self.hwnd)

    def take(self, burst):
        how = "plain"
        u.SetForegroundWindow(self.hwnd)
        u.BringWindowToTop(self.hwnd)
        ok = u.GetForegroundWindow() == self.hwnd
        if not ok:
            how = "attach"
            fg = u.GetForegroundWindow()
            me, them = k.GetCurrentThreadId(), u.GetWindowThreadProcessId(fg, None)
            attached = bool(them) and them != me and u.AttachThreadInput(me, them, True)
            try:
                u.BringWindowToTop(self.hwnd)
                u.SetForegroundWindow(self.hwnd)
            finally:
                if attached:
                    u.AttachThreadInput(me, them, False)
            ok = u.GetForegroundWindow() == self.hwnd
        self.log("take", burst=burst, ok=bool(ok), how=how)
        if burst == 2 and self.args.hang:      # a game loading: its window thread pumps no messages for a while
            time.sleep(self.args.hang)
            self.log("hang_end", seconds=self.args.hang)

    def wndproc(self, hwnd, msg, wp, lp):
        if msg == WM_TIMER and wp == PAINT_TIMER:
            u.InvalidateRect(hwnd, None, False)
            now = time.perf_counter()
            if now - self.t0 >= (self.frames_logged + 1) * 0.5:
                self.frames_logged += 1
                self.log("frames", n=self.frames)
            return 0
        if msg == WM_TIMER and wp == SCHEDULE_TIMER:
            now = time.perf_counter() - self.t0
            due = [p for p in self.pending if p[0] <= now]
            self.pending = [p for p in self.pending if p[0] > now]
            for _, action, arg in due:
                if action == "take":
                    self.take(arg)
                elif action == "recreate":
                    old = self.hwnd
                    self.hwnd = None
                    u.DestroyWindow(old)
                    self.create(SW_SHOW)
                    self.log("recreated", old=int(old))
                elif action == "quit":
                    u.DestroyWindow(self.hwnd)
            return 0
        if msg == WM_PAINT:
            ps = PAINTSTRUCT()
            hdc = u.BeginPaint(hwnd, ctypes.byref(ps))
            r = wt.RECT()
            u.GetClientRect(hwnd, ctypes.byref(r))
            self.frames += 1
            f = self.frames
            colour = (40 + f * 7 % 200) | ((40 + f * 3 % 200) << 8) | ((120 if self.args.role == "game" else 200) << 16)
            brush = g.CreateSolidBrush(colour)
            u.FillRect(hdc, ctypes.byref(r), brush)
            g.DeleteObject(brush)
            g.SetBkMode(hdc, 1)
            text = f"{self.title}  frame {f}"
            g.TextOutW(hdc, 20, 20, text, len(text))
            u.EndPaint(hwnd, ctypes.byref(ps))
            return 0
        if msg == WM_SIZE:
            self.log("size", kind={0: "restored", 1: "minimised", 2: "maximised"}.get(wp, wp))
        if msg == WM_ACTIVATEAPP:
            self.log("activateapp", active=bool(wp))
        if msg == WM_DESTROY and hwnd == self.hwnd:
            u.PostQuitMessage(0)
            return 0
        return u.DefWindowProcW(hwnd, msg, wp, lp)

    def run(self):
        a = self.args
        if a.role == "game":
            for t in [float(x) for x in a.takes.split(",") if x]:
                self.pending += [(t + i * 0.15, "take", i) for i in range(3)]
            if a.recreate:
                self.pending.append((a.recreate, "recreate", None))
            self.create(SW_SHOWDEFAULT)        # the first show takes STARTUPINFO's wShowWindow, as the game's does
        else:
            self.create(SW_SHOW)
            self.take(0)
        self.pending.append((a.seconds, "quit", None))
        msg = (ctypes.c_byte * 64)()
        while u.GetMessageW(msg, None, 0, 0) > 0:
            u.TranslateMessage(msg)
            u.DispatchMessageW(msg)
        self.log("end", frames=self.frames)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", choices=["game", "user"], required=True)
    ap.add_argument("--events", required=True)
    ap.add_argument("--takes", default="1.5,4,6.5")
    ap.add_argument("--recreate", type=float, default=0)
    ap.add_argument("--seconds", type=float, default=9)
    ap.add_argument("--hang", type=float, default=0, help="seconds the window thread sleeps after each burst of takes")
    StandIn(ap.parse_args()).run()
