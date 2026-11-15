# Seerr requests companion

Seerr is optional. Select it in setup to generate its Compose service, or enable
it in Apps with the address of an existing installation. Finish Seerr's own
setup first: choose your media server, connect the appropriate Sonarr/Radarr
instances and set household permissions. For an app installed by Stackarr, return
to **Finish connecting** to save its connection privately. Existing installations
can use their API key in Stackarr Apps. Follow the
[Plex sign-in guide](SEERR-SETUP.md) for new installs and pop-up help.

Stackarr reads connection status and request counts. Activity shows the counts and
links back to Seerr. It does not approve requests, copy user identities, alter
permissions or duplicate request history. Disabled Seerr makes no network calls.
Schema 3 upgrades older configurations with Seerr disabled.

The experimental Compose service uses the official image, a separate named config
volume, loopback port 5055, an init process and dropped capabilities. It does not
mount media. Like other app plans, installation remains subject to the runtime lab
and image-digest release gates.

Interface research, 2026-09-26:

- [Official Docker guide](https://docs.seerr.dev/getting-started/docker/).
- [API contract at reviewed source revision](https://github.com/seerr-team/seerr/blob/4fd0da04e355f8b376f357246258ea7bdabdd3e5/seerr-api.yml): GET status with update checking disabled and authenticated GET request/count.
- [Project and license](https://github.com/seerr-team/seerr): no upstream code, assets or branding were copied. Stackarr uses its own placeholder icon.

Fresh Seerr container installation, verified named-volume storage and account
guidance are covered by real browser-to-Docker acceptance. The new-install check
clears the misleading image marker only after verifying actual owned storage and
durable write/read access; settings and databases stay in place. See
[SEERR-SETUP.md](SEERR-SETUP.md) for exact tests and human account-step limits.
Request permissions and recipient account walkthroughs remain release gates.
