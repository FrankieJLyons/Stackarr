# First-run readiness

Readiness and reviewed Docker setup are now included in the main Windows Docker
package. Open **Start Stackarr.cmd**, then **Continue to Stackarr** when ready.
The same browser tab opens app setup; existing installations keep their settings
and maintenance controls. See [integrated first run](INTEGRATED-FIRST-RUN.md).

The independent executable and build recipe below remain available for focused
prerequisite testing. Their original standalone acceptance does not certify a
clean Windows install or reboot.

## Recipient experience

Open **StackarrReadiness.exe**. A local browser page checks the installation
computer and shows one next step for each unmet requirement. When Docker is
missing, choose **Install Docker Desktop**, review the version/download and
changes, then choose **Download & install**. Docker's own installer opens after
checksum and Windows publisher verification. It installs for the current Windows
account using the documented `install --user` route. Complete the vendor's
Windows permission/terms prompts, open Docker Desktop from Start and choose
**Check again**. Reopen this checker after an installer-requested restart.
The official guide remains available as an alternative.

No download or installation occurs during the initial checks or review. The
checker does not accept Docker's terms, enable automatic sign-in, change Docker
settings or invoke a Windows reboot. Enabling missing WSL/Windows components may
require separate Windows permission and setup through the official guide.

The reviewed payload is Docker Desktop **4.95.0**, build **242831**, 636,811,696
bytes, pinned to the checksum published by Docker. Both the checksum and a Valid
Windows Authenticode signature with organization **Docker Inc** are required.
Downloads stay on Docker's HTTPS host and have size/time limits. The verified
payload is held against replacement while the interactive installer is launched.
Existing Docker executables or installed-app records block this fresh-install
operation; the existing app/container updater is not involved.

Setup progress and cancellation are provided before the native installer opens.
The per-user prerequisite journal and operation lock use **Stackarr/first-run/docker**
under local application data, separate from dashboard/controller state. An
interrupted operation never automatically launches another installer. It requires
a fresh review and confirmation that the earlier installer has finished or been
closed. Active operations prevent this checker from closing or starting a second
installation. An installer exit requiring restart is shown explicitly; it does
not trigger a reboot from Stackarr.

**Connect apps I already run** skips all host/Docker checks and explains the
existing-app connection path through the local Stackarr launcher. It does not
claim those app addresses or logins have been verified.

**Close checks** stops this checker only once prerequisite work has finished or
been cancelled. An unused checker expires after twenty
minutes; reopen the executable if an old tab no longer responds. Dashboard
accounts, controller enrollments, media folders and media-app installation state
remain separate from this prerequisite operation.

## Checks and boundaries

- Windows desktop build 22631 or later and x64 architecture; older builds,
  Windows Server, ARM and 32-bit hosts do not pass this installation preview.
  This is a minimum-build check, not certification of a Windows edition's
  current servicing status. The page directs users to keep Windows supported.
- At least 8 GB of physical memory. Selected apps may require more.
- Virtualization reported by Windows, or demonstrated by a running verified
  local Linux Docker engine. Unknown firmware capability is shown as unknown.
- Read-only free space on the existing per-user setup drive. Below 10 GiB shows
  a planning reminder; it is not a Docker/image/media-space estimate. Docker's
  storage location, media space and folder write access need later checks.
- Existing read-only Docker checks: executable discovery including both Windows
  install locations, verified local context, Compose, Linux x64 engine and
  network-capacity estimate. Remote/overridden endpoints are refused. The checker
  never starts Docker, pulls an image or changes a container/network.

The requirements baseline was reviewed on 19 October 2026 against
[Docker's Windows installation guide](https://docs.docker.com/desktop/setup/install/windows-install/).
WSL 2 is one supported Docker backend, so the checker does not demand WSL from
an already working Hyper-V/VMM engine. Automatic WSL/Windows feature changes and
clean-machine/reboot certification remain future work. Docker download/installer
progress and interrupted-operation review are now included. See
[Microsoft's WSL guide](https://learn.microsoft.com/windows/wsl/install).
Reaching **Ready for the next setup step** is prerequisite readiness only.
Storage access, app installation/connections, media playback, LAN access and
startup while signed out still need their own acceptance tests.

## Local access

The server reserves an available loopback-only port. A per-process random
capability arrives in the browser fragment, is removed from its address and is
kept in that tab's session storage. It never appears in HTTP URLs, source HTML,
server logs or referrers. Checks and shutdown require the matching capability,
exact Host and Origin, a bounded JSON body and a fixed action. There is no
arbitrary command/path endpoint. Concurrent checks are refused; connection and
subprocess timeouts and a client limit bound local work. Pages use local assets,
no third-party requests, a restrictive content policy and text-only rendering
of results. Raw inventory, endpoint addresses and command failures are not sent
to the browser.

## Maintainer commands

Source preview (existing Python environment):

```text
python -m stackarr.first_run_server
python -m stackarr.first_run_server --report test-results/readiness.json
python -m stackarr.first_run_server --self-test-report test-results/readiness-smoke.json
```

Report files are exclusively created and never overwrite an earlier observation.
The first command needs only Python's standard library, including Tk for the
default-browser fallback. The report commands do not open a browser. Exit codes:
0 ready/passed; 1 prerequisites need attention/smoke failed; 2 report/start failure.

Use a separate build environment with `pyinstaller==6.22.3`:

```text
python -m PyInstaller --distpath dist/first-run-readiness --workpath build/first-run-readiness platform/windows/StackarrReadiness.spec
```

This produces **dist/first-run-readiness/StackarrReadiness.exe**, without
overwriting **dist/StackarrPreview.exe**. It bundles the readiness assets, local
runtime-check modules, Python/Tk and the project license. It does not bundle the
dashboard, Seerr image, personal state or application installation payloads.
It is an unsigned private preview, not the signed product installer.

For an isolated release ZIP with hashes, use the separate packager. It first
copies only the explicit readiness source allowlist to a private build snapshot,
so a concurrent Seerr build cannot change its application inputs. It refuses to
reuse release/build directories. Its manifest records the exact source-file and
payload hashes; it does not claim bit-for-bit executable reproducibility.

```text
python -m tools.package_first_run --build-python .runtime/first-run-build/Scripts/python.exe --output dist/Stackarr-Readiness-Preview-20261019-r1
```

Focused verification:

```text
python -m pytest -q tests/test_first_run.py tests/test_first_run_server.py
python -m tools.first_run_browser_check --output test-results/first-run-browser-new
```

The browser check uses synthetic missing/ready/failure states and tests retry,
existing-app choices, reload, private launch, keyboard focus, narrow layouts,
shutdown and local-only assets. Frozen smoke checks use synthetic facts and
local HTTP without Docker. Test the actual frozen executable from outside the
checkout with Docker discovery unavailable and inspect its report separately.
Neither synthetic discovery nor a normal current-host report certifies a fresh
Windows installation, native dialogs, prerequisite installation or a reboot.

The separate `tools.first_run_docker_browser_check` adds reviewed install,
cancellation, restart guidance and interrupted-installer acknowledgement using
synthetic bytes and installer calls. Never execute a Docker installer on the
working Docker computer to substitute for a disposable clean-Windows test.
