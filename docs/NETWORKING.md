# Networking and HTTPS

## Local HTTPS setup and the control room

Open **Start Stackarr → Home network & recovery**, select the home connection,
and choose **Prepare secure access**. Caddy creates and retains a private local
certificate authority and renews its server certificates. Review activation,
start secure access, and use **Copy address** to save the address on another
device. The helper must stay running while its gateway is in use.

The default address uses the server's private IP. Under network details, an
optional local computer name (for example `frankies-pc`) can be used if every
client already resolves it to the selected server address. `.local` and
`.home.arpa` names are also accepted. This does not create DNS records.

Download only the public `.cer` file. Compare its fingerprint on the server and
trust it once on each device. The helper provides Windows, macOS, iOS, Android
and Firefox instructions. Browsers that use the same trust store share that trust;
some browsers and managed devices have separate requirements. Server certificates
from this same gateway CA reuse that trust. Other gateways have separate identities.
Keep the private gateway folder on the server and retain it between restarts.

A local-only name or private IP cannot receive ordinary public browser trust
automatically. Self-signing provides encryption after enrollment; it does not
remove the first trust step. No browser verification is disabled and no trust
stores, router, firewall or DNS settings are changed by this setup. The gateway
currently exposes Stackarr; app routes and real-device playback still need their
own checks. Physical device and signed-out reboot acceptance remain pending.

Configured stacks now open in the original blue control-room layout. Add apps
from its grouped sections. Card restart controls check the installation receipt
and runtime before offering a reviewed restart, or start if stopped. App additions
save a setup draft and require the existing install/connection review before use.

## LAN engineering candidate — 21 October 2026

The source now supports a separately prepared Caddy gateway and a second, exact
HTTPS browser origin while keeping the existing loopback origin. LAN configuration
changes use the packaged Stackarr maintenance worker, checked database copies and
an encrypted rollback checkpoint. They do not change app API addresses, media,
ownership receipts or Windows/network settings. This is not in the published R8
ZIP and is not yet a novice network-setup wizard.

The [dated acceptance record](LAN-ACCEPTANCE-2026-10-21.md) identifies the private
candidate, completed isolated checks, cutover dossier and remaining physical gates.

`STACKARR_LAN_ORIGIN` is one HTTPS origin with no path, query or credentials.
`STACKARR_LAN_LINKS` is a JSON map of app IDs to HTTPS origins. Each app needs a
different hostname, including from Stackarr: cookies are scoped to hosts, not
ports. These environment settings require a dashboard restart. They are not
configuration-schema fields, do not migrate the saved app configuration and are
preserved by compatible updates. Updates to a package without LAN support are
rejected while LAN access is enabled; roll back LAN access first.

Remote requests still need the owner's Stackarr login. Host and Origin must match
the exact selected origin, writes require CSRF protection and remote login cookies
are Secure, HttpOnly and SameSite=Strict. Forwarded headers cannot select the
application origin. Initial account approval and native folder/backup/update
dialogs remain local. This is owner administration, not a new household-user role.

Remote status, setup and Plex links use the explicit LAN routes. Missing routes
show a setup message instead of directing another computer to its own localhost.
API and peer addresses and the saved local browser addresses are preserved.
An HTTPS link is not evidence that its upstream app has adequate authentication.
The first prepared cutover exposes only Stackarr; app routes, especially Plex,
must pass their own unauthenticated-access and browser/playback checks before use.

### Prepare without changing the server

`python -m stackarr.lan_gateway prepare REQUEST.json NEW-BUNDLE --caddy PATH`
validates and copies an explicitly selected Caddy binary into a new directory,
generates its configuration and records hashes. Example request (use the actual
reserved server address and intended client subnet, not these sample values):

```json
{
  "origin": "https://stackarr.home.arpa:29443",
  "bind": "172.20.50.10",
  "clients": ["172.20.50.0/24"],
  "dashboard_port": 28000,
  "apps": {},
  "state_root": "C:/Stackarr/State"
}
```

The gateway binds one private IPv4 address, admits only reviewed private client
subnets (/16 or narrower), proxies to loopback, rejects unknown hosts and disables
its admin API, automatic HTTP listeners, HTTP/3 and automatic CA trust installation.
Its CA and logs live under the bundle's private directory, separate from existing
Caddy state. Only `lab: true` permits a loopback listener/client allowlist.
Preserve the entire bundle, especially CA private state; never distribute its keys.
Use only Caddy binaries from a trusted, verified source. Hashing a selected binary
detects later changes; it does not authenticate its publisher.

For a compatible managed installation, the frozen executable supports:

```text
StackarrPreview.exe --lan-review BUNDLE --maintenance-report NEW-REVIEW.json
StackarrPreview.exe --lan-apply NEW-REVIEW.json --maintenance-report NEW-JOB.json
StackarrPreview.exe --lan-run BUNDLE
```

Review is read-only apart from saving the review file. Apply rechecks the exact
installation and bundle, creates the standard encrypted maintenance checkpoint,
and changes only Stackarr's allowed LAN origin/browser links. It does not launch
the gateway. The existing local dashboard remains the recovery entry point.
The local Python developer interface offers equivalent `review`, `apply`, `run`.

`--lan-run` waits for the existing Docker runtime with six bounded checks and
backoff, then uses the verified saved release's start/recovery path before running
the gateway. It never starts Docker Desktop, enables automatic Windows sign-in,
registers a task, or retries an ownership/storage rejection blindly. Its saved
status distinguishes missing Docker from rejected startup. An external, explicitly
configured supervisor must own the foreground gateway; the program does not kill
other Caddy processes by PID or name.

### Cutover and rollback

`python -m tools.lan_cutover` prepares a source fingerprint, exact candidate,
separate gateway, prerequisites and ordered rollback dossier without writing to
the current installation. First update an older Stackarr through its existing
reviewed package update. Apply LAN access as a separate operation. Keep its local
address, old release and encrypted checkpoints available throughout.

Rollback stops only the new gateway through its own supervisor, then rolls back
the LAN operation in local Stackarr Settings. This restores the prior allowed
origins and browser routes with checked settings. The preceding package update
has its own separate rollback. Later DNS, firewall, startup and trust changes must
have exact creation receipts and their own reversal; no broad firewall reset,
task deletion, certificate cleanup or router reconfiguration is supported.

### Remaining acceptance gates

The user has no spare Windows host yet and explicitly asked to leave physical
checks pending. Do not reboot or change the working host to close these gates.
Use [the Windows lab protocol](WINDOWS-RUNTIME-LAB.md) on a disposable host and a
separate client: trusted certificate/hostname validation in the normal browser,
owner sign-in, denied unlisted clients, correct app links, Plex playback, and a
cold boot with Windows remaining signed out. A process/container restart is not a
cold boot. Docker Desktop availability before sign-in is still unproven; a failed
runtime requires a supported alternative before an always-on claim.

No DNS entries, firewall rules, CA trust, router mappings or startup registrations
are installed by the candidate. The client must resolve each selected hostname,
trust only the public CA certificate after checking its fingerprint, and reach
only the chosen gateway port on the intended interface. Use a stable DHCP
reservation or reviewed static address. Gateway readiness does not certify app
playback, account revocation or Windows startup.

## Existing manual deployment

The Docker Compose deployment publishes Stackarr at `127.0.0.1:28000` by default; the container and native CLI still listen on port 8787 internally. Set `STACKARR_ORIGIN` to the exact browser origin, including scheme and port, and place a trusted reverse proxy in front when LAN access is needed. The origin is checked against the Host and Origin headers, and WebSocket support is not needed by the alpha server.

Do not open router ports automatically. Keep the service on the LAN or behind a VPN. If you use Caddy, nginx, Traefik, or a NAS proxy, forward the normal HTTP request and preserve the original Host, Origin, and redirect behavior. Do not rewrite every client to trusted localhost or remove application authentication.

Use a certificate issued by a public or private CA trusted by the clients. For a private CA, distribute the public root certificate through the platform's normal trust store. Browsers may require a separate mobile or Firefox trust step; never disable certificate validation. Renewal remains the reverse proxy's responsibility.

The default Compose port is loopback only. Change `STACKARR_BIND` only after reviewing firewall scope. Stackarr does not create Windows firewall rules, certificates, DNS records, or router mappings.
