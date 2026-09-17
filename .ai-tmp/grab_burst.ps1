param(
    [string]$OutDir = "D:\Neon3Sdk\.ai-tmp\fxburst26",
    [string]$TitlePrefix = "Neon3",
    [int]$Count = 8,
    [int]$IntervalMs = 50
)
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public static class Win32Grab2 {
    public delegate bool EnumProc(IntPtr h, IntPtr l);
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr l);
    [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder sb, int max);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint flags);
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    public struct RECT { public int L, T, R, B; }
}
"@
[Win32Grab2]::SetProcessDPIAware() | Out-Null
$found = [IntPtr]::Zero
$cb = [Win32Grab2+EnumProc]{ param($h, $l)
    $sb = New-Object System.Text.StringBuilder 512
    [Win32Grab2]::GetWindowText($h, $sb, 512) | Out-Null
    if ([Win32Grab2]::IsWindowVisible($h) -and $sb.ToString().StartsWith($TitlePrefix)) {
        $script:found = $h
        return $false
    }
    return $true
}
[Win32Grab2]::EnumWindows($cb, [IntPtr]::Zero) | Out-Null
if ($found -eq [IntPtr]::Zero) { Write-Error "window not found with prefix: $TitlePrefix"; exit 1 }
$h = $found
if (!(Test-Path $OutDir)) { New-Item -ItemType Directory -Path $OutDir | Out-Null }
$rect = New-Object Win32Grab2+RECT
[Win32Grab2]::GetWindowRect($h, [ref]$rect) | Out-Null
$w = $rect.R - $rect.L
$hh = $rect.B - $rect.T
Write-Host "window ${w}x${hh}"
for ($i = 0; $i -lt $Count; $i++) {
    $bmp = New-Object System.Drawing.Bitmap($w, $hh)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $dc = $g.GetHdc()
    $ok = [Win32Grab2]::PrintWindow($h, $dc, 2)
    $g.ReleaseHdc($dc)
    $g.Dispose()
    $name = "{0:D2}.png" -f $i
    $bmp.Save((Join-Path $OutDir $name), [System.Drawing.Imaging.ImageFormat]::Png)
    $bmp.Dispose()
    Write-Host "saved $name ok=$ok"
    Start-Sleep -Milliseconds $IntervalMs
}
