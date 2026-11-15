# Quality by year and title

Open **Apps → Quality by year and title**, then choose **TV rules** or **Movie
rules**. The starting choices are SD before 2000 and 1080p from 2000 onward.
Search for a specific title to give it 4K, SD or 1080p independently of its year.
Preview the settings, then save them for new requests.

TV uses a show's premiere year, not individual episode or season years. Movies
use their release year. Exceptions match TVDB IDs for shows and TMDB IDs for
movies; similarly named titles cannot accidentally share an exception. An
exception takes precedence even when the year is missing. Without an exception,
unknown years keep the existing library profile; new requests need an explicit
quality choice.

Rules apply to new requests made through **Stackarr Home**. The title dialog
shows the selected rule and allows an explicit override for that request.
Additional seasons of an already tracked show retain its existing profile.
Requests or imports made directly through Seerr, Sonarr, Radarr or an import list
are outside this policy. Rules do not transcode, shrink or delete files.

## Download format preferences

TV and movie rules each have **Download formats**, using the same preview/save
flow as year and title choices:

- **Block Dolby Vision downloads** rejects labelled DV/DoVi/Dolby Vision,
  including HDR10-compatible hybrids. It does not block Dolby Atmos audio.
- **10-bit video**: No preference, Prefer, or Avoid (block).
- **H.264/AVC, H.265/HEVC, AV1 and VP9** each have the same three choices.

Prefer adds a modest custom-format score; other formats remain eligible. Arr's
quality ordering still takes precedence over a positive format score. Avoid is a
hard rejection for a matching label, even if other preferences match. Every
block scores -10,000; each preference scores +100, with a minimum accepted score
of zero. All possible positive scores combined cannot override one block.
Automatic upgrades stay off. These choices neither replace nor transcode files
already in the library. Additional seasons of existing shows keep their existing
profile unless the separate library preview is applied.

Matching uses release names, including common abbreviations and underscore
separators. Missing or inaccurate labels can bypass the filters. The 10-bit rule
matches explicit 10-bit, Hi10P and Main10 labels; HDR alone does not establish an
exact bit depth. These are release-selection rules, not media-file inspection or
an antivirus guarantee. Existing policies default to no format preference.

Preferences create immutable, versioned custom formats and profiles. Changing a
choice creates another profile generation; old definitions and assignments stay
intact. Arr automatically adds neutral entries to other profiles when a custom
format is created; those zero-score entries do not change their behavior.
Requests verify both the selected profile and its filter definitions again.
Seerr can temporarily cache an older profile list. With rules enabled, Stackarr
uses its managed profiles verified directly in the same connected Arr instance,
so a newly saved preference is immediately selectable. A cache refresh does not
invalidate that choice; edits to the live profile, filters or connection still do.
Interrupted creation can be reviewed and retried without duplicating definitions.
Undo preserves later edits to the original profile's scored format definitions.

AV1 and 10-bit downloads may require conversion by Plex, even when the browser
itself can decode them. Conversion can reduce resolution or bit depth. Test a
sample on your usual player before choosing Prefer; selecting 4K describes the
downloaded file and does not guarantee 4K playback on every client.

Check **Plex Dashboard → Now Playing** during playback. In the video row,
**Direct Play** or **Direct Stream** keeps the original video; **Transcode**
means Plex is converting it. An audio-only transcode does not reduce video
quality. Media Info
describes the stored file and does not prove what is playing. If quality drops,
check for an **Indirect** connection and choose **Original** or **Maximum**
playback quality. The Plex desktop app may support formats that Plex Web converts;
the native Windows acceptance results below demonstrate this for AV1.

## Profiles and existing titles

Saving enabled rules creates three dedicated profiles if they do not exist.
Stackarr resolves their quality IDs from the connected app's schema. It never
edits a user's existing profiles or chooses one merely because it is named SD.

| Profile | Allowed release qualities |
|---|---|
| SD | SDTV, DVD, WEBRip/WEBDL 480p, Blu-ray 480p/576p where supported |
| 1080p | HDTV, WEBRip, WEBDL and Blu-ray 1080p |
| 4K | HDTV, WEBRip, WEBDL and Blu-ray 2160p |

CAM, workprints, screeners, telecine, telesync, disc images, raw captures and
remuxes are excluded. Automatic upgrades are off. The app's schema language
default is retained. Custom-format scores are neutral unless download format
preferences are selected below. Audio, language and release-size preferences are
outside these starter rules. They are also **not malware protection**. The dedicated profiles are verified again before use; if
edited in another app, Stackarr asks for a fresh review instead of repairing them
silently.

Saving rules does not reassign existing titles. **Preview existing library**
shows every title, original profile, proposed profile and matching rule. Applying
that preview changes only profile assignments. Stackarr sends no search command,
file move, deletion, monitoring or tag change. An app's normal processing still
applies to monitored titles after their profile changes.

Each library operation records the original profile IDs in an encrypted journal
before writes. Results and **Restore original profiles** remain available in
history after a dashboard restart. Undo checks the title's stable ID, current
profile, original profile definition, its scored custom-format definitions and
saved app connection. Conflicting later
edits are preserved. A lost response is marked uncertain and can be reconciled
through undo; a later review can apply the remaining assignments. These upstream
APIs do not offer an atomic transaction across titles, so partial results are
reported rather than described as an all-or-nothing change.

Imported native apps remain read-only. Rule previews do not grant permission to
change them. Reviews are session-bound, expire after ten minutes and are consumed
once; changed connections, credentials, policies, profiles or title assignments
invalidate a pending apply. Seerr must point to the same verified Arr instance
before its requests can use the saved rules.

The implementation uses the documented
[Sonarr v3 API](https://sonarr.tv/docs/api/) and
[Radarr v3 API](https://radarr.video/docs/api/), including their partial title
editor endpoints. No upstream implementation was copied. Recyclarr/Configarr
integration remains a separate future option for advanced profile management.

## Per-app setup completion

**Finish connecting** verifies and saves each ready installed app independently.
An unfinished Plex or Seerr account, or an unreachable app, no longer blocks the
other apps. Progress survives refreshes and restarts. Retry checks unfinished
connections while preserving completed ones and any separately imported settings.
Generated qBittorrent and companion logins are available as soon as their own
connection is saved. Arr web-login preparation can proceed once that
installation's Arr connections are saved, without waiting for Plex or Seerr.

Changing a previously completed connection does not transfer ownership of the
new target. Port recovery cannot rewrite ports after any connection in that
installation has completed. Credential handoffs remain validated as a whole
before any ready subset is saved, and all subset saves use a local transaction.

## Real end-to-end verification — 2026-10-21

The isolated six-app installation passed rule setup, title requests, downloads,
imports, Plex discovery and browser playback. All videos were original generated
colour bars and silence; the following names were metadata stand-ins, not copies
of the named works. Each title had three available private local releases, at
480p, 1080p and 2160p, so the test verified release selection as well as profile
assignment.

| Type | Metadata title | Year | Matching rule | Downloaded and decoded |
|---|---|---|---|---|
| Movie | Office Space | 1999 | Before 2000 → SD | 854×480 |
| Movie | Cast Away | 2000 | 2000 or later → 1080p | 1920×1080 |
| Movie | Jurassic Park | 1993 | Specific title → 4K | 3840×2160 |
| TV | Spaced | 1999 | Before 2000 → SD | 854×480 |
| TV | Black Books | 2000 | 2000 or later → 1080p | 1920×1080 |
| TV | Futurama | 1999 | Specific title → 4K | 3840×2160 |

- Browser requests used the suggested quality without a manual override. The
  two older-title exceptions overrode the SD year rule. Actual Arr profile IDs,
  metadata years and shared Plex root folders were checked after each request.
- All six selected releases transferred from a separate private seeder and
  imported automatically. The twelve wrong-resolution alternatives were rejected
  by the profiles and transferred zero payload bytes. Imported SHA-256 hashes
  matched the generated sources. No manual import or manual Plex scan was used.
- Both 4K samples played for 60 seconds each in real Plex Web: **3840×2160,
  1,442 decoded frames, zero dropped frames and no playback error**. The four SD
  and 1080p cases each played for 15 seconds with 364 decoded frames and zero
  drops. Plex independently reported the selected item as playing; its stream
  decisions confirmed video/audio copying rather than a lower-resolution video
  transcode. The files were 24 fps SDR H.264 with AAC audio. HEVC/HDR, remote
  streaming and TV-device playback are separate coverage.
- Stackarr confirmed all movie availability and Plex links. TV was correctly
  shown as partially available because each fixture supplied only episode one.
  Existing-library profile apply and undo also passed through the browser;
  original profile definitions, monitoring, paths, tags and existing files were
  preserved.
- Request choices, confirmations and history now show **SD**, **1080p** and
  **4K**, rather than internal versioned profile names. Profile IDs and policy
  validation are unchanged. The isolated source preview was restarted and the
  simplified choices and saved request labels were checked in the real browser.

The small generated samples required temporary lab-only release-size floors;
the original limits were restored. Test sources were removed, helper containers
and the six test torrents were stopped, and only these new test titles were left
unmonitored. The samples and policies remain in the isolated preview on port
29493, with the same test password as port 29480. Its integration transport can
access only the isolated app ports; Plex Web tests blocked working-server access.
Native Arr/Plex fingerprints and all 17 protected container records remained
unchanged. No working stack or published package was updated.

Validation: **91 relevant Python tests passed**, including new multi-title source
fixture tests; Ruff and diff checks passed. `tools/make_quality_media.py` creates
the original resolution variants in a network-disabled, resource-limited FFmpeg
container. `tools/torznab_fixture.py` now supports explicit per-title identifiers,
SD/HD/UHD categories and episode filtering. Private local evidence lives under
`test-results/fresh-review-20261020/quality-e2e/`; the consolidated result is
`test-results/fresh-review-20261020/quality-end-to-end-report.json`.

The fast 4K episode completion exposed a qBittorrent 5.2.4 transfer-counter
inconsistency: its session counter initially contained the full payload while
the all-time counter was zero. The acceptance check independently verified the
private seeder's per-torrent payload ledger and the imported file hash, rather
than inferring a transfer from a completed-file flag.

## HEVC and HDR10 playback verification — 2026-10-21

Five original moving test patterns were played in **two real Plex Web clients**
against the same receipt-owned isolated Plex on port 42401. Edge supported HEVC;
the bundled Chromium did not. These are playback-layer tests in a separate
**Stackarr codec tests** personal-media library, not a repeat of the previously
verified request/download/import pipeline. Existing Movies/TV libraries and Arr
titles were preserved.

| Source | Duration tested per browser | Edge output | Chromium automatic-quality output |
|---|---:|---|---|
| 1080p HEVC, 8-bit SDR | 30 s | 1920×1080 HEVC, copied | 1920×1080 H.264, transcoded |
| 4K HEVC, 8-bit SDR | 60 s | 3840×2160 HEVC, copied | 2276×1280 H.264, transcoded |
| 4K HEVC Main 10, SDR | 60 s | 3840×2160 HEVC, copied | 2276×1280 H.264, transcoded |
| 1080p HEVC Main 10, HDR10 | 30 s | 1920×1080 HEVC/PQ, copied | 1920×1080 H.264/SDR, transcoded |
| 4K HEVC Main 10, HDR10 | 60 s | 3840×2160 HEVC/PQ, copied | 2276×1280 H.264/SDR, transcoded |

All ten playback runs completed without video errors. Edge decoded 1,444–1,445
frames in each 4K run, with 1–6 dropped frames (under 0.5%). Its two 1080p runs
decoded 724 frames each, with four dropped each. Chromium decoded 1,445 frames
per 4K-source run and 725 per 1080p run, with **zero dropped frames**. Observed
startup times were approximately 5–6 seconds in Edge and 10–25 seconds in
Chromium. These are measurements from this lab, not device performance promises.

The 4K HDR10 file also passed a seek to 90 seconds and continued beyond 95 seconds
at 3840×2160. Captured video segments independently confirmed both paths:

- Edge received **HEVC Main 10, 3840×2160, 10-bit BT.2020/PQ**, retaining both
  mastering-display and content-light HDR10 metadata. Browser decoder diagnostics
  confirmed HEVC using a platform video decoder; Plex reported video/audio copying.
- Chromium received **H.264, 2276×1280, 8-bit BT.709 SDR** for the 4K HDR source.
  This is a working fallback, **not full-resolution 4K or native HDR output**.
  The server's existing tone-mapping setting remained enabled and unchanged.

Both browser contexts reported an SDR display. These tests establish HDR input
handling, HDR stream preservation to a capable decoder, and SDR fallback. They
**do not verify a physical display entering HDR mode or calibrated HDR colour**.
Dolby Vision and HLG were tested separately below. TV-device playback, remote
streaming, and sustained high-bitrate feature-film playback remain unverified. See Plex's explanation of
[HDR-to-SDR tone mapping](https://support.plex.tv/articles/hdr-to-sdr-tone-mapping/).

The quality-rule panel now includes **About 4K and HDR playback**, explaining that
the resolution choice does not guarantee a player's codec or HDR support. The
explanation was verified in the isolated preview, and all three existing quality
UI tests passed. No Plex codec, hardware, transcoder, or account settings were
changed to manufacture a pass.

`tools/make_codec_media.py` generates and probes the five-format matrix using the
pinned FFmpeg image, no network, at most two CPUs and 2 GiB memory. HDR pixels are
converted through linear light into BT.2020/PQ; the files are not merely tagged
as HDR. Each source contains four seconds of original 24 fps motion, looped into
a two-minute clip with silent AAC. The final generator was rerun as a complete
matrix after fixing colour signalling, first-packet probing, and peak memory use.

The acceptance harness now reads the current Plex title after metadata analysis
and explicitly stops its own test sessions. Samples remain in the separate lab
library. Evidence lives under `test-results/fresh-review-20261020/codec-e2e/`,
including both browser reports, source/segment probes, screenshots, and the seek
result. The consolidated report is `codec-playback-report.json` in that folder.
The original 17 protected container records, native Arr/Plex fingerprints, Plex
settings, original libraries, and Arr title settings remained unchanged.

## Dolby Vision, HLG and format preference acceptance — 2026-10-21

The isolated Plex server on **42401** now has a separate **Stackarr HDR format
tests** library. Six samples were tested in Edge and Chromium, with a fresh
browser context per sample. The prior test harness retained Plex's failed-player
state across pages; fresh contexts prevent that error dialog from contaminating
the next playback result. No Plex server or transcoder settings were changed.

| Source | Edge result | Chromium result |
|---|---|---|
| Dolby Vision Profile 5, 1080p and 4K | Plex refuses playback: Profile 5 colour space unsupported | Same explicit refusal |
| Dolby Vision Profile 8.1, 1080p | Full-resolution HEVC Main 10/PQ, copied | 1080p H.264/BT.709 SDR, converted |
| Dolby Vision Profile 8.1, 4K | 3840×2160 HEVC Main 10/PQ, copied | 2276×1280 H.264/BT.709 SDR, converted |
| HLG, 1080p | 1080p H.264/BT.709 SDR, converted | 1080p H.264/BT.709 SDR, converted |
| HLG, 4K | 1920×1080 H.264/BT.709 SDR, converted | 2276×1280 H.264/BT.709 SDR, converted |

Every playable 4K-source case ran for 60 seconds and every playable 1080p case
for 30 seconds. Edge's Profile 8.1 cases decoded 1,444/724 frames with one dropped
frame each. HLG and Chromium runs decoded 1,445/725 frames with zero drops.
Captured delivery segments independently confirm the codecs, dimensions and
colour tags above. Edge's Profile 8.1 delivery retained the Dolby Vision
configuration record and RPU metadata. Screenshots were inspected for the
expected distinct colour patches/bars; an independent SDR reference was also
extracted from Dolby's Profile 8.1 source.

**These browser contexts report an SDR display.** Preserving Dolby metadata in a
stream does not prove Dolby Vision display output. Native HLG/4K HLG display
output was not achieved here. These tests also do not establish calibrated
colour accuracy, Profile 7/8.4 compatibility, TV-app behavior, or sustained
high-bitrate playback. The green/purple failure was not reproduced: this Plex
version explicitly rejected Profile 5 instead. The UI explains both possible
outcomes and offers the requested download block.

The 1080p Dolby inputs are Dolby's clear, public test patterns. The 4K Dolby
inputs are **upscaled compatibility fixtures**, not native-4K masters: encoded
components were scaled without converting the Profile 5 IPT-PQ-C2 colour space,
and Dolby metadata was retained using FFmpeg's Dolby Vision encoder support.
FFprobe and dovi_tool verified profiles, compatibility identifiers and one RPU
per encoded frame across every final fixture. Source URLs/hashes and derivation
records are retained locally; Dolby media and tool binaries are not vendored.
HLG uses original pixel-converted moving patterns generated by
`tools/make_codec_media.py --case hevc-1080p-hlg --case hevc-4k-hlg` with a new
output directory argument. Generation uses the pinned, network-disabled FFmpeg
container, at most two CPUs and 2 GiB memory.

The preference acceptance test submitted **72 real interactive release
assessments** across isolated Sonarr and Radarr: 18 labelled releases, two
preference combinations, two apps. It verified positive ranking, negative-score
rejection, combined preferences never rescuing a block, underscore labels,
HDR10/HLG eligibility, and Dolby Atmos not triggering the DV detector. These
were metadata-only assessments from a private fixture indexer; no torrents were
fetched. Its advertised sizes were plausible test metadata, not payload sizes.
RSS and automatic searches were disabled. The temporary indexers were removed,
test title profiles restored, and the fixture container stopped.

The actual Stackarr UI saved both TV and movie preferences, disabled stale
previews after a selection changed, and passed a 390-pixel layout check. **134
focused Python tests and six quality-rule UI tests passed**; Ruff and diff
checks passed. Those tests cover retries, native read-only protection, tampered
filters blocking requests, old-profile preservation, and safe library undo.

The isolated source preview remains on **29493**. The original 17 protected
container records, native Arr/Plex fingerprints, original Plex libraries and
settings, and original Arr title settings were verified unchanged. No working
stack or published package was updated. Private evidence is under
`test-results/fresh-review-20261020/formats-e2e/`; the consolidated report is
`format-playback-report.json`.

Primary references: [Dolby profile definitions](https://ott.dolby.com/OnDelKits/Dolby_Vision_Online_Delivery_Kit/v1/Documentation/Specs/Visio_Profiles/help_files/topics/c_dovi_profiles.html),
[Dolby's Profile 5 colour-space notes](https://ott.dolby.com/OnDelKits/Dolby_Vision_Online_Delivery_Kit/v1/Documentation/Specs/Visio_Profiles/help_files/topics/c_notes_profile_public.html),
[Chromium's official test-media provenance](https://chromium.googlesource.com/chromium/src/+/main/media/test/data/README.md),
and [dovi_tool](https://github.com/quietvoid/dovi_tool) (MIT).

## AV1 download and playback acceptance — 2026-10-30

Four requests completed through the real Stackarr UI, Seerr, Prowlarr,
Sonarr/Radarr, qBittorrent, automatic import and automatic Plex discovery in the
isolated installation. Each request had five competing payloads: AV1 8-bit,
AV1 10-bit, HEVC 8-bit, HEVC 10-bit and Dolby Vision. Dolby Vision blocking was
enabled in every case. Title names exercised metadata matching; the downloaded
files contain original generated SDR colour bars and silent AAC, not those works.

| Metadata title | Rule and preferences | Downloaded and imported |
|---|---|---|
| Arrival | 1080p default; prefer AV1 and 10-bit | AV1, 1920×1080, 10-bit |
| The Expanse | Specific-title 4K override; prefer AV1 and 10-bit | AV1, 3840×2160, 10-bit |
| Edge of Tomorrow | Specific-title 4K override; avoid AV1 and 10-bit, prefer HEVC | HEVC, 3840×2160, 8-bit |
| Dark | 1080p default; prefer AV1, avoid 10-bit | AV1, 1920×1080, 8-bit |

All four imported SHA-256 hashes matched the private seed payloads. The seeder
transferred exactly 19,835,583; 6,112,594; 70,498,151; and 3,887,830 payload bytes,
respectively. The other **16 candidates transferred zero payload bytes**,
including all Dolby Vision candidates. Live Arr release assessments confirmed
the preference scores and negative-score rejections. No manual import or Plex
scan was used. Stackarr reported both movies as available and the TV seasons as
partially available, with the correct resolution and isolated Plex links.

The private feed advertised actual payload sizes. The generated movie/episode
containers have two-hour/30-minute durations to exercise normal runtime checks;
they are repetitive patterns, not representative feature-film encodes. Temporary
lab-only minimum sizes for WEB-DL 1080p/2160p were restored after acceptance.
The Dolby candidates reuse the public test-pattern fixtures described above;
none was downloaded by the receiving client.

Two request-flow fixes were verified:

- Seerr's cached profile list omitted newly saved profiles during three real
  requests, across both Sonarr and Radarr. Stackarr successfully used the managed
  profiles verified directly against the same Arr server. Regression tests also
  cover Seerr refreshing/reordering its cache and continue to reject changed
  server bindings, live profiles and custom-format definitions.
- Adding the separate AV1 test library no longer invalidates an existing movie
  or TV mapping. Requests still verify the selected Plex folder, server identity
  and storage mounts. Moving or removing the selected folder remains a blocker.

All four imported files played in **both Edge and Chromium**, with fresh Plex
Web sessions: 30 seconds for 1080p sources and 60 seconds for 4K sources. All
eight runs also sought to 90 seconds and continued beyond 95 seconds. Captured
delivery segments were independently probed:

| Imported source | Edge delivery | Chromium delivery |
|---|---|---|
| AV1 10-bit, 1080p | H.264, 1920×1080, 8-bit | H.264, 1920×1080, 8-bit |
| AV1 10-bit, 4K | H.264, 2276×1280, 8-bit | H.264, 2276×1280, 8-bit |
| HEVC 8-bit, 4K control | HEVC, 3840×2160, 8-bit, copied | H.264, 2276×1280, 8-bit |
| AV1 8-bit, 1080p | H.264, 1920×1080, 8-bit | H.264, 1920×1080, 8-bit |

Each run decoded 725 or 1,445 frames. Seven had no dropped frames; Chromium's
1080p AV1 8-bit case dropped one. The eight earlier moving-pattern Plex tests
also passed for AV1 at 1080p/4K and 8/10-bit, with the same H.264 conversion and
zero dropped frames. Selecting Plex's advertised maximum 4K conversion quality
in a separate Edge check did not produce full-resolution output.

**AV1 playback works here through Plex conversion; Plex Web did not preserve
4K resolution or 10-bit depth.** The original downloaded 4K/10-bit files remain
intact. A separate plain-video decoder control, serving original sample bytes
through the isolated Plex server without transcoding, played all four AV1
formats at source resolution in both browsers and passed the same seek check.
Edge used D3D11VideoDecoder with zero drops; Chromium used Dav1dVideoDecoder,
with four/two dropped frames in its 4K 8/10-bit runs and zero in its 1080p runs.
This control is **not Plex Web Direct Play**. Browser codec support alone does
not establish Plex client compatibility.

The format-preference UI now explains that AV1/10-bit may require conversion
and lose resolution or bit depth. Both browser contexts reported an SDR display;
physical 10-bit/HDR output, AV1 HDR, TV apps, remote streaming and sustained
high-bitrate playback remain unverified. The generator now supports AV1 and
explicit SVT-AV1 BT.709 colour signalling, verified with FFprobe. Moving samples
contain four seconds of original 24 fps motion looped into two minutes; the
download fixtures use static bars for small, reproducible private transfers.

Docker Desktop was started with the owner's explicit authorization, including
automatic startup of existing containers. A fresh baseline after that restart
verified **28 non-fixture container configurations and native Arr/Plex
fingerprints unchanged**. The original 14 lab titles retained their assignments,
and original profiles, custom formats, download protection and Plex libraries
were preserved. Temporary sources were removed, both fixture helpers and the
four test torrents stopped, new titles unmonitored, and future policies and size
floors restored. Samples remain available in the isolated libraries. Test playback
sessions were stopped. No working stack settings or published package changed.

The isolated Plex hidden `LanguageInCloud` value differed from the October 21
baseline after the nine-day pause and authorized restart; it was left untouched.
Plex preference values were unchanged during final playback and cleanup. This
distinction avoids treating runtime or cloud synchronization drift as a setting
that the test should overwrite.

**171 focused Python tests and six quality-rule UI tests passed**, as did Ruff
and diff checks. Private evidence, screenshots, transfer ledgers, source/delivery
probes and cleanup checks are under
`test-results/fresh-review-20261020/av1-e2e/`; the consolidated result is
`av1-playback-and-download-report.json`. Its playback result is separate from
the explicitly unsuccessful Plex Web native AV1 4K/10-bit preservation result.

## Native Plex desktop AV1 verification — 2026-10-30

The official **Plex for Windows 1.115.0.426-4e960a1d** player was extracted into
the isolated test directory. Its installer checksum and Plex signature were
verified. The owner signed in to the new desktop profile; browser sign-in alone
does not sign in this player. The bundled Windows App Runtime dependency was
installed per-user. The existing Plex Media Server installation was not changed.

Two connection problems initially prevented a useful decoder test:

- The isolated Docker server's alternate host port was not discoverable as a
  direct connection. Advertising its loopback URL enabled local discovery.
  This is a same-PC lab address, not a LAN or remote-access configuration.
- Direct HTTPS then failed with player error **4294967283**. The isolated server
  presented an incomplete certificate chain. Its old certificate was backed up
  and only that lab container was restarted to obtain a fresh official Plex
  certificate. The new three-certificate chain verifies against the player's
  unchanged bundled trust store. No TLS verification or security setting was
  disabled. See [Let's Encrypt's current certificate chains](https://letsencrypt.org/ca/certificates/).

After this repair, the already-open player retained a 2 Mbps Relay limit and
transcoded to SD despite its existing Maximum/recommended quality preferences.
Restarting only the test player cleared that cached limit. Playback then used
the original AV1 stream. This is why a connection error or a quality cap must be
distinguished from unsupported video decoding. Plex documents
[custom server access URLs and Relay](https://support.plex.tv/articles/200430283-network/).

**All six native desktop cases passed with Direct Play and no server
transcoding.** Server session observations were correlated with the player's
read-only decoder telemetry, rather than relying on the source Media Info panel.

| AV1 sample | Preserved video | Decoder observation | Dropped frames |
|---|---|---|---|
| Moving pattern | 3840×2160, 10-bit | 60 seconds | 0 |
| Moving pattern | 3840×2160, 8-bit | 60 seconds | 0 |
| Moving pattern | 1920×1080, 10-bit | 30 seconds | 0 |
| Imported TV fixture, The Expanse S01E01 metadata | 3840×2160, 10-bit | 60 seconds | 0 |
| Imported movie fixture, Arrival metadata | 1920×1080, 10-bit | 30 seconds | 0 |
| Imported TV fixture, Dark S01E01 metadata | 1920×1080, 8-bit | 30 seconds | 0 |

Every case used NVIDIA hardware decoding (`nvdec-copy`) at 24 fps. Ten-bit
sources decoded as `p010`; eight-bit sources decoded as `nv12`. The imported
fixtures are the actual files previously transferred through qBittorrent,
imported by Arr, and mapped into the isolated Plex libraries using the format
preferences and Seerr profiles verified above. Their bytes contain original
synthetic test bars and silent AAC audio, not the named films or episodes.

Both 4K 10-bit samples also passed seeking: the moving pattern continued from
89 to 108 seconds, and the imported fixture from 15:00 to 15:19. Correlated
decoder observations retained 3840×2160 AV1, `p010`, and hardware decoding after
both seeks. These results establish native desktop playback at original video
quality on this PC. They do not establish physical panel 10-bit/HDR output,
AV1 HDR, sustained high-bitrate playback, subtitle/audio combinations, or
compatibility with other clients and devices.

Stackarr's quality panel now explains how to inspect the active video decision,
spot an indirect connection or quality cap, and distinguish source metadata
from actual playback. All six quality-rule UI tests passed after the copy change.
The lab's loopback discovery fix and refreshed certificate are retained so its
desktop playback remains usable; the original certificate is backed up.
No working server was restarted or reconfigured. Final checks confirmed all
28 monitored container configurations and native Arr/Plex setting fingerprints
unchanged. Only the isolated Plex `customConnections` preference changed.
Test playback was stopped and the temporary decoder observer removed.

The consolidated local evidence is
`test-results/fresh-review-20261020/plex-desktop-e2e/status.json` and `matrix.json`,
with per-session and seek observations alongside `decoder-observations.jsonl`.
Private preferences and installation artifacts remain in the ignored test
directory; they are not part of the repository documentation.
