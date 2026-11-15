# First-run readiness checkpoint — 19 October 2026

The independent readiness preview is implemented and packaged. It opens before
Docker is installed, offers the official installation guide, checks again after
the user resolves a prerequisite and skips local requirements for existing-app
connections. The missing-Docker action is visible at the top of the page.

Private package: **dist/Stackarr-Readiness-Preview-20261019-r1.zip**.
Open **StackarrReadiness.exe** in its extracted folder. SHA-256:

```text
1ed065654c92b78e2499a6ace06d7d732a7c2bcadfedc6a5a6b7fbe0f348bbf2
```

## Recorded verification

- **57 tests passed** across the new prerequisite/server tests and existing
  Docker-runtime tests. They cover unknown facts, unsupported hosts, missing
  Docker, stopped engines, remote contexts, timeouts, redaction, exclusive report
  creation and the local HTTP authorization/input boundaries.
- **11 browser cases passed**, with inspected desktop/mobile screenshots:
  missing-Docker guidance, retry, existing apps, reload, narrow layout, keyboard
  focus/text zoom, unauthorized browser, blocked session storage, redacted failure
  and retry, shutdown and no external requests/script errors.
- **9 frozen smoke checks passed** after copying the executable to a separate
  workspace outside the source checkout. The executable served its own bundled
  page/assets, handled missing Docker and existing apps with synthetic facts,
  and rejected an unauthorized check without contacting Docker.
- With PATH empty and both Docker fallback locations redirected to an empty
  directory for child processes only, the frozen executable independently
  reported **Install Docker Desktop to continue**. Existing-app mode remained
  ready. Neither recipient Python nor source imports were available in this run.
- The frozen executable's actual current-host report passed **10 prerequisite
  checks**, marking low Docker network capacity as a review note. It performed
  read-only Windows/Docker inventory and reported installation not started.
- ZIP entries and payload/source hashes verified. The build snapshot contains
  only 14 allowlisted source inputs. Its application module inventory includes
  the readiness modules and read-only Docker/network checkers, with no Seerr or
  dashboard modules. A 17-file focused source scan reported **0 findings**.

Private evidence is under **test-results/first-run-readiness/**. Browser evidence
is **browser-r2/**; test results are **tests.xml**; source/payload verification is
**package-verification.json**. Frozen evidence is copied into **frozen-r1/**.
The source snapshot is retained under **build/first-run-readiness/**.

## Scope still open

This is a separate unsigned prerequisite-checking preview. It is not integrated
into the shared Stackarr launcher or Docker package. No Seerr code, shared
packager, shared progress/plan files or existing app state was edited by this
workstream. The only shared runtime modules it uses are copied into its own
build snapshot.

Simulated absent discovery is not a clean-PC test. Automatic/verified prerequisite
installation, Windows feature changes, resume through reboot, servicing-status
certification, native dialogs, actual app/media storage permissions, LAN playback
and startup while signed out remain acceptance/integration work. See
[implementation and build notes](FIRST-RUN-READINESS.md).
