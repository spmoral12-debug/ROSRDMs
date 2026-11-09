import ctypes, sys
from ctypes import wintypes

user32 = ctypes.windll.user32

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

windows = []

def enum_cb(hwnd, lparam):
    if user32.IsWindowVisible(hwnd):
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        w = rect.right - rect.left
        h = rect.bottom - rect.top
        if w > 20 and h > 20:
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            length = user32.GetWindowTextLengthW(hwnd)
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)
            
            class_buff = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, class_buff, 256)
            
            windows.append((pid.value, buff.value, class_buff.value, w, h, hwnd))
    return True

user32.EnumWindows(WNDENUMPROC(enum_cb), 0)

with open(r"c:\Users\seanj\dev\windows_list.txt", "w", encoding="utf-8") as f:
    for pid, title, cls, w, h, hwnd in windows:
        line = f"PID: {pid:6d} | Size: {w:4d}x{h:4d} | Class: {cls:30s} | Title: '{title}'\n"
        f.write(line)

print(f"Wrote {len(windows)} windows to windows_list.txt", flush=True)
