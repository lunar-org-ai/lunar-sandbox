# CUA Helper for Windows
# Provides screenshot, mouse, keyboard, and scroll primitives for
# the WindowsCUAActionHandler to call over SSH.
#
# Usage:
#   powershell -File C:\lunar-cua\cua_helper.ps1 -Action screenshot
#   powershell -File C:\lunar-cua\cua_helper.ps1 -Action mouse_move -X 300 -Y 400
#   powershell -File C:\lunar-cua\cua_helper.ps1 -Action left_click -X 300 -Y 400
#   powershell -File C:\lunar-cua\cua_helper.ps1 -Action type -Text "hello world"
#   powershell -File C:\lunar-cua\cua_helper.ps1 -Action key -Keys "enter"
#   powershell -File C:\lunar-cua\cua_helper.ps1 -Action scroll -X 300 -Y 400 -Direction down -Clicks 3
#   powershell -File C:\lunar-cua\cua_helper.ps1 -Action cursor_position
#   powershell -File C:\lunar-cua\cua_helper.ps1 -Action health_check

param(
    [Parameter(Mandatory=$true)]
    [string]$Action,

    [int]$X = 0,
    [int]$Y = 0,
    [int]$EndX = 0,
    [int]$EndY = 0,
    [string]$Text = "",
    [string]$Keys = "",
    [string]$Direction = "down",
    [int]$Clicks = 3,
    [int]$Quality = 70,
    [string]$Button = "left"
)

$ErrorActionPreference = "Stop"

# ── Load .NET assemblies ─────────────────────────────────────────────────────
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

# ── P/Invoke for mouse and keyboard ─────────────────────────────────────────
Add-Type @"
using System;
using System.Runtime.InteropServices;

public class NativeInput {
    [DllImport("user32.dll")]
    public static extern bool SetCursorPos(int X, int Y);

    [DllImport("user32.dll")]
    public static extern void mouse_event(uint dwFlags, int dx, int dy, int dwData, IntPtr dwExtraInfo);

    [DllImport("user32.dll")]
    public static extern bool GetCursorPos(out POINT lpPoint);

    [StructLayout(LayoutKind.Sequential)]
    public struct POINT {
        public int X;
        public int Y;
    }

    // mouse_event flags
    public const uint MOUSEEVENTF_LEFTDOWN   = 0x0002;
    public const uint MOUSEEVENTF_LEFTUP     = 0x0004;
    public const uint MOUSEEVENTF_RIGHTDOWN  = 0x0008;
    public const uint MOUSEEVENTF_RIGHTUP    = 0x0010;
    public const uint MOUSEEVENTF_MIDDLEDOWN = 0x0020;
    public const uint MOUSEEVENTF_MIDDLEUP   = 0x0040;
    public const uint MOUSEEVENTF_WHEEL      = 0x0800;

    public const int WHEEL_DELTA = 120;
}
"@

# ── Helper functions ─────────────────────────────────────────────────────────

function Take-Screenshot {
    param([int]$JpegQuality = 70)

    $screen = [System.Windows.Forms.Screen]::PrimaryScreen
    $bounds = $screen.Bounds
    $bitmap = New-Object System.Drawing.Bitmap($bounds.Width, $bounds.Height)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $graphics.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
    $graphics.Dispose()

    # Encode as JPEG with specified quality
    $encoder = [System.Drawing.Imaging.ImageCodecInfo]::GetImageEncoders() |
        Where-Object { $_.MimeType -eq "image/jpeg" }
    $encoderParams = New-Object System.Drawing.Imaging.EncoderParameters(1)
    $encoderParams.Param[0] = New-Object System.Drawing.Imaging.EncoderParameter(
        [System.Drawing.Imaging.Encoder]::Quality, [long]$JpegQuality
    )

    $stream = New-Object System.IO.MemoryStream
    $bitmap.Save($stream, $encoder, $encoderParams)
    $bitmap.Dispose()

    $bytes = $stream.ToArray()
    $stream.Dispose()

    return [Convert]::ToBase64String($bytes)
}

function Move-Mouse {
    param([int]$TargetX, [int]$TargetY)
    [NativeInput]::SetCursorPos($TargetX, $TargetY)
}

function Click-Mouse {
    param(
        [int]$TargetX,
        [int]$TargetY,
        [string]$ClickButton = "left",
        [int]$ClickCount = 1
    )

    [NativeInput]::SetCursorPos($TargetX, $TargetY)
    Start-Sleep -Milliseconds 10

    for ($i = 0; $i -lt $ClickCount; $i++) {
        switch ($ClickButton) {
            "left" {
                [NativeInput]::mouse_event([NativeInput]::MOUSEEVENTF_LEFTDOWN, 0, 0, 0, [IntPtr]::Zero)
                [NativeInput]::mouse_event([NativeInput]::MOUSEEVENTF_LEFTUP, 0, 0, 0, [IntPtr]::Zero)
            }
            "right" {
                [NativeInput]::mouse_event([NativeInput]::MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, [IntPtr]::Zero)
                [NativeInput]::mouse_event([NativeInput]::MOUSEEVENTF_RIGHTUP, 0, 0, 0, [IntPtr]::Zero)
            }
            "middle" {
                [NativeInput]::mouse_event([NativeInput]::MOUSEEVENTF_MIDDLEDOWN, 0, 0, 0, [IntPtr]::Zero)
                [NativeInput]::mouse_event([NativeInput]::MOUSEEVENTF_MIDDLEUP, 0, 0, 0, [IntPtr]::Zero)
            }
        }
        if ($i -lt ($ClickCount - 1)) {
            Start-Sleep -Milliseconds 50
        }
    }
}

function Drag-Mouse {
    param(
        [int]$StartX, [int]$StartY,
        [int]$DestX, [int]$DestY
    )

    [NativeInput]::SetCursorPos($StartX, $StartY)
    Start-Sleep -Milliseconds 50
    [NativeInput]::mouse_event([NativeInput]::MOUSEEVENTF_LEFTDOWN, 0, 0, 0, [IntPtr]::Zero)
    Start-Sleep -Milliseconds 100
    [NativeInput]::SetCursorPos($DestX, $DestY)
    Start-Sleep -Milliseconds 100
    [NativeInput]::mouse_event([NativeInput]::MOUSEEVENTF_LEFTUP, 0, 0, 0, [IntPtr]::Zero)
}

function Scroll-Mouse {
    param(
        [int]$TargetX, [int]$TargetY,
        [string]$ScrollDirection = "down",
        [int]$ScrollClicks = 3
    )

    [NativeInput]::SetCursorPos($TargetX, $TargetY)
    Start-Sleep -Milliseconds 10

    $delta = [NativeInput]::WHEEL_DELTA * $ScrollClicks
    if ($ScrollDirection -eq "down") { $delta = -$delta }

    [NativeInput]::mouse_event([NativeInput]::MOUSEEVENTF_WHEEL, 0, 0, $delta, [IntPtr]::Zero)
}

function Type-Text {
    param([string]$InputText)
    # SendKeys handles special characters and modifiers
    [System.Windows.Forms.SendKeys]::SendWait($InputText)
}

function Press-Key {
    param([string]$KeyCombo)

    # Map common key names to SendKeys format
    $keyMap = @{
        "enter"     = "{ENTER}"
        "return"    = "{ENTER}"
        "tab"       = "{TAB}"
        "escape"    = "{ESC}"
        "esc"       = "{ESC}"
        "backspace" = "{BACKSPACE}"
        "delete"    = "{DELETE}"
        "del"       = "{DELETE}"
        "home"      = "{HOME}"
        "end"       = "{END}"
        "pageup"    = "{PGUP}"
        "pagedown"  = "{PGDN}"
        "up"        = "{UP}"
        "down"      = "{DOWN}"
        "left"      = "{LEFT}"
        "right"     = "{RIGHT}"
        "space"     = " "
        "f1"        = "{F1}"
        "f2"        = "{F2}"
        "f3"        = "{F3}"
        "f4"        = "{F4}"
        "f5"        = "{F5}"
        "f6"        = "{F6}"
        "f7"        = "{F7}"
        "f8"        = "{F8}"
        "f9"        = "{F9}"
        "f10"       = "{F10}"
        "f11"       = "{F11}"
        "f12"       = "{F12}"
    }

    # Handle modifier+key combos like "ctrl+c", "alt+f4", "ctrl+shift+s"
    $parts = $KeyCombo.ToLower() -split '\+'
    $modPrefix = ""
    $mainKey = ""

    foreach ($part in $parts) {
        $trimmed = $part.Trim()
        switch ($trimmed) {
            "ctrl"    { $modPrefix += "^" }
            "control" { $modPrefix += "^" }
            "alt"     { $modPrefix += "%" }
            "shift"   { $modPrefix += "+" }
            "super"   { $modPrefix += "^{ESC}" }  # Windows key approximation
            "win"     { $modPrefix += "^{ESC}" }
            default   {
                if ($keyMap.ContainsKey($trimmed)) {
                    $mainKey = $keyMap[$trimmed]
                } else {
                    # Single character key
                    $mainKey = $trimmed
                }
            }
        }
    }

    $sendKeysStr = "${modPrefix}${mainKey}"
    [System.Windows.Forms.SendKeys]::SendWait($sendKeysStr)
}

function Get-CursorPosition {
    $point = New-Object NativeInput+POINT
    [NativeInput]::GetCursorPos([ref]$point) | Out-Null
    return @{ X = $point.X; Y = $point.Y }
}

# ── Main dispatch ────────────────────────────────────────────────────────────

switch ($Action.ToLower()) {
    "screenshot" {
        $b64 = Take-Screenshot -JpegQuality $Quality
        Write-Output $b64
    }
    "mouse_move" {
        Move-Mouse -TargetX $X -TargetY $Y
        Write-Output "OK"
    }
    "left_click" {
        Click-Mouse -TargetX $X -TargetY $Y -ClickButton "left"
        Write-Output "OK"
    }
    "right_click" {
        Click-Mouse -TargetX $X -TargetY $Y -ClickButton "right"
        Write-Output "OK"
    }
    "double_click" {
        Click-Mouse -TargetX $X -TargetY $Y -ClickButton "left" -ClickCount 2
        Write-Output "OK"
    }
    "middle_click" {
        Click-Mouse -TargetX $X -TargetY $Y -ClickButton "middle"
        Write-Output "OK"
    }
    "left_click_drag" {
        Drag-Mouse -StartX $X -StartY $Y -DestX $EndX -DestY $EndY
        Write-Output "OK"
    }
    "type" {
        Type-Text -InputText $Text
        Write-Output "OK"
    }
    "key" {
        Press-Key -KeyCombo $Keys
        Write-Output "OK"
    }
    "scroll" {
        Scroll-Mouse -TargetX $X -TargetY $Y -ScrollDirection $Direction -ScrollClicks $Clicks
        Write-Output "OK"
    }
    "cursor_position" {
        $pos = Get-CursorPosition
        Write-Output "X=$($pos.X)"
        Write-Output "Y=$($pos.Y)"
    }
    "health_check" {
        # Verify we can take a screenshot (display is accessible)
        try {
            $null = Take-Screenshot -JpegQuality 10
            Write-Output "HEALTHY"
        } catch {
            Write-Output "UNHEALTHY: $($_.Exception.Message)"
            exit 1
        }
    }
    default {
        Write-Error "Unknown action: $Action"
        exit 1
    }
}
