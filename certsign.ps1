
#Retieve the cert

$cert = Get-ChildItem Cert:\CurrentUser\My | Where-Object { $_.Subject -like "*SY5TEM5*" }
Set-AuthenticodeSignature "C:\Users\SY5\Documents\Claude\Projects\local-system-engineer\lse-stack-launch.ps1" -Certificate $cert

#Sign it

Get-AuthenticodeSignature "C:\Users\SY5\Documents\Claude\Projects\local-system-engineer\lse-stack-launch.ps1" | Select-Object Status, StatusMessage









PS C:\Users\SY5> $cert = Get-ChildItem Cert:\CurrentUser\My | Where-Object { $_.Subject -like "*SY5TEM5*" }
PS C:\Users\SY5> Set-AuthenticodeSignature "C:\Users\SY5\Documents\Claude\Projects\local-system-engineer\lse-stack-launch.ps1" -Certificate $cert

    Directory: C:\Users\SY5\Documents\Claude\Projects\local-system-engineer

SignerCertificate                         Status                         StatusMessage                 Path
-----------------                         ------                         -------------                 ----
2ACAC827D2AF5D24469E07B33A1E62A7464826FB  Valid                          Signature verified.           lse-stack-launch.ps1

PS C:\Users\SY5> Get-AuthenticodeSignature "C:\Users\SY5\Documents\Claude\Projects\local-system-engineer\lse-stack-launch.ps1" | Select-Object Status, StatusMessage

Status StatusMessage
------ -------------
 Valid Signature verified.

PS C:\Users\SY5>