param([string]$Output = "docs\interface.png")
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing
Add-Type @'
using System;
using System.Runtime.InteropServices;
public class AppWindow {
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
  [StructLayout(LayoutKind.Sequential)] public struct POINT { public int X, Y; }
  [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr h, out RECT rect);
  [DllImport("user32.dll")] public static extern bool ClientToScreen(IntPtr h, ref POINT point);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int w, int height, uint flags);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT rect);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
}
'@
[AppWindow]::SetProcessDPIAware() | Out-Null
$app = Get-Process | Where-Object { $_.MainWindowTitle -like "TrainerRelay*" } | Select-Object -First 1
if (-not $app) { throw "Open bridge.py --preview before capturing the interface." }
[AppWindow]::ShowWindow($app.MainWindowHandle, 9) | Out-Null
[AppWindow]::SetForegroundWindow($app.MainWindowHandle) | Out-Null
[AppWindow]::SetWindowPos($app.MainWindowHandle,[IntPtr](-1),0,0,0,0,3) | Out-Null
Start-Sleep -Milliseconds 750
$rect = New-Object AppWindow+RECT
[AppWindow]::GetClientRect($app.MainWindowHandle, [ref]$rect) | Out-Null
$origin = New-Object AppWindow+POINT
[AppWindow]::ClientToScreen($app.MainWindowHandle, [ref]$origin) | Out-Null
$bitmap = New-Object System.Drawing.Bitmap ($rect.Right-$rect.Left),($rect.Bottom-$rect.Top)
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
try {
    $graphics.CopyFromScreen($origin.X,$origin.Y,0,0,$bitmap.Size)
    $bitmap.Save((Join-Path (Get-Location).Path $Output),[System.Drawing.Imaging.ImageFormat]::Png)
} finally {
    $graphics.Dispose(); $bitmap.Dispose()
    [AppWindow]::SetWindowPos($app.MainWindowHandle,[IntPtr](-2),0,0,0,0,3) | Out-Null
}
