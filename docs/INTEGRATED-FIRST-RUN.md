# Integrated first run — 19 October 2026

The current manual-walkthrough package is
**dist/Stackarr-Docker-First-Run-Preview-20261019-r5.zip**, SHA-256
`c7c41de61f567ac7c7971484ca4adf4eeb34ee9f2b41dad043c8958b3b0543bc`.
The original r1 acceptance record below remains historical evidence.

The manual walkthrough reached password creation and saved a six-app draft, then
found that both Windows common folder-dialog implementations stalled without a
visible picker. Removing PowerShell's Hidden flag did not resolve it. The host
controller now opens a separate bundled GUI process with a local-drive folder
list, navigation, explicit folder creation and selection. It does not invoke
Windows shell folder enumeration or enumerate network drives. Only the chosen
folder is granted; the host rechecks its existing dedicated-folder/link rules.
The bounded private result file handles cancellation and invalid output without
changing a previous selection. This also keeps GUI work on its own main thread.

The replacement passes **34 focused tests** and **23 frozen runtime checks**.
Both its source GUI and its r5 packaged GUI visibly open on this host. The r5
package also resumes the original healthy dashboard and authenticated browser
session. End-to-end app installation and the user's folder selection are still
being exercised in the manual walkthrough;
these checks do not certify clean-Windows, reboot or LAN behavior. The existing
account, six-app draft, dashboard and enrollment are retained during this repair.

The main Windows Docker package now includes readiness and reviewed Docker setup.
Open **Start Stackarr.cmd** from the complete extracted folder. No separate
readiness executable, Python environment or source checkout is needed.

Private artifact: **dist/Stackarr-Docker-First-Run-Preview-20261019-r1.zip**

```text
bf8067bd8c1295aae1e63ac9737c50ce9337d1ce1de46ce39dae6b5993255b01
```

## Recipient experience

1. Choose **Install apps on this computer** or **Connect apps I already run**.
2. Installation checks Windows, processor, memory, virtualization, free space and
   the existing local Docker/Compose engine. Missing Docker offers **Install
   Docker Desktop** with a review before download or installation. Checksum and
   Windows publisher checks precede the vendor installer. Complete Docker's
   prompts and first start, then choose **Check again**. Restart Windows yourself
   if its installer requests it, then reopen **Start Stackarr.cmd**.
3. When ready, choose **Continue to Stackarr**. Readiness is checked again before
   startup. The same tab opens password creation, app choices, folders and the
   installation review. App installation still requires its own approval.
4. Reopening finds the saved Docker installation and its active managed release.
   Retained removal or failed startup opens the existing local reinstall/repair
   review. Complete that review and choose **Continue to Stackarr** again.

Existing-app mode skips Docker requirements and opens the local Stackarr window
with its matching browser-code approval. It uses the local launcher's existing
data directory, separate from Docker preview state. It does not verify app
addresses or credentials until connection setup. The native window must stay open.

Default Docker state remains **%LOCALAPPDATA%/Stackarr/DockerPreview**; existing-app
state remains **%LOCALAPPDATA%/Stackarr/data**. The prerequisite journal stays in
**%LOCALAPPDATA%/Stackarr/first-run/docker**. Distinct directories are required.
The internal `--data-directory`, `--connect-directory`, `--prerequisite-directory`
and port flags support isolated test installations without changing those defaults.

## Implementation and retained safeguards

`StackarrPreview.exe --package-first-run` runs the bundled readiness assets and
private loopback service. Fixed authenticated routes start/poll one package handoff;
no browser-provided commands or executable paths are accepted. Host, Origin,
launch-key and bounded JSON checks apply before every operation. A new readiness
inspection is required at continuation; a stale ready page cannot bypass a stopped
engine. Active setup prevents simultaneous prerequisite work or checker closure.

The launcher verifies all eight package payload hashes before starting its fixed
PowerShell bootstrap or native child. A private temporary result file carries only
the local destination or a repair/reinstall review outcome. Browser setup capabilities
stay out of console logs. The handoff accepts loopback HTTP destinations only.
Failure is redacted and retryable. A root-specific lock prevents concurrent startup.

The existing bootstrap retains image validation, private enrollment, available-port
selection, saved addresses, managed active-release startup and interrupted maintenance
recovery. `-NoBrowser` remains available for developer automation. Ordinary packaged
startup delegates to readiness; **Recover Stackarr.cmd** keeps its recovery wizard.
The ZIP still has nine entries, including the manifest, and bundles the verified
Seerr security image. No settings, media, credentials or lab evidence are packaged.

## Acceptance

- **687 Python tests pass, 3 skip**, including 17 new handoff contracts: fresh
  readiness, duplicate continuation, unsafe destinations, saved-state retry,
  repair/reinstall review, fixed commands, tamper rejection and HTTP protections.
- **9 browser scenarios** pass with real local services and explicitly synthetic
  prerequisite/installer/process fixtures. They cover review/cancel, verification
  order, restart/reopen guidance, interrupted installation, integrated continuation,
  existing-app mode, stale readiness and retry after retained-runtime review/failure.
- All eight payload hashes and nine ZIP entries pass. The main executable passes
  **23 frozen checks outside the checkout**, including bundled readiness assets.
- The extracted package performs actual Windows/Docker checks, creates no app state
  before continuation, then opens the Docker dashboard in the same browser tab.
  The browser creates a new owner and reviews/installs a separate Seerr. Its patched
  persistent storage passes, setup opens, and the misleading mount warning is absent.
  Desktop and narrow readiness layouts pass.
- A second frozen launch reopens that saved Docker installation with the same
  account, browser session, dashboard/app IDs, controller settings, Seerr settings
  and volumes. Original lab media bytes remain unchanged. No prerequisite installer
  runs and no local existing-app data is created during that Docker journey.

The first package attempt reached successful setup/installation, then exposed a
URL predicate error in the acceptance harness. Only that harness was corrected;
the unchanged package passed a complete fresh second run. Both labs retain their
state and volumes after their test containers/networks are removed.

Private evidence: **test-results/docker-integrated-readiness-20261019-r1/**,
including `suite.xml`, `source-browser/browser-report.json`, `frozen-smoke.json`,
`package-verification.json`, `packaged-browser.json`, `acceptance.json` and fresh
`main-authenticated-monitoring.json`. Reusable drivers are
`tools/integrated_readiness_browser_check.py` and
`tools/docker_integrated_readiness_check.py`.

## Remaining release gates

This integrates the existing prerequisite workflow; it does not certify an actual
Docker installation on empty Windows. Installer calls, restart and missing-Docker
states are simulated in this slice. Earlier vendor payload verification is recorded
in [FIRST-RUN-DOCKER-SETUP.md](FIRST-RUN-DOCKER-SETUP.md). The working Docker
installation is never replaced to test an installer.

Clean-Windows installation, human native-dialog/existing-app walkthroughs,
signed-out reboot startup, LAN/second-device behavior, signing and durable public
distribution remain open. Automatic WSL/Windows-feature changes remain outside
this flow. Docker's first start and terms acceptance stay in its own application.
The existing main Stackarr installation is not upgraded by these tests.
