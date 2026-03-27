# Windows CUA Helper Setup Script
# Run this once on the Windows VM to install the CUA helper and enable SSH/RDP.
#
# Usage (from elevated PowerShell):
#   Set-ExecutionPolicy Bypass -Scope Process -Force
#   .\setup.ps1

$ErrorActionPreference = "Stop"

Write-Host "[setup] Configuring Windows CUA environment..."

# ── 1. Enable OpenSSH Server ─────────────────────────────────────────────────
$sshCapability = Get-WindowsCapability -Online | Where-Object Name -Like 'OpenSSH.Server*'
if ($sshCapability.State -ne 'Installed') {
    Write-Host "[setup] Installing OpenSSH Server..."
    Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
}
Start-Service sshd
Set-Service -Name sshd -StartupType Automatic
Write-Host "[setup] OpenSSH Server is running."

# ── 2. Enable RDP ────────────────────────────────────────────────────────────
Set-ItemProperty -Path 'HKLM:\System\CurrentControlSet\Control\Terminal Server' `
    -Name "fDenyTSConnections" -Value 0
Enable-NetFirewallRule -DisplayGroup "Remote Desktop"
Write-Host "[setup] RDP is enabled."

# ── 3. Install CUA helper script ─────────────────────────────────────────────
$helperDir = "C:\lunar-cua"
if (-not (Test-Path $helperDir)) {
    New-Item -ItemType Directory -Path $helperDir | Out-Null
}

# Exclude from Windows Defender -- the helper uses P/Invoke (user32.dll)
# which Defender may flag as suspicious during real-time scanning.
try {
    Add-MpPreference -ExclusionPath $helperDir -ErrorAction SilentlyContinue
    Write-Host "[setup] Added Defender exclusion for $helperDir"
} catch {
    Write-Host "[setup] Could not add Defender exclusion (non-fatal)"
}

# Copy the helper from the same directory as this script
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Copy-Item "$scriptDir\cua_helper.ps1" "$helperDir\cua_helper.ps1" -Force
Write-Host "[setup] CUA helper installed to $helperDir\cua_helper.ps1"

# ── 4. Set screen resolution (optional, for headless VMs) ────────────────────
# Azure VMs and QEMU VMs may default to low resolution.
# This sets 1280x800 if QRes is available, otherwise logs a note.
$qresPath = "C:\Tools\QRes.exe"
if (Test-Path $qresPath) {
    & $qresPath /x:1280 /y:800
    Write-Host "[setup] Resolution set to 1280x800."
} else {
    Write-Host "[setup] QRes not found at $qresPath -- set resolution manually or install QRes."
}

Write-Host "[setup] Windows CUA setup complete."
Write-Host "[setup] SSH: port 22"
Write-Host "[setup] RDP: port 3389"
Write-Host "[setup] Helper: C:\lunar-cua\cua_helper.ps1"
