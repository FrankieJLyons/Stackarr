# Windows runtime feasibility lab

Status on 16 October 2026: the existing Windows computer has a running Docker Desktop Linux x64 engine and Compose 5.5.1. Read-only inventory reports virtualization available and AutoAdminLogon disabled. The owner requested Docker-only testing because no second Windows computer is available. No disposable Windows guest or signed-out observer is assigned, and no Windows topology is certified. Docker Plex evidence is recorded in PROGRESS.md; cold boot, second-device playback and clean-machine checks remain deferred. Do not use the working media host as a substitute for those checks.

## Decision to make

Select the simplest Windows deployment that passes startup before sign-in, LAN playback, storage/credential access, quiet recovery, and preservation on uninstall. Compose remains the portable format. A desktop login requirement is a failed always-on criterion, not a reason to turn on Windows autologon.

| Candidate | Why test it | Unresolved evidence |
| --- | --- | --- |
| Docker Desktop with Compose | Shared portable app definitions | Engine availability before sign-in, host folder behavior, resource cost, Plex device capabilities |
| Native Windows | Closest to the existing server's launch model | Each app's supported install/start/update behavior, profiles/secrets, service versus task privileges |
| Hybrid native Plex plus Compose companions | Allows separate Plex hardware/runtime choice | Both startup mechanisms must pass; more support complexity than a single runtime |

Research supports a test order, not a winner. Test Compose first for portability. If a supported boot route cannot satisfy the criteria, record the failure and test native Windows. Evaluate hybrid only if it resolves a demonstrated Plex limitation without breaking the rest of the stack.

Official references:

- [Docker permission model](https://docs.docker.com/desktop/setup/install/windows-permission-requirements/): privileged helper service behavior is distinct from proof that the Linux app stack has started.
- [Docker settings](https://docs.docker.com/desktop/settings-and-maintenance/settings/): startup setting is documented in terms of sign-in.
- [Plex setup guide](https://support.plex.tv/articles/200264746-quick-start-step-by-step-guides/): account/library setup remains a user task. This is not certification of a Windows service wrapper.
- [Caddy automatic HTTPS](https://caddyserver.com/docs/automatic-https): client trust must be established and tested, not bypassed.

## Lab prerequisites

Use a spare Windows 11 x64 PC or disposable guest capable of the selected runtime, plus a second trusted LAN client. Nested virtualization availability must be checked for VM testing. A VM cannot establish physical GPU compatibility. Record Windows build, app versions, runtime version and installer/image checksums in private lab evidence.

Use five apps: Stackarr, Plex, qBittorrent, Sonarr, Caddy. Use an owned short video with no personal information and an isolated test directory. No real torrents, indexer credentials, production app keys, personal media paths, or real account passwords belong in a report. For Plex sign-in use the operator's explicitly chosen account, store its token only in the app, and redact recordings.

Take a guest snapshot where available; record a recovery method on physical equipment. Agree the test machine can be rebooted and have lab-owned software installed before starting. Never guess a target or reboot a machine just because it answers on the LAN.

## Toolkit

Run `platform/windows/Test-StackarrLabReadiness.ps1` on the chosen lab host. This is read-only inventory: it checks OS/resources and command availability and reads only the AutoAdminLogon flag. It does not read a saved password, enumerate applications/media, install anything, start Docker, change power settings, or reboot. A missing registry flag is reported as unknown and is not proof that every form of automatic sign-in is disabled.

The maintainer's evidence ledger uses Python; this is lab tooling, not the future recipient installer:

```text
python tools/windows_lab.py template compose-desktop test-results/windows-lab-compose.json
python tools/windows_lab.py evaluate test-results/windows-lab-compose.json
```

Create `test-results` first if absent. Each new record starts with all checks `not_run`. The template command refuses to overwrite an existing record. Use a separate record and restored baseline for each topology.

Set `environment` to `disposable-vm` or `spare-test-pc`; fill every version (use a descriptive native launch mechanism for `runtime` where no Docker engine exists). For each check record `pass`, `fail`, `blocked`, or `not_run`, plus relative paths to nonempty private evidence files alongside the ledger. Paths cannot escape that evidence directory. The evaluator reports completeness, not observation authenticity or product certification. Raw evidence stays under ignored `test-results/`; publish only an explicitly redacted summary.

## Execution protocol

1. **Clean install:** capture empty lab baseline; install only selected test apps from reviewed upstream sources. Record topology, launch identities, privileges, time, versions and hashes. If Stackarr lacks an install adapter, use a documented manual lab procedure and mark consumer-installer readiness untested.
2. **Account/storage:** test a small read/write sentinel through each relevant app under its actual startup account. Plex needs read access, Sonarr/qBittorrent need approved write access. Verify hashes and resolve host versus container paths. Record network shares as a separate capability; a local-folder pass does not prove NAS access.
3. **Credential restart:** save test credentials using the normal mechanism; restart the lab-owned processes and verify authenticated API requests. Do not log keys, cookies, session tokens, or full API bodies.
4. **Cold boot:** use the lab host's normal reboot UI; do not sign into the console or remote desktop afterward. From the observer record boot time, reachability and authenticated application identity for all five apps, every 30 seconds for up to five minutes. A listening port or login-page HTTP 200 alone is insufficient. Record a failed deadline as failure, even if later signing in fixes it.
5. **LAN playback:** while host remains signed out, play the owned sample for five minutes on the observer. Record direct play versus transcode, stalls, start latency, timestamps and matching Plex session. Test hardware transcoding separately on suitable physical hardware before advertising it.
6. **Import path:** use Sonarr's supported manual import with a correctly structured lawful sample in the approved completed-download location. Verify resulting library file and hash. This proves the mount/import path, not tracker search/download behavior; full client-to-Arr automation belongs to a later fixture test.
7. **HTTPS:** enroll the public test CA on the observer with explicit consent; verify hostname, validity and chain using normal browser validation. Check auth remains required and no public/router rule exists. Keep the CA private key out of artifacts.
8. **Quiet/resource test:** after finishing signed-out evidence, sign in and record focus behavior and idle/playback CPU/RAM over ten minutes. Record whether an app update or recovery opens an unwanted browser/window. Do not change the machine's power plan automatically.
9. **Recovery:** stop one test-owned process using the chosen lifecycle mechanism. Verify bounded restart and audit. If no supported recovery mechanism exists, mark blocked or failed rather than adding an ad hoc administrator watchdog. Confirm downloads and sentinels remain untouched.
10. **Uninstall:** use only the lab installation's documented uninstaller. Prove sentinel media and independently created foreign state survive, and list any residual owned files. Do not test recursive cleanup against a production directory.

After each phase, save timestamps, observed result, exact reproducible steps, and an evidence reference. Redact account names, IP addresses, hostnames and file paths in the shareable conclusion.

## Handoff

Show the human one comparison table with pass/fail/blocked/not-run for each check and topology, the observed boot/playback demo, limitations, and proposed runtime choice. Do not substitute mocked unit tests for these observations. The operator approves a topology only after reviewing complete evidence. A failed candidate is a useful result; an untested one is not.

Current result: no real-machine checks run. Next required resource is an explicitly selected disposable Windows environment and LAN observer. In parallel, bundled setup UI and prerequisite presentation can proceed without deciding the privileged host runtime.
