import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32

WM_CLOSE = 0x0010
SW_HIDE = 0

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

found = []

def enum_cb(hwnd, lparam):
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value == 12804:
        length = user32.GetWindowTextLengthW(hwnd)
        buff = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buff, length + 1)
        found.append((hwnd, buff.value))
        print(f"Closing window {hwnd} (Title: '{buff.value}') of PID 12804")
        user32.ShowWindow(hwnd, SW_HIDE)
        user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
    return True

user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
print(f"Done. Processed {len(found)} windows.")

