[CmdletBinding()]
param(
    [string]$StateDirectory = '',
    [string]$MediaFolder = '',
    [int]$Port = 28000,
    [int]$ControllerPort = 28010,
    [switch]$NoBrowser,
    [string]$ResultFile = ''
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$env:PYINSTALLER_RESET_ENVIRONMENT = '1'
function Get-PreviewHash([string]$Path) {
    $hash = [Security.Cryptography.SHA256]::Create()
    $stream = [IO.File]::OpenRead($Path)
    try { return ([BitConverter]::ToString($hash.ComputeHash($stream))).Replace('-', '').ToLowerInvariant() }
    finally { $stream.Dispose(); $hash.Dispose() }
}
function Find-PreviewPort([int]$Requested, [int[]]$Reserved) {
    if ($Requested -lt 1 -or $Requested -gt 65535) { throw 'Ports must be between 1 and 65535.' }
    $candidates = @($Requested..([Math]::Min($Requested + 255, 65535))) + @(49152..49407)
    foreach ($candidate in $candidates) {
        if ($Reserved -contains $candidate) { continue }
        $addresses = @([Net.IPAddress]::Any, [Net.IPAddress]::Loopback)
        $free = $true
        foreach ($address in $addresses) {
            $listener = New-Object Net.Sockets.TcpListener($address, $candidate)
            $listener.ExclusiveAddressUse = $true
            try { $listener.Start() } catch { $free = $false } finally { $listener.Stop() }
            if (-not $free) { break }
        }
        if ($free) { return [int]$candidate }
    }
    throw 'No available port was found. Free a port and reopen Stackarr; existing services were left running.'
}
function Write-PreviewResult([string]$Address) {
    Write-PreviewJson @{url=$Address}
}
function Find-StackarrProject {
    $used = @()
    foreach ($arguments in @(
        @('ps', '-a', '--format', '{{.Labels}}'),
        @('volume', 'ls', '--format', '{{.Labels}}'),
        @('network', 'ls', '--format', '{{.Labels}}')
    )) {
        # Windows PowerShell removes embedded quotes in native arguments.
        # Read the label list without a quoted Go-template parameter instead.
        $labels = @(& $dockerExe @arguments)
        if ($LASTEXITCODE -ne 0) { throw 'Docker groups could not be checked. Start Docker Desktop, then reopen Stackarr.' }
        foreach ($line in $labels) {
            foreach ($label in ([string]$line).Split(',')) {
                if ($label.StartsWith('com.docker.compose.project=')) {
                    $used += $label.Substring('com.docker.compose.project='.Length)
                }
            }
        }
    }
    $number = 1
    $candidate = 'stackarr-controller'
    while ($used -contains $candidate) {
        $number++
        $candidate = 'stackarr-controller-' + $number
    }
    return $candidate
}
function Write-PreviewJson([hashtable]$Value) {
    if (-not $ResultFile) { return }
    $bytes = [Text.Encoding]::UTF8.GetBytes(($Value | ConvertTo-Json -Compress))
    $stream = [IO.File]::Open($ResultFile, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try { $stream.Write($bytes, 0, $bytes.Length); $stream.Flush($true) } finally { $stream.Dispose() }
}
try {
    $manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'manifest.json') -Raw | ConvertFrom-Json
    if ($manifest.schema -ne 1) { throw 'This preview package format is not supported.' }
    foreach ($name in @('StackarrPreview.exe', 'stackarr-image.tar')) {
        $payloadPath = Join-Path $PSScriptRoot $name
        $expected = $manifest.files.$name
        if ($expected -notmatch '^[a-f0-9]{64}$' -or (Get-PreviewHash $payloadPath) -ne $expected) {
            throw 'A preview download is incomplete or changed. Download the complete package again.'
        }
    }
    $workerExe = Join-Path $PSScriptRoot 'StackarrPreview.exe'
    if (-not $NoBrowser) {
        $options = @('--package-first-run', '--dashboard-port', [string]$Port, '--controller-port', [string]$ControllerPort)
        if ($StateDirectory) { $options += @('--data-directory', ('"' + $StateDirectory + '"')) }
        if ($MediaFolder) { $options += @('--media-folder', ('"' + $MediaFolder + '"')) }
        Start-Process -FilePath $workerExe -ArgumentList $options -WindowStyle Hidden | Out-Null
        exit 0
    }
    $dockerCommand = Get-Command docker -ErrorAction SilentlyContinue
    $dockerExe = if ($dockerCommand) { $dockerCommand.Source } else {
        @((Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe'),
          (Join-Path $env:ProgramFiles 'Docker\Docker\resources\bin\docker.exe')) |
            Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    }
    if (-not $dockerExe) { throw 'Install Docker Desktop, open it with Linux containers, then run Start Stackarr again.' }
    if (-not $StateDirectory) { $StateDirectory = Join-Path $env:LOCALAPPDATA 'Stackarr\DockerPreview' }
    if (-not [IO.Path]::IsPathRooted($StateDirectory)) { throw 'Choose an absolute preview data directory.' }
    $stateRoot = [IO.Path]::GetFullPath($StateDirectory)
    if ($stateRoot -eq [IO.Path]::GetPathRoot($stateRoot)) { throw 'Choose a dedicated preview data directory.' }
    if (Test-Path -LiteralPath $stateRoot) {
        $stateItem = Get-Item -LiteralPath $stateRoot
        if ($stateItem.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'The preview data directory must not be a filesystem link.' }
    }
    New-Item -ItemType Directory -Path $stateRoot -Force | Out-Null
    # The active release lives with this installation. Reopening an older package
    # must not overwrite a completed update or bypass interrupted-update recovery.
    if (Test-Path -LiteralPath (Join-Path $stateRoot 'stackarr-runtime.json')) {
        $maintenanceReport = Join-Path $stateRoot ('managed-start-' + [guid]::NewGuid().ToString('N') + '.json')
        $managed = Start-Process -FilePath $workerExe -ArgumentList @('--stackarr-start', ('"' + $stateRoot + '"'), '--maintenance-report', ('"' + $maintenanceReport + '"')) -PassThru -WindowStyle Hidden
        if (-not $managed.WaitForExit(180000)) { throw 'Stackarr maintenance is still running. Reopen after checking its saved maintenance status.' }
        if ($managed.ExitCode -ne 0) {
            if (-not $NoBrowser -or $ResultFile) {
                Start-Process -FilePath $workerExe -ArgumentList @('--stackarr-repair', ('"' + $stateRoot + '"')) -WindowStyle Hidden | Out-Null
            }
            if ($ResultFile) { Write-PreviewJson @{review='repair'}; exit 0 }
            throw 'Stackarr could not start. Restore Docker/storage access, then review repair in the local window or reopen this package. Previous releases and checkpoints are retained.'
        }
        $managedResult = Get-Content -LiteralPath $maintenanceReport -Raw | ConvertFrom-Json
        if ($managedResult.PSObject.Properties.Name -contains 'removed' -and $managedResult.removed) {
            if (-not $NoBrowser -or $ResultFile) {
                Start-Process -FilePath $workerExe -ArgumentList @('--stackarr-reinstall', ('"' + $stateRoot + '"')) -WindowStyle Hidden | Out-Null
            }
            if ($ResultFile) { Write-PreviewJson @{review='reinstall'} }
            Write-Host 'Stackarr is removed with settings retained. Review reinstall in the local window; media apps keep running.'
            exit 0
        }
        Write-PreviewResult $managedResult.url
        if (-not $NoBrowser) { Start-Process -FilePath $managedResult.url }
        Write-Host ('Stackarr is ready at ' + $managedResult.url + '. Your saved active release was used.')
        exit 0
    }
    $installPath = Join-Path $stateRoot 'installation.json'
    if (Test-Path -LiteralPath $installPath) {
        $installation = Get-Content -LiteralPath $installPath -Raw | ConvertFrom-Json
        if ($installation.owner -ne 'stackarr-docker-preview-v1' -or $installation.project -notmatch '^(stackarr-preview-[a-f0-9]{12}|stackarr-controller(-[2-9]|-[1-9][0-9]+)?)$') {
            throw 'This directory does not belong to a supported Stackarr preview.'
        }
    } else {
        if (@(Get-ChildItem -LiteralPath $stateRoot -Force).Count) { throw 'Choose an empty preview data directory. Existing files will be preserved.' }
        $mediaRoot = ''
        if ($MediaFolder -and (-not [IO.Path]::IsPathRooted($MediaFolder) -or -not (Test-Path -LiteralPath $MediaFolder -PathType Container))) {
            throw 'Choose an existing absolute media folder.'
        }
        if ($MediaFolder) {
            $mediaRoot = [IO.Path]::GetFullPath($MediaFolder)
            if ($mediaRoot -eq [IO.Path]::GetPathRoot($mediaRoot)) { throw 'Choose a media folder rather than an entire drive.' }
        }
        foreach ($number in @($Port, $ControllerPort)) {
            if ($number -lt 1 -or $number -gt 65535) { throw 'Preview ports must be between 1 and 65535.' }
        }
        $requestedPort = $Port
        $Port = Find-PreviewPort $Port @($ControllerPort)
        $requestedControllerPort = $ControllerPort
        $ControllerPort = Find-PreviewPort $ControllerPort @($Port)
        if ($Port -ne $requestedPort) { Write-Host ('The requested dashboard port is busy. Stackarr will use ' + $Port + '; existing apps stay running.') }
        if ($ControllerPort -ne $requestedControllerPort) { Write-Host 'The requested private setup port is busy. Stackarr selected an available port.' }
        $installation = [pscustomobject]@{owner='stackarr-docker-preview-v1';project=(Find-StackarrProject);port=$Port;controller_port=$ControllerPort;media_root=$mediaRoot}
        $installation | ConvertTo-Json | Set-Content -LiteralPath $installPath -Encoding utf8
    }
    $Port = [int]$installation.port
    $ControllerPort = [int]$installation.controller_port
    $origin = 'http://localhost:' + $Port
    $runtimePath = Join-Path $stateRoot ('runtime-' + [guid]::NewGuid().ToString('N') + '.json')
    $runtime = Start-Process -FilePath $workerExe -ArgumentList @('--runtime-report', ('"' + $runtimePath + '"')) -PassThru -WindowStyle Hidden
    if (-not $runtime.WaitForExit(60000)) { $runtime.Kill(); throw 'Docker checks timed out. Open Docker Desktop and try again.' }
    $readiness = Get-Content -LiteralPath $runtimePath -Raw | ConvertFrom-Json
    if ($runtime.ExitCode -ne 0 -or $readiness.state -ne 'ready') {
        throw (($readiness.checks | Where-Object { -not $_.ok } | ForEach-Object { $_.detail }) -join ' ')
    }
    $existingImage = & $dockerExe image ls --no-trunc --quiet $manifest.image
    $loadImages = ($LASTEXITCODE -ne 0 -or -not $existingImage -or ($existingImage -join '').Trim() -ne $manifest.image_id)
    foreach ($appImage in @($manifest.bundled_app_images)) {
        if ($null -eq $appImage) { continue }
        if ($appImage.app -ne 'seerr' -or $appImage.image -notmatch '^stackarr-seerr@sha256:[a-f0-9]{64}$' -or $appImage.image_id -notmatch '^sha256:[a-f0-9]{64}$') { throw 'A packaged app image record is invalid.' }
        # Windows PowerShell treats stderr from a missing native image as an
        # error record. Absence here means load the verified package, not abort.
        $savedErrorPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = 'Continue'
            $present = & $dockerExe image inspect $appImage.image --format '{{.Id}}' 2>$null
            $inspectExit = $LASTEXITCODE
        } finally { $ErrorActionPreference = $savedErrorPreference }
        if ($inspectExit -ne 0 -or -not $present -or $present.Trim() -ne $appImage.image_id) { $loadImages = $true }
    }
    if ($loadImages) {
        Write-Host 'Preparing the downloaded Stackarr app...'
        & $dockerExe load --input (Join-Path $PSScriptRoot 'stackarr-image.tar') | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'The downloaded Stackarr app could not be loaded into Docker.' }
    }
    $loadedImage = & $dockerExe image inspect $manifest.image --format '{{.Id}}'
    if ($LASTEXITCODE -ne 0 -or $loadedImage.Trim() -ne $manifest.image_id) { throw 'The Stackarr image did not match this package.' }
    foreach ($appImage in @($manifest.bundled_app_images)) {
        if ($null -eq $appImage) { continue }
        $loadedApp = & $dockerExe image inspect $appImage.image --format '{{.Id}}'
        if ($LASTEXITCODE -ne 0 -or $loadedApp.Trim() -ne $appImage.image_id) { throw 'The Seerr security image did not match this package.' }
    }
    $controllerRoot = Join-Path $stateRoot 'controller'
    $enroll = Start-Process -FilePath $workerExe -ArgumentList @('--controller-enroll', ('"' + $controllerRoot + '"')) -PassThru -WindowStyle Hidden
    if (-not $enroll.WaitForExit(60000)) { $enroll.Kill(); throw 'Private setup connection timed out.' }
    if ($enroll.ExitCode -ne 0) { throw 'The private setup connection needs repair. Existing app data is preserved.' }
    $env:STACKARR_PORT = [string]$Port
    $mediaRoots = @()
    if ($installation.media_root) { $mediaRoots = @(@{path=$installation.media_root;host_path=$installation.media_root;label='My media folder'}) }
    $env:STACKARR_CONTROLLER_ROOTS = ConvertTo-Json -Compress -InputObject $mediaRoots
    $probe = New-Object System.Net.Sockets.TcpClient
    $listening = $false
    try {
        $pending = $probe.BeginConnect('127.0.0.1', $ControllerPort, $null, $null)
        if ($pending.AsyncWaitHandle.WaitOne(300)) { $probe.EndConnect($pending); $listening = $true }
    } catch { $listening = $false } finally { $probe.Dispose() }
    # A listener is only a reason to avoid duplicate startup. The private signed TLS probe below proves identity.
    if (-not $listening) {
        $worker = Start-Process -FilePath $workerExe -ArgumentList @('--controller-serve', ('"' + $controllerRoot + '"'), '--controller-port', [string]$ControllerPort) -PassThru -WindowStyle Hidden -WorkingDirectory $stateRoot
        [string]$worker.Id | Set-Content -LiteralPath (Join-Path $stateRoot 'controller.pid') -Encoding ascii
    }
    $composePath = Join-Path $stateRoot 'compose.json'
    $compose = @{services=@{stackarr=@{
        image=$manifest.image;init=$true;read_only=$true;cap_drop=@('ALL');security_opt=@('no-new-privileges:true');
        restart='unless-stopped';ports=@('127.0.0.1:' + $Port + ':8787');
        environment=@{STACKARR_ORIGIN=$origin;STACKARR_CONTROLLER_SHARED='/run/stackarr-controller';STACKARR_CONTROLLER_PORT=[string]$ControllerPort};
        volumes=@('dashboard-state:/var/lib/stackarr', @{type='bind';source=(Join-Path $controllerRoot 'shared');target='/run/stackarr-controller';read_only=$true});
        tmpfs=@('/tmp:rw,noexec,nosuid,size=32m')
    }};volumes=@{'dashboard-state'=@{}}}
    if ($installation.project -like 'stackarr-controller*') { $compose.services.stackarr.container_name = $installation.project }
    $compose | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $composePath -Encoding utf8
    $base = @('compose','--project-name',$installation.project,'-f',$composePath)
    Write-Host 'Starting Stackarr...'
    & $dockerExe @base up -d --wait --wait-timeout 120
    if ($LASTEXITCODE -ne 0) { throw 'Stackarr could not start. Check Docker and the selected port, then reopen this preview.' }
    $shared = '/run/stackarr-controller'
    & $dockerExe @base exec -T stackarr stackarr controller-probe $shared | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'The private installation connection is unavailable. Reopen this preview; no app installation was requested.' }
    $setupAddress = & $dockerExe @base exec -T stackarr stackarr setup-link
    if ($LASTEXITCODE -ne 0) { throw 'Stackarr could not open its private setup page. Reopen this preview.' }
    $address = [Uri]$setupAddress.Trim()
    if ($address.GetLeftPart([UriPartial]::Authority) -ne $origin) { throw 'The setup address did not match this preview.' }
    Write-PreviewResult $address.AbsoluteUri
    if (-not $NoBrowser) { Start-Process -FilePath $address.AbsoluteUri }
    Write-Host ('Stackarr is ready at ' + $origin + '. Choose your apps in the browser. A media folder is only needed for media apps.')
} catch {
    Write-Host $_.Exception.Message
    exit 1
}
