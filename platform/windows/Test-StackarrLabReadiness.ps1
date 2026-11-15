# Read-only lab inventory. Does not run Docker, install software, or access media.
[CmdletBinding()]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$os = Get-CimInstance Win32_OperatingSystem
$computer = Get-CimInstance Win32_ComputerSystem
$autologon = Get-ItemProperty -LiteralPath 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon' -Name AutoAdminLogon -ErrorAction SilentlyContinue
$autoEnabled = $null
if ($null -ne $autologon) { $autoEnabled = $autologon.AutoAdminLogon -eq '1' }
[ordered]@{
    schema = 1
    windowsBuild = $os.BuildNumber
    architecture = $os.OSArchitecture
    memoryGiB = [math]::Round($computer.TotalPhysicalMemory / 1GB, 1)
    hypervisorPresent = [bool]$computer.HypervisorPresent
    dockerCommandAvailable = [bool](Get-Command docker -ErrorAction SilentlyContinue)
    hyperVCommandAvailable = [bool](Get-Command Get-VM -ErrorAction SilentlyContinue)
    autoAdminLogonValueEnabled = $autoEnabled
    verdict = 'inventory-only; not proof of lab isolation, engine health, or signed-out startup'
} | ConvertTo-Json
