[CmdletBinding(DefaultParameterSetName = 'Plan')]
param(
    [Parameter(Mandatory = $true)]
    [string] $SourceRoot,
    [Parameter(Mandatory = $true)]
    [string] $InstallRoot,
    [Parameter(ParameterSetName = 'Apply')]
    [switch] $Apply
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Test-StackarrFreshSource {
    param([string] $Root)
    $rootPath = (Resolve-Path -LiteralPath $Root).Path
    foreach ($file in 'compose.yaml', 'Dockerfile', 'pyproject.toml') {
        if (-not (Test-Path -LiteralPath (Join-Path $rootPath $file) -PathType Leaf)) {
            throw "This does not look like a Stackarr release directory: $file is missing."
        }
    }
    return $rootPath
}

$source = Test-StackarrFreshSource -Root $SourceRoot
$target = [IO.Path]::GetFullPath($InstallRoot)
$docker = Get-Command docker -ErrorAction SilentlyContinue
$checks = [ordered]@{
    source = $source
    installRoot = $target
    docker = [bool]$docker
    compose = $false
    installDirectorySafe = -not (Test-Path -LiteralPath $target) -or
        -not @(Get-ChildItem -LiteralPath $target -Force -ErrorAction SilentlyContinue).Count
}
if ($docker) {
    $composeCheck = & $docker.Source compose version 2>$null
    $checks.compose = $LASTEXITCODE -eq 0
}
[pscustomobject]$checks | ConvertTo-Json
if (-not $Apply) {
    Write-Output 'Review only. Install Docker Desktop with Linux containers, then rerun with -Apply.'
    exit 0
}
if (-not $checks.docker -or -not $checks.compose) {
    throw 'Docker Compose v2 with a running Linux-container engine is required. No software was installed.'
}
if (-not $checks.installDirectorySafe) {
    throw 'Choose a new empty directory. The fresh installer never overwrites an existing installation.'
}

New-Item -ItemType Directory -Path $target -Force | Out-Null
foreach ($item in 'compose.yaml', 'Dockerfile', 'pyproject.toml', 'requirements.lock', 'stackarr') {
    Copy-Item -LiteralPath (Join-Path $source $item) -Destination $target -Recurse -Force
}
@(
    'STACKARR_ORIGIN=http://localhost:28000'
    'STACKARR_BIND=127.0.0.1'
) | Set-Content -LiteralPath (Join-Path $target '.env') -Encoding ascii
@{ owner = 'stackarr-fresh-v1'; installed = (Get-Date).ToUniversalTime().ToString('o') } |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $target 'stackarr-install.json') -Encoding utf8

Push-Location $target
try {
    & $docker.Source compose up -d --build
    if ($LASTEXITCODE -ne 0) { throw 'Docker Compose could not start Stackarr. The copied source remains for inspection or removal.' }
} finally {
    Pop-Location
}
Write-Output 'Stackarr started locally. Open http://localhost:28000 and use the one-time setup token from docker compose exec stackarr stackarr setup-token.'
