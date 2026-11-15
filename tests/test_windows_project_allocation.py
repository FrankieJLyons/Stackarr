"""Exercise the actual Windows PowerShell native-argument boundary."""
import os
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(os.name != 'nt', reason='Windows PowerShell native argument handling')
def test_project_names_include_retained_volumes_and_networks(tmp_path):
    script = Path('platform/docker/Start-StackarrPreview.ps1').read_text()
    function = script.split('function Find-StackarrProject {', 1)[1].split('\nfunction ', 1)[0]
    docker = tmp_path / 'docker-fixture.cmd'
    docker.write_text('@echo off\n'
        'if not "%~3"=="--format" if not "%~2"=="-a" exit /b 3\n'
        'if not "%~4"=="{{.Labels}}" exit /b 4\n'
        'if "%~1"=="ps" echo other=value,com.docker.compose.project=stackarr-controller\n'
        'if "%~1"=="volume" echo com.docker.compose.project=stackarr-controller-2,other=value\n'
        'if "%~1"=="network" echo com.docker.compose.project=stackarr-controller-3\n'
        'exit /b 0\n')
    target = tmp_path / 'check.ps1'
    target.write_text("$ErrorActionPreference='Stop'\n$dockerExe=$args[0]\nfunction Find-StackarrProject {"
                      + function + '\nFind-StackarrProject\n')
    # Include cold Windows PowerShell startup and .cmd inspection on shared CI
    # runners in this bounded budget. The fixture never contacts real Docker.
    result = subprocess.run([str(Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'),
        '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(target), str(docker)],
        stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=90,
        creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'stackarr-controller-4'
