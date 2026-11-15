[CmdletBinding(DefaultParameterSetName = 'Plan')]
param(
    [Parameter(Mandatory = $true, ParameterSetName = 'Plan')]
    [Parameter(Mandatory = $true, ParameterSetName = 'Apply')]
    [string] $SourceRoot,
    [Parameter(Mandatory = $true)]
    [string] $ConfigPath,
    [Parameter(ParameterSetName = 'Apply')]
    [switch] $Apply,
    [Parameter(ParameterSetName = 'Rollback')]
    [switch] $Rollback
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ($Apply -or $Rollback) {
    throw 'Legacy native runtime apply/rollback is disabled. Use the fresh-install preview; do not modify a working media server with this experimental script.'
}

function Read-StackarrWindowsConfig {
    param([string] $Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Configuration file was not found: $Path" }
    $config = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    if ($config.version -ne 1) { throw 'Unsupported Windows runtime configuration version.' }
    foreach ($name in 'runtimeRoot', 'releaseRoot') {
        if ([string]::IsNullOrWhiteSpace($config.$name) -or -not [IO.Path]::IsPathRooted($config.$name)) {
            throw "$name must be an absolute local path."
        }
    }
    if ($config.storageGuard.enabled -and ($config.storageGuard.resumeAtGb -le $config.storageGuard.pauseBelowGb)) {
        throw 'Storage Guard resumeAtGb must be greater than pauseBelowGb.'
    }
    if ($config.managedTasks | Where-Object { $_.create -and [string]::IsNullOrWhiteSpace($_.name) }) {
        throw 'Every requested managed task needs a name.'
    }
    return $config
}

function Get-StackarrWindowsPlan {
    param([pscustomobject] $Config, [string] $Root)
    $payload = Join-Path $Root 'platform\windows\runtime'
    if (-not (Test-Path -LiteralPath $payload -PathType Container)) { throw "Runtime payload is missing: $payload" }
    $existing = @(Get-ScheduledTask -ErrorAction SilentlyContinue | Where-Object { $_.TaskName -like 'Stackarr*' } | Select-Object -ExpandProperty TaskName)
    [pscustomobject]@{
        action = 'stage-versioned-runtime'
        source = $payload
        releaseRoot = $Config.releaseRoot
        runtimeRoot = $Config.runtimeRoot
        existingStackarrTasks = $existing
        requestedTasks = @($Config.managedTasks | Where-Object { $_.create } | ForEach-Object { $_.name })
        gateway = [bool]$Config.gateway.enabled
        storageGuard = [bool]$Config.storageGuard.enabled
        note = 'Existing tasks are reported only. This preview does not adopt or replace them.'
    }
}

$config = Read-StackarrWindowsConfig -Path $ConfigPath
$plan = Get-StackarrWindowsPlan -Config $config -Root $SourceRoot
$plan | ConvertTo-Json -Depth 5
