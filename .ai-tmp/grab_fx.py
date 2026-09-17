import ctypes, subprocess, sys, time
from ctypes import wintypes

ps = subprocess.run(['powershell','-NoProfile','-Command',
  "Get-Process nui_flow_code_editor_demo | Select-Object -ExpandProperty MainWindowHandle"],
  capture_output=True, text=True)
hwnd = int(ps.stdout.strip().split()[0])
print('hwnd', hex(hwnd))

user32 = ctypes.WinDLL('user32', use_last_error=True)
gdi32 = ctypes.WinDLL('gdi32', use_last_error=True)

rect = wintypes.RECT()
user32.GetWindowRect(ctypes.wintypes.HWND(hwnd), ctypes.byref(rect))
w = rect.right - rect.left
h = rect.bottom - rect.top
print('win', w, h)

# Bring window to front-ish for capture
user32.ShowWindow(ctypes.wintypes.HWND(hwnd), 9)  # SW_RESTORE

hdc_win = user32.GetWindowDC(ctypes.wintypes.HWND(hwnd))
hdc_mem = gdi32.CreateCompatibleDC(hdc_win)
bmp = gdi32.CreateCompatibleBitmap(hdc_win, w, h)
gdi32.SelectObject(hdc_mem, bmp)
ok = user32.PrintWindow(ctypes.wintypes.HWND(hwnd), hdc_mem, 2)  # PW_RENDERFULLCONTENT
print('printwindow', ok, 'gle', ctypes.get_last_error())

# Save via System.Drawing
sys.path.append(r'D:\Neon3Sdk\.ai-tmp')
import clr  # noqa
