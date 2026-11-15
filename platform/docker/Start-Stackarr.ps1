$ErrorActionPreference = 'Stop'
try {
    $releaseRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
    $composeFile = Join-Path $releaseRoot 'compose.yaml'
    $dockerCommand = Get-Command docker -ErrorAction SilentlyContinue
    $dockerExe = if ($dockerCommand) { $dockerCommand.Source } else {
        @(
            (Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe'),
            'C:\Program Files\Docker\Docker\resources\bin\docker.exe'
        ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    }
    if (-not $dockerExe) { throw 'Docker Desktop was not found. Install or start Docker Desktop, then try again.' }
    $env:PATH = (Split-Path $dockerExe -Parent) + ';' + $env:PATH
    $python = Join-Path $releaseRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python)) {
        throw 'This source checkout needs its local Python environment for the installation controller. The packaged launcher is still being built.'
    }
    $enrollment = Join-Path $releaseRoot '.controller'
    & $python -m stackarr.cli controller-enroll $enrollment
    if ($LASTEXITCODE -ne 0) { throw 'The private installation connection could not be prepared.' }
    $env:STACKARR_CONTROLLER_SHARED_HOST = Join-Path $enrollment 'shared'
    $listener = Get-NetTCPConnection -LocalPort 28010 -State Listen -ErrorAction SilentlyContinue
    if (-not $listener) {
        Start-Process -FilePath $python -ArgumentList @('-m', 'stackarr.cli', 'controller-serve', ('"' + $enrollment + '"')) -WorkingDirectory $releaseRoot -WindowStyle Hidden | Out-Null
    }
    & $dockerExe compose --project-directory $releaseRoot -f $composeFile up -d --build --wait --wait-timeout 120 stackarr
    if ($LASTEXITCODE -ne 0) { throw 'Stackarr could not start. Make sure Docker Desktop is running with Linux containers, then try again.' }
    & $dockerExe compose --project-directory $releaseRoot -f $composeFile exec -T stackarr stackarr controller-probe /run/stackarr-controller
    if ($LASTEXITCODE -ne 0) { throw 'Stackarr opened, but its private installation controller is unavailable. Check Docker Desktop and try Start Stackarr again.' }
    $setupAddress = & $dockerExe compose --project-directory $releaseRoot -f $composeFile exec -T stackarr stackarr setup-link
    if ($LASTEXITCODE -ne 0) { throw 'Stackarr could not open setup. Try Start Stackarr again.' }
    $address = [Uri]($setupAddress.Trim())
    if ($address.Scheme -notin @('http', 'https')) { throw 'The Stackarr address is invalid.' }
    # Keep the one-use invitation out of terminal output. The page removes it.
    Start-Process -FilePath $address.AbsoluteUri
    Write-Host 'Stackarr is open in your browser. Choose your password to begin, or sign in if already set up.'
} catch {
    Write-Host $_.Exception.Message
    Read-Host 'Press Enter to close'
    exit 1
}
