param([string]$OutPath = "D:\Neon3Sdk\.ai-tmp\fx_frame.png")
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32Grab {
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr hwnd, IntPtr hdc, uint flags);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hwnd, out RECT rect);
    [DllImport("user32.dll")] public static extern IntPtr GetWindowDC(IntPtr hwnd);
    [DllImport("user32.dll")] public static extern int ReleaseDC(IntPtr hwnd, IntPtr hdc);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hwnd, int cmd);
    [DllImport("gdi32.dll")] public static extern IntPtr CreateCompatibleDC(IntPtr hdc);
    [DllImport("gdi32.dll")] public static extern IntPtr CreateCompatibleBitmap(IntPtr hdc, int w, int h);
    [DllImport("gdi32.dll")] public static extern IntPtr SelectObject(IntPtr hdc, IntPtr obj);
    [DllImport("gdi32.dll")] public static extern bool DeleteObject(IntPtr obj);
    [DllImport("gdi32.dll")] public static extern bool DeleteDC(IntPtr hdc);
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
}
"@
$p = Get-Process nui_flow_code_editor_demo -ErrorAction SilentlyContinue
if (-not $p) { Write-Output "no process"; exit 1 }
$hwnd = $p.MainWindowHandle
if ($hwnd -eq 0) { Write-Output "no window"; exit 1 }
[Win32Grab]::ShowWindow($hwnd, 9) | Out-Null
Start-Sleep -Milliseconds 300
$r = New-Object Win32Grab+RECT
[Win32Grab]::GetWindowRect($hwnd, [ref]$r) | Out-Null
$w = $r.Right - $r.Left; $h = $r.Bottom - $r.Top
Write-Output "win ${w}x${h}"
$hdcWin = [Win32Grab]::GetWindowDC($hwnd)
$hdcMem = [Win32Grab]::CreateCompatibleDC($hdcWin)
$bmp = [Win32Grab]::CreateCompatibleBitmap($hdcWin, $w, $h)
[Win32Grab]::SelectObject($hdcMem, $bmp) | Out-Null
$ok = [Win32Grab]::PrintWindow($hwnd, $hdcMem, 2)
Write-Output "printwindow=$ok"
$img = [System.Drawing.Image]::FromHbitmap($bmp)
$img.Save($OutPath, [System.Drawing.Imaging.ImageFormat]::Png)
$img.Dispose()
[Win32Grab]::DeleteObject($bmp) | Out-Null
[Win32Grab]::DeleteDC($hdcMem) | Out-Null
[Win32Grab]::ReleaseDC($hwnd, $hdcWin) | Out-Null
Write-Output "saved $OutPath"
