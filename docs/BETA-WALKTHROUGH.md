# Fresh-user beta walkthrough

For the current unsigned installer candidate, use the
[0.1.1 testing handoff](BETA-0.1.1.md). This worksheet records the released 0.1.0 experience.

Use the public **0.1.0 Windows ZIP**, not a source checkout or a development build. This run checks the released experience. Fixes found during it belong in a later candidate; do not silently replace the 0.1.0 assets.

## Before starting

- Download the ZIP and its SHA-256 file from the [release](https://github.com/FrankieJLyons/Stackarr/releases/tag/v0.1.0) and compare the hash.
- Extract into a new permanent folder. Use fresh Stackarr state and an empty test media folder.
- Leave the regular media stack running. Do not import or migrate it during this run.
- Use a distinct test Plex server name. Install only apps selected in the reviewed test plan.
- Keep personal account/provider credentials in the apps. Record sanitized observations, not tokens, keys, setup URLs or raw logs.

An existing Windows/Docker host can test fresh **Stackarr state**. It cannot establish clean-Windows prerequisite behavior. Record which environment was actually used.

## Walkthrough record

Version: 0.1.0  
Environment: existing host with fresh Stackarr state / disposable clean Windows  
Windows and Docker versions:  
Selected apps:  
Active interaction time:  
Download/vendor setup/reboot time:  
Assistance needed:

| Step | Expected result | Result: pass / fail / not run | Sanitized observation |
| --- | --- | --- | --- |
| Launch | Start Stackarr.cmd opens readiness without Python or a terminal procedure. | | |
| Prerequisites | Readiness gives an actionable result and preserves progress after any vendor setup. | | |
| Account | Create a new local password; sign-in succeeds. | | |
| Choose apps | Choose a minimal set or Movies & TV; unselected companions do not block progress. | | |
| Review | Review test folders, available ports and selected apps before installation. | | |
| Install | Selected apps start; the normal media stack remains usable. | | |
| Plex/account setup | Complete personal sign-in; return to the saved checklist with the intended test server selected. | | |
| Libraries/connections | Prepare the test libraries and app connections through the checklist. | | |
| Sources, if needed | Test authorized movie and TV sources separately; distinguish no matching release from connection failure. | | |
| Movie | Request permitted test content; verify transfer, import, library visibility, status and actual playback. | | |
| TV | Repeat with a permitted episode/season; check requested quality and availability. | | |
| Existing-media path | If selected, play an owned sample without requiring a download source. | | |
| Reopen | Close/reopen the launcher; account, settings and checklist resume. | | |
| Backup, optional | Create an encrypted test configuration backup and retain its recovery key separately. | | |
| Second device, optional | Check HTTPS trust and intended-device playback without bypassing browser warnings. | | |
| Windows restart, separate | Only on an explicitly chosen test host; manually reopen Docker/Stackarr for 0.1.0 and verify retained state. | | |

Do not reboot a working household server merely to fill this checklist. Mark unavailable physical checks **not run**. For a novice test, record the point where help became necessary before giving coaching.

## When something fails

Record the checklist step, expected behavior, actual behavior, and a short sanitized error. Stop dependent steps if installation ownership or the selected media folder is uncertain. Preserve failed test state for diagnosis; do not reset Docker, prune shared resources, or repair the regular stack.

A green container or visible catalog item is not a playback pass. Keep independent outcomes for installation, authentication, connections, imports and playback.

## Completion

List passed checks, blockers, unrun checks and any changes to unrelated apps (expected: none). File reproducible defects through the [bug template](https://github.com/FrankieJLyons/Stackarr/issues/new?template=bug_report.md); report security concerns through [SECURITY.md](../SECURITY.md). Retest fixes on a new candidate and record its exact version.
