param([string]$Name = 'dashboard', [int]$Width = 1440, [int]$Height = 900)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
Add-Type @'
using System;
using System.Runtime.InteropServices;
public class DashboardCapture {
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int w, int height, uint flags);
}
'@
$app = Get-Process aiei_wealth | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if (!$app) { throw 'No visible application window found.' }
[DashboardCapture]::SetWindowPos($app.MainWindowHandle, [IntPtr]::Zero, 20, 20, $Width, $Height, 0x0040) | Out-Null
[DashboardCapture]::SetForegroundWindow($app.MainWindowHandle) | Out-Null
Start-Sleep -Milliseconds 800
$keys = New-Object -ComObject WScript.Shell
$keys.SendKeys('^1')
Start-Sleep -Milliseconds 1200
$rect = New-Object DashboardCapture+RECT
[DashboardCapture]::GetWindowRect($app.MainWindowHandle, [ref]$rect) | Out-Null
$bitmap = New-Object Drawing.Bitmap ($rect.Right-$rect.Left), ($rect.Bottom-$rect.Top)
$graphics = [Drawing.Graphics]::FromImage($bitmap)
$graphics.CopyFromScreen($rect.Left, $rect.Top, 0, 0, $bitmap.Size)
$folder = Join-Path $PSScriptRoot '..\artifacts\dashboard'
New-Item -ItemType Directory -Path $folder -Force | Out-Null
$path = Join-Path $folder ($Name + '.png')
$bitmap.Save($path, [Drawing.Imaging.ImageFormat]::Png)
$graphics.Dispose()
$bitmap.Dispose()
Write-Output $path
