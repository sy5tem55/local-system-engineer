<#
  ipad-lan-setup.ps1 — expose the Faust server (WSL2, port 8787) to the LAN so an iPad
  (or any device) can reach it at http://<this-PC-LAN-IP>:8787, no SSH tunnel.

  This is the PORT-PROXY route (works on Win10 + Win11). It forwards the Windows host's
  0.0.0.0:8787 to WSL2's current internal IP and opens the firewall. WSL2's IP changes on
  every reboot, so RE-RUN this after a Windows/WSL restart (or prefer mirrored networking —
  see the README). Run in an ADMIN PowerShell:  powershell -ExecutionPolicy Bypass -File .\ipad-lan-setup.ps1

  Undo:  netsh interface portproxy delete v4tov4 listenport=8787 listenaddress=0.0.0.0
#>
param([int]$Port = 8787)

# --- must be admin ---
$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
         ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) { Write-Error "Run this in an ADMIN PowerShell (right-click > Run as administrator)."; exit 1 }

# --- find WSL2's current IP ---
$wslIp = (wsl hostname -I).Trim().Split(" ")[0]
if (-not $wslIp) { Write-Error "Could not get WSL IP (is WSL running? try 'wsl -d Ubuntu echo ok')."; exit 1 }
Write-Host "WSL2 IP: $wslIp" -ForegroundColor Cyan

# --- (re)create the port proxy ---
netsh interface portproxy delete v4tov4 listenport=$Port listenaddress=0.0.0.0 2>$null | Out-Null
netsh interface portproxy add    v4tov4 listenport=$Port listenaddress=0.0.0.0 connectport=$Port connectaddress=$wslIp
Write-Host "Port proxy: 0.0.0.0:$Port  ->  ${wslIp}:$Port" -ForegroundColor Green

# --- firewall rule (idempotent) ---
$ruleName = "Faust $Port (WSL LAN)"
if (-not (Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue)) {
  New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Action Allow `
    -Protocol TCP -LocalPort $Port -Profile Private | Out-Null
  Write-Host "Firewall: allowed inbound TCP $Port (Private profile)" -ForegroundColor Green
} else { Write-Host "Firewall rule already present." -ForegroundColor DarkGray }

# --- show the LAN URL to open on the iPad ---
$lan = (Get-NetIPAddress -AddressFamily IPv4 |
        Where-Object { $_.IPAddress -notmatch '^(127\.|169\.254\.|172\.(1[6-9]|2\d|3[01])\.)' -and
                       $_.PrefixOrigin -ne 'WellKnown' } |
        Select-Object -First 1 -ExpandProperty IPAddress)
Write-Host "`nOpen on the iPad (same Wi-Fi):  http://${lan}:$Port" -ForegroundColor Yellow
Write-Host "Active proxies:" -ForegroundColor DarkGray
netsh interface portproxy show v4tov4
