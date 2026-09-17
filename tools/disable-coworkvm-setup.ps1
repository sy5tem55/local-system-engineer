# disable-coworkvm-setup.ps1
# One-time setup: permanently disable CoworkVMService (Claude Desktop MSIX) auto-start.
# Run in an ELEVATED (Administrator) Windows PowerShell.
# Source: https://github.com/anthropics/claude-code/issues/57371 (manifest-verified 2026-09-12)
# v2: package-SID grant now uses built-in Win32_Sid (no ActiveDirectory module) and
#     is non-fatal, so a SID-resolution hiccup can't abort before the boot guard is set.

$ErrorActionPreference = 'Stop'
$svcName = 'CoworkVMService'
$regPath = "HKLM:\SYSTEM\CurrentControlSet\Services\$svcName"
$payloadDir  = 'C:\ProgramData\lse'
$payloadPath = Join-Path $payloadDir 'disable-coworkvm.ps1'

# --- 0. Sanity ----------------------------------------------------------------
$svc = Get-Service $svcName -ErrorAction Stop
Write-Host ("[0] Found: {0}  Status={1}  StartType={2}" -f $svc.Name, $svc.Status, $svc.StartType)

# --- 1. Stop it now ------------------------------------------------------------
Stop-Service $svcName -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
Write-Host ("[1] Now: {0}" -f (Get-Service $svcName).Status)

# --- 2. Take ownership of the package-protected service registry key -----------
$admSid = New-Object System.Security.Principal.SecurityIdentifier('S-1-5-32-544') # BUILTIN\Administrators
$k = [Microsoft.Win32.Registry]::LocalMachine.OpenSubKey(
    "SYSTEM\CurrentControlSet\Services\$svcName",
    [Microsoft.Win32.RegistryKeyPermissionCheck]::ReadWriteSubTree,
    [System.Security.AccessControl.RegistryRights]::TakeOwnership)
$acl = $k.GetAccessControl()
$acl.SetOwner($admSid)
$k.SetAccessControl($acl)

$k = [Microsoft.Win32.Registry]::LocalMachine.OpenSubKey(
    "SYSTEM\CurrentControlSet\Services\$svcName",
    [Microsoft.Win32.RegistryKeyPermissionCheck]::ReadWriteSubTree,
    [System.Security.AccessControl.RegistryRights]::ChangePermissions)
$acl = $k.GetAccessControl()
$acl.AddAccessRule((New-Object System.Security.AccessControl.RegistryAccessRule($admSid, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')))
$pkg = Get-AppxPackage -Name 'Claude' -ErrorAction SilentlyContinue
if ($pkg) {
    try {
        # Resolve the package family name (SDDL form) to a real SID using the
        # built-in Win32_Sid CIM class -- no ActiveDirectory module required.
        $sidStr = (Get-CimInstance Win32_Sid -Filter "Domain='$($pkg.PackageFamilyName)'").Sid
        $pkgSid = New-Object System.Security.Principal.SecurityIdentifier($sidStr)
        $acl.AddAccessRule((New-Object System.Security.AccessControl.RegistryAccessRule($pkgSid, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')))
        Write-Host ("[2] Ownership -> Administrators; FullControl granted to Administrators + package {0}" -f $pkg.PackageFamilyName)
    } catch {
        Write-Warning ("[2] Could not resolve package SID (" + $_.Exception.Message + ") -- granting FullControl to Administrators only. Continuing.")
        Write-Host "[2] Ownership -> Administrators; FullControl granted to Administrators (package SID unresolved)"
    }
} else {
    Write-Host "[2] Ownership -> Administrators; FullControl granted to Administrators (no Claude package found)"
}
$k.SetAccessControl($acl)

# --- 3. Disable auto-start (Start=4 = Disabled) --------------------------------
Set-ItemProperty $regPath -Name Start -Value 4 -Type DWord
Write-Host ("[3] Start= {0}  (0=Boot 1=System 2=Auto 3=Manual 4=Disabled)" -f (Get-ItemProperty $regPath).Start)

# --- 4. Boot task guard (survives package updates that re-register the service) --
New-Item -ItemType Directory -Path $payloadDir -Force | Out-Null
$payloadContent = @'
$svcKey = 'HKLM:\SYSTEM\CurrentControlSet\Services\CoworkVMService'
if (Test-Path $svcKey) {
    if ((Get-ItemProperty $svcKey).Start -ne 4) {
        Set-ItemProperty $svcKey -Name Start -Value 4 -Type DWord
    }
    Stop-Service CoworkVMService -Force -ErrorAction SilentlyContinue
}
'@
Set-Content -Path $payloadPath -Value $payloadContent -Encoding ASCII

$action    = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ("-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$payloadPath`"")
$trigger   = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId 'NT AUTHORITY\SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$settings  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName 'DisableCoworkVMService' -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Write-Host "[4] Boot task 'DisableCoworkVMService' registered (runs as SYSTEM at every boot)"

# --- 5. Verify --------------------------------------------------------------------
Write-Host "[5] Verification:"
Get-Service $svcName | Format-List Name, Status, StartType
Get-ScheduledTask -TaskName 'DisableCoworkVMService' | Format-List TaskName, State
Write-Host "Done. CoworkVMService will NOT auto-start after the next reboot."
