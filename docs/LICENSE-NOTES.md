# Licensing notes

Guided LAN builds optionally include Caddy 2.11.7 for Windows amd64 under the
Apache License 2.0. Its original LICENSE is included beside the executable in the
frozen runtime. The pinned release and verification hashes are recorded in
`stackarr/caddy.lock.json`. [Caddy source](https://github.com/caddyserver/caddy).

Stackarr's chosen project license is Apache-2.0. The root LICENSE contains the complete [official Apache-2.0 text](https://www.apache.org/licenses/LICENSE-2.0.txt), including its patent, contribution and trademark provisions. Third-party dependencies and assets retain their own terms; the project license does not resolve their redistribution requirements.

Do not copy GPL-3.0 code from Buildarr, Homepage, or other GPL projects into Stackarr without accepting the corresponding copyleft obligations. Prefer documented APIs, generated configuration, subprocess boundaries, or separately distributed optional integrations. MIT, Apache-2.0, GPL, Unlicense, and custom/proprietary terms in this ecosystem are different licenses; the license of awesome-arr itself applies to the list, not automatically to the projects it links.

The Docker preview includes a separate Seerr 3.5.0 image with Stackarr's Manage Users backport and Plex setup fixes. Seerr is MIT licensed, copyright (c) 2020 sct; its full notice is retained at `/usr/share/stackarr-seerr/LICENSE-Seerr` inside that image and in `platform/seerr/LICENSE-Seerr` in the source package. The image also contains the patch source, exact upstream hash lock, build recipe and applied-file receipt at `/usr/share/stackarr-seerr/`. Its immutable upstream base and unchanged dependencies retain their own notices. This is a Stackarr-patched build, not an official Seerr release. Other apps are referenced by pinned upstream image names and downloaded separately. Product names and logos belong to their respective owners. The included dashboard icons are from the dashboard-icons project and retain its license notice in `stackarr/static/icons/LICENSE.txt`. Review each image, icon, dependency, and logo license before creating a public release.
