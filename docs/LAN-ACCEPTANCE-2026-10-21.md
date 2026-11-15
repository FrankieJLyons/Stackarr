# Secure LAN candidate and reversible cutover — 21 October 2026

Status: built for engineering acceptance, with physical LAN and signed-out boot
checks pending at the owner's request. No production cutover has been performed.
This is not yet a novice-ready network installer or a certified always-on Windows
server.

## Candidate and scope

The private candidate is `Stackarr-LAN-20261021-r4`, built from the current working
tree with a frozen Windows launcher and Docker dashboard. Its ZIP SHA-256 is:

```text
edc6c357b830f6f6a13ab9c5cb84821f69a724ff049b3dadeec13ce8308aa17a
```

The package and all host-specific evidence are under ignored
`test-results/lan-20261021/`. The package is an unsigned private preview and has
not been published. Caddy 2.11.7 was obtained separately from its official release;
the archive was checked against the release SHA-256 and published SHA-512 before
preparing a separate gateway bundle. Its license and provenance are retained there.

The candidate adds an exact HTTPS origin, owner authentication, Secure/HttpOnly/
SameSite cookies, same-origin CSRF checks, explicit remote browser links, and a
private-interface gateway restricted to reviewed clients. The existing loopback
dashboard remains available for recovery. Remote users cannot approve initial
account setup or open native file/folder dialogs. App API connections and media
ownership are preserved. The proposed first gateway exposes only the dashboard;
additional apps need separate authentication and playback acceptance.

LAN activation uses the existing maintenance mechanism, with checked settings
copies and an encrypted checkpoint. Rollback removes the allowed LAN origin and
restores the previous browser routes. A preceding package upgrade has its own
rollback checkpoint.

Startup now has bounded dependency waiting and uses the verified saved release's
start/recovery mechanism. Docker availability is checked without starting Docker
Desktop. Ownership/storage failures stop with a saved diagnostic. The gateway is
a foreground child for a future selected supervisor. No Windows task, service or
automatic sign-in mechanism has been registered.

## Automated and isolated evidence

| Check | Result and evidence |
| --- | --- |
| Full Python regression suite | 1,063 passed, 3 skipped; `test-results/lan-full-tests.log` |
| Final targeted Python checks, including the added incompatible-update guard | 119 passed; `test-results/lan-fixed-dependency-tests.log` |
| JavaScript suite including remote links | 88 passed; `test-results/lan-node-final.log` |
| Browser smoke | Passed setup, wizard, session, failure state, filters, settings, mobile and logout/login; `test-results/lan-browser-final.log` |
| Frozen r4 launcher self-test | Passed all 29 checks; `test-results/lan-20261021/frozen-selftest-r4.json` |
| Exact r4 package and older-preview rehearsal | All 10 checks passed; `test-results/lan-20261021/acceptance-r4-verified/report.json` |
| Packaged remote-link scripts | All 7 final scripts match the verified source; `test-results/lan-20261021/r4-packaged-assets.json` |
| Ruff and whitespace checks | Passed |
| Locked dependency audit | No known vulnerabilities found after updating certifi to 2026.10.19; `test-results/lan-dependency-audit-final.log` |
| Portable source scan | Reviewed matches were private-range constants and synthetic networking examples, not host addresses; `test-results/lan-source-audit.json` |

The packaged loopback HTTPS exercise uses new dashboard/controller state, new
ports and a synthetic owner account. It performs real maintenance operations,
validates TLS against the generated CA without bypassing verification, rejects an
untrusted CA, requires login, checks secure cookies and CSRF, rejects an unlisted
client and spoofed Host, and verifies persistence across gateway/dashboard
restarts. The actual LAN rollback revokes remote access while preserving local
sign-in and settings. These are process/container checks, not a Windows reboot or
normal-browser trust-store test.

The final rehearsal starts with the same older preview release as the working
installation, `Stackarr-Alpha-0.1-Named-r2`, in new synthetic state. It adopts that
test installation, upgrades to r4, invokes the frozen LAN review/apply commands,
performs the HTTPS/restart checks, rolls back LAN, then separately restores the
older package. Owner sign-in and saved values survive. It does not clone the
personal installation's databases or certify all its app connections.

After testing, all 22 containers present before this work retained their IDs,
images, start times, restart counts, mounts and port bindings. The working
installation's source-file fingerprints were unchanged and no maintenance
adoption was performed there. Only this task's new test fixtures were stopped;
their settings, packages and encrypted checkpoints were retained. Test addresses
in the reports describe the test run and are no longer running entry points.

The first older-package rehearsal found a Windows PowerShell quoting defect in
the original preview's launcher. That launcher is unchanged; PowerShell 7 was
used for the isolated older-version fixture. The candidate launcher already
contains the compatible label-reading fix. Schema expansion adds integration
fields; preservation checks require every pre-existing value to remain unchanged.

## Prepared cutover

`test-results/lan-20261021/cutover-final/` contains the source-file fingerprints,
candidate manifest fingerprint, inactive validated gateway, exact proposed
network/startup settings, and ordered cutover and reversal steps. Preparing it
did not adopt or write to the existing installation. The original preview will
need reviewed maintenance adoption at cutover time.
The client-trust folder contains only the public CA certificate and its recorded
fingerprint. The gateway's private CA state must remain on the server; no system
or browser trust store was modified.

Keep the local entry point and old releases. After all acceptance gates pass,
create and verify an encrypted whole-host recovery file and keep its key
separately. Upgrade Stackarr through its reviewed update path, verify local app
connections and the selected Plex server, then review/apply LAN as a separate
operation. Record exact DNS, firewall, trust and supervisor changes before
activation. Reverse only newly created entries with matching receipts.

## Pending physical and operator checks

- A separate client using normal browser certificate and hostname validation,
  successful owner sign-in and denied access from an unlisted client.
- Explicit app routes, required upstream authentication, correct app links and
  Plex playback from that client.
- A disposable Windows host cold boot with Windows remaining signed out,
  authenticated app readiness and playback, then supported failure recovery.
- The actual current installation's app identities, selected Plex server and
  verified whole-host recovery backup, followed by owner cutover approval.

Docker Desktop's per-user Linux engine has not been proved available before
Windows sign-in. If its supported startup mechanism fails that test, choose and
test another supported runtime; a logon task or automatic sign-in does not close
the gate. The working host must not be rebooted to substitute for the missing lab.

See [networking and gateway operation](NETWORKING.md) and the
[Windows lab protocol](WINDOWS-RUNTIME-LAB.md) for reproducible procedures.
