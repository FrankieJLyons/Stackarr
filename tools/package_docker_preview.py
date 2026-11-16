"""Bundle a prebuilt Docker dashboard and Windows controller without runtime state."""

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from stackarr.bundled_images import catalog as bundled_catalog
from stackarr.bundled_images import verify as verify_bundled
from stackarr.docker_runtime import executable


def digest(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--output", type=Path, required=True, help="New empty output directory")
    parser.add_argument("--controller-executable", type=Path, default=Path("dist/StackarrPreview.exe"))
    parser.add_argument("--alpha-test", action="store_true", help="Portable state, a new test-media folder and a short alpha walkthrough")
    parser.add_argument("--guided-lan", action="store_true", help="Require a self-tested launcher with the pinned gateway bundled")
    args = parser.parse_args()
    root = Path.cwd()
    if args.guided_lan:
        with tempfile.TemporaryDirectory(prefix="stackarr-lan-package-") as temporary:
            report = Path(temporary) / "selftest.json"
            result = subprocess.run([str(args.controller_executable.resolve()), "--self-test-report", str(report)],
                                    creationflags=subprocess.CREATE_NO_WINDOW, timeout=120)
            value = json.loads(report.read_text()) if report.is_file() else {}
            if result.returncode or not value.get("passed") or not value.get("guided_lan"):
                raise SystemExit("Guided LAN packaging requires the tested launcher and pinned bundled Caddy.")
    output = args.output.resolve()
    if not output.is_relative_to(root.resolve()) or output.exists():
        raise SystemExit("Choose a new output directory inside this workspace.")
    output.mkdir(parents=True)
    for source, name in (
        (args.controller_executable.resolve(), "StackarrPreview.exe"),
        (root / "platform/docker/Start-StackarrPreview.ps1", "Start-StackarrPreview.ps1"),
        (root / "LICENSE", "LICENSE"),
        (root / "docs/LICENSE-NOTES.md", "THIRD-PARTY-NOTICES.md"),
    ):
        if source.is_symlink() or not source.is_file():
            raise SystemExit("A required package input is unavailable.")
        shutil.copyfile(source, output / name)
    (output / "Start Stackarr.cmd").write_text('@echo off\nstart "" "%~dp0StackarrPreview.exe" --package-first-run\n', encoding="ascii")
    (output / "Recover Stackarr.cmd").write_text('@echo off\nstart "" "%~dp0StackarrPreview.exe" --host-recovery\n', encoding="ascii")
    (output / "README.txt").write_text(
        "Stackarr Docker media-app preview\n\n"
        "1. Unpack this entire folder and open Start Stackarr.cmd. Readiness checks and Docker setup are included; Python and a separate readiness download are not needed.\n"
        "2. Choose new apps or existing apps. If Docker is missing, review Install Docker Desktop before the verified download and vendor installer open. Complete Docker's prompts and first start, then Check again and Continue to Stackarr. Existing apps open in the local Stackarr window without requiring Docker. A requested Windows restart remains your choice; reopen Start Stackarr afterward.\n"
        "3. Create your local Stackarr password and select your apps. Available ports are chosen for you. Media apps ask for one folder; an already shared folder is reused. Other apps need no media folder. Review and approve installation.\n"
        "4. Finish Plex sign-in and Server Setup. Give the new server a name you recognise. At Media Library choose Next without Add Library, then Done. Return to Stackarr; you do not need Plex's Docker folder picker.\n"
        "5. In Stackarr choose Check Plex sign-in & continue, review, then prepare watching and requests. Stackarr uses your chosen Windows media folder, prepares missing Movies and TV libraries and connects the new Seerr owner using that same Plex sign-in. No second Seerr sign-in or key copying is needed. Check Plex libraries can reopen this preparation later. Existing accounts and libraries are preserved.\n"
        "6. Review app login setup and prepare/save the generated Arr logins. Your Stackarr owner password reveals one login briefly; existing logins are preserved.\n"
        "7. Follow the setup checklist to review app connections and apply the reviewed changes, including Seerr's Arr profiles and library folders. Under Where will your media come from?, choose a provider you already use, enter its required account details, review, then Test and connect source. Check source sharing and test both a movie and TV search. Advanced provider setup opens Prowlarr or accepts an existing Torznab feed. No media is requested during source setup.\n\n"
        "8. Home lets you find a movie or show, choose its download quality and request a movie or selected TV seasons. Your requests shows progress and the chosen quality. Reviewed automatic import discovery scans the matching Plex libraries after successful imports; keep Stackarr running, though this browser window can close. Seerr checks newly available titles. Open in Plex hands the verified title to Plex; choose Play there and Back to return. Existing shows keep their Sonarr quality. Device playback, household permissions and future-season automation remain separate. Manage server opens setup, apps and maintenance.\n\n"
        "Use Restart on a managed app card to review a restart (or start a stopped app). In Apps,\n"
        "check an installation for advanced Start, Stop, Repair and recovery controls.\n"
        "9. In Backups, review an encrypted Docker app backup, refresh the list and review a restore when needed. Apps stop briefly; media/download files stay untouched. Restore creates a safety copy first.\n\n"
        "10. In Apps, choose Check packaged updates, review a pinned candidate and approve Update app. Failed health/settings checks recover the previous image and configuration. Refresh update history to review rollback or recover an interrupted update. Keep your data directory and encryption key.\n\n"
        "11. In Backups, choose a folder on another physical disk, select apps, nightly time and copies to keep, then review/save the backup plan. Run it now to verify the destination. Save your recovery key privately and separately. Only older scheduled snapshots are removed; manual and safety copies are retained. A missing local snapshot can restore from its verified second-disk copy.\n\n"
        "12. For Tautulli, Uptime Kuma and Cleanuparr, open Apps, Review companion setup and Set up companions. Then choose Finish connecting. Generated local logins are available with your Stackarr owner password. Kuma monitors service availability. Cleanuparr starts in dry-run with every automatic job off and no media/download folders mounted.\n\n"
        "13. If a port becomes busy, choose Use available ports and review again. Existing services stay running. Manual ports are under Advanced port settings. A new preview also chooses available dashboard/setup ports; reopening it keeps its saved addresses. Choose another folder opens the Windows folder dialog on the installation computer. Cancel keeps your previous choice.\n\n"
        "Python, a source checkout and a local image build are not needed. Seerr 3.5.0-stackarr.2 is included with the Manage Users security fix, same-tab Plex sign-in and empty-library setup; other selected apps download pinned images after installation approval. Keep the complete package to reload Seerr for recovery.\n"
        "This unsigned public beta requires Windows 11 x64. New Docker apps need Docker Desktop running with Linux containers; the included prerequisite flow guides its reviewed setup.\n"
        "It does not install Windows services, change firewall/router rules or certify startup while signed out.\n"
        "Access is local to this computer. Keep the app-data directory: it holds your account, enrollment and installation receipts.\n"
        "The controller runs in the background while the dashboard and selected apps run in Docker. Reopen Start Stackarr after a host restart.\n"
        "Docker app restore is limited to the same owned installation and pinned version. Keep the entire app-data directory, including controller/state/secrets.key; backups cannot be decrypted without it. Media is not backed up. Same-disk snapshots do not protect against disk failure.\n"
        "Scheduled app backups run while the controller and Docker are running. A missed night runs once after startup; a failed run retries after an hour. Media files are not backed up.\n"
        "14. In Backups choose Prepare whole-host recovery, review all apps, then Create recovery file. Maintenance results show the saved encrypted file (also copied to your approved backup disk). Save the recovery key separately. On an empty replacement installation, unpack this package and open Recover Stackarr.cmd, choose the recovery file/key, an empty state folder and your preserved media folders, then approve the review. Your Stackarr password and app logins are retained; sessions are revoked and backup schedules pause for review. Original app ports must be free. Existing app volumes or networks block recovery. Media must already be available or restored from its own backup. Keep the complete package and pinned images available.\n\n"
        "15. In Settings, choose a trusted downloaded Stackarr update ZIP, check update status and review Update Stackarr. The dashboard and private controller update together; media apps keep running. Encrypted database checkpoints and previous releases are retained. Failed checks recover the previous Stackarr release/data. Update history offers reviewed rollback; newer Stackarr settings are replaced only after that review, with a safety checkpoint retained. If interrupted, reopen Start Stackarr from this recovery-capable package. Startup follows the saved active release and recovers pending maintenance before opening the dashboard. Keep your Stackarr state folder and staged releases.\n\n"
        "16. In Apps, Check installation then review Repair or Remove for one owned app. Both save a verified encrypted settings backup before container replacement/removal. Remove app, keep settings removes only the container: login, settings volume, media, downloads, connections and backups remain. Repair uses the same saved image, ports and folders and can bring a removed app back. Failed repair restores its settings checkpoint. After interruption reopen Stackarr and review Recover maintenance for that app; operations are not replayed automatically. Missing images, volumes, changed ownership or shared settings block maintenance. Retained settings can still be backed up while the container is absent.\n\n"
        "17. In Settings, Review Stackarr removal then Remove Stackarr, keep settings. Only the Stackarr dashboard container is removed and its private controller stopped, after a verified encrypted checkpoint. Media apps keep running. Your account, settings, keys, generated app logins, receipts and backups stay in the state folder and retained Docker volumes. Scheduled backups pause while Stackarr is removed. Reopen Start Stackarr.cmd from this package to Review reinstall in the local window. Reinstall checks copies of retained data before promotion; failed/interrupted reinstall keeps the original data and returns to the removed state. Do not delete the state folder, retained Docker volumes or staged releases. Missing/shared/changed data and occupied saved ports block reinstall; use whole-host recovery for lost state. Older packages cannot silently reinstall a completed removal.\n\n"
        "18. In Settings choose Review Stackarr repair to recreate only its dashboard and restart its private controller using the same saved release and checked settings copies. Your password, connections and backups are retained; media apps keep running. If Stackarr cannot open, restore Docker and writable storage, then reopen Start Stackarr to review repair in the local window. Missing account keys or settings volumes require whole-host recovery, never an automatic reset. A disk-full or access failure retains the original data and checkpoint; restore storage access and reopen this repair-capable package to recover.\n\n"
        "19. Check Docker reports estimated network capacity without creating or removing networks. Exhausted address pools block new app batches; review unused networks or address-pool settings with your Docker administrator, then check again. Failed or interrupted image downloads offer Retry download. Completed images remain cached; the same reviewed images, ports and folders are reused. Stackarr verifies each image digest/platform before creating app folders or starting containers. Only downloads retry automatically; app setup waits for a verified image and your explicit resume after interruption.\n\n"
        "20. If a port becomes busy during final app startup, choose Review available ports, check the changed addresses, then Apply new ports & resume. This resumes the same installation and retains its settings volumes, logins and media. Running apps keep their containers and addresses. Existing services using the old ports keep running. If the original port becomes free, choose Resume installation instead. Changed/shared resources block recovery for inspection; nothing is automatically deleted or reset.\n\n"
        "Updates cover compatible Stackarr preview packages and packaged same-major app candidates only. Major state migrations, network/cloud backup destinations, household/LAN certification and signing remain release work. Whole-host recovery is tested in isolated Docker; replacement-Windows and native recovery-dialog walkthroughs remain release gates.\n", encoding="utf-8")
    if args.alpha_test:
        (output / "Start Stackarr.cmd").write_text(
            '@echo off\n'
            'if not exist "%~dp0alpha-data\\media" mkdir "%~dp0alpha-data\\media"\n'
            'if not exist "%~dp0alpha-data\\media" exit /b 1\n'
            'start "" "%~dp0StackarrPreview.exe" --package-first-run '
            '--data-directory "%~dp0alpha-data\\docker" '
            '--connect-directory "%~dp0alpha-data\\existing" '
            '--prerequisite-directory "%~dp0alpha-data\\prerequisites" '
            '--media-folder "%~dp0alpha-data\\media"\n', encoding="ascii")
        (output / "README.txt").write_text(
            "Stackarr private preview - Windows Docker test\n\n"
            "Extract the complete ZIP and double-click Start Stackarr.cmd. Keep all files together.\n"
            "Settings and the separate test-media folder are created in alpha-data beside the launcher.\n"
            "Keep this extracted folder in one location so Docker can find its saved mounts.\n\n"
            "1. Choose Install apps on this computer, then Continue to Stackarr when checks pass.\n"
            "2. Create your local Stackarr password. No Stackarr online account is needed.\n"
            "3. Choose Movies & TV · recommended for the six-app request setup, or choose a\n"
            "   smaller/custom setup. Tautulli, Uptime Kuma and Cleanuparr are optional.\n"
            "   Leave automatic ports selected and follow the saved setup checklist.\n"
            "4. The new test folder is offered automatically. Setup shows one Movies folder\n"
            "   and one TV folder. Choose 1080p for both for this first run. You can also choose\n"
            "   4K / UHD or Other (SD / 720p). These choices do not split or move media.\n"
            "5. Review the apps, folders and quality choices, then Download & install these apps.\n"
            "6. If selected, complete Plex sign-in yourself and give its new server a distinct name.\n"
            "   Skip adding libraries there; return to Stackarr and Check Plex sign-in & continue.\n"
            "7. Review Prepare watching and requests. Stackarr creates missing Movies and TV libraries,\n"
            "   reuses the Plex sign-in in the new requests app, and connects the new download apps.\n"
            "   You do not need a second Plex sign-in, folder paths or app-key copying.\n"
            "8. If you selected companion apps, Review companion setup and Set up companions.\n"
            "   Then choose Finish connecting.\n"
            "   This prepares Tautulli, Uptime Kuma and Cleanuparr's local logins and connections.\n"
            "9. Preview app connections and apply the review. Seerr uses the quality profiles\n"
            "   you selected for new requests. For direct adds in Sonarr/Radarr, select the same\n"
            "   profile there. Native profile rules and existing Seerr connections are preserved.\n"
            "10. Under Where will your media come from?, choose a provider you already use.\n"
            "    Enter its required account details, then Test & connect source.\n"
            "    Some sources need their own account or subscription. Advanced provider setup\n"
            "    opens Prowlarr or accepts an existing Torznab feed. Check source sharing.\n"
            "11. Test a movie search and a TV search. No media is downloaded by these checks.\n"
            "    No matches means try another title; sign-in, category and search errors give\n"
            "    different guidance. A catalog title alone does not guarantee a copy exists.\n"
            "12. Open Home to browse/search movies and TV shows. Review a title, then Request\n"
            "    movie or choose TV seasons and Request selected seasons. Requests use your\n"
            "    connected Seerr account. Choose Download quality before submitting. Your requests\n"
            "    follows native status; Your library shows 12 recently added available/partial\n"
            "    titles. Open a title to verify the configured Plex server and library item,\n"
            "    then Open in Plex in the same tab. Choose Play there; use Back to return.\n"
            "    Manage server opens setup, apps and maintenance. Advanced quality, future-season\n"
            "    automation, approvals and household permissions remain in Seerr.\n"
            "    Preview app connections to enable Plex notifications after imports and\n"
            "    Seerr checks every minute after Plex has matched the files. Existing Plex\n"
            "    connections and custom schedules are preserved. Check notices if unavailable.\n"
            "    The new flow passes native-app checks against a Plex protocol simulator;\n"
            "    real-account import-to-availability verification remains pending because\n"
            "    its disposable Plex server was kept unclaimed. Playback needs a device test.\n"
            "    Existing files need no download source. Test your usual viewing device too.\n"
            "    App logins can be viewed with your Stackarr password when needed.\n\n"
            "Docker groups use stackarr-controller and stackarr-apps. Additional installations\n"
            "use short numbered suffixes when an existing group or retained storage owns a name.\n\n"
            "Reopen Start Stackarr.cmd to return to this same installation. Closing the browser\n"
            "does not stop the containers. Keep alpha-data, Docker settings volumes and this package.\n"
            "Private unsigned alpha; local access. Cleanuparr has automatic cleanup disabled.\n"
            "Clean-Windows Docker setup, reboot startup and LAN access remain uncertified.\n", encoding="utf-8")
    # Keep the first-run instructions short; retain detailed operations separately.
    technical_guide = (output / "README.txt").read_text(encoding="utf-8")
    (output / "README.txt").write_text(
        "STACKARR 0.1.0 - WINDOWS PUBLIC BETA\n\n"
        "Start here\n"
        "1. Extract this complete ZIP into its own folder. Keep the files together.\n"
        "2. Double-click Start Stackarr.cmd. Choose Install apps on this computer.\n"
        "   If Docker is missing, follow the guided installation and reopen Stackarr afterward.\n"
        "3. Create your local Stackarr password. Choose Movies & TV - recommended.\n"
        "4. Pick one media folder, choose your movie and TV quality (1080p suits most screens),\n"
        "   then review and install. Stackarr chooses free ports and remembers your progress.\n"
        "5. Sign into Plex. At Media Library, choose Next without Add Library, then Done.\n"
        "   Return to Stackarr, Check Plex sign-in & continue, then Prepare watching and requests.\n"
        "   Stackarr prepares Movies and TV, connects requests with that same Plex sign-in, and\n"
        "   connects the new download apps. Choose your provider and Test & connect source.\n"
        "   Enter the provider's own details when asked. App keys are handled privately.\n"
        "6. Open Home, search for a movie or TV show, choose Download quality and request it.\n"
        "   For TV, select the seasons you want. A quality choice applies to that new title;\n"
        "   more seasons of an existing show keep its existing quality settings.\n"
        "7. Choose Follow in Your requests. Imports can show Adding to Plex while the library\n"
        "   is being checked. When available, open the title and choose Open in Plex, then Play.\n"
        "   Use your browser's Back button to return to Stackarr.\n"
        "8. Reopen Start Stackarr.cmd to return to this same setup. Keep the extracted folder.\n\n"
        "You need your own Plex account and content sources for new downloads. Sources may\n"
        "need a separate account or subscription, and must offer a matching release. Existing\n"
        "movie and TV files can be watched without a download source.\n\n"
        "Use the Apps tab to choose a supported app and open its setup dialog.\n"
        "Settings / Appearance offers six colours, light/dark mode and overview cards.\n"
        "Setup is an ordered checklist; Help / FAQ holds the guides. Health keeps app action history.\n"
        "Configured apps open in the blue Media Stack control room. Add app installs or connects\n"
        "another app; Restart on a managed app card checks its state before your review.\n"
        "Discover opens browsing and requests. Setup, Apps and Backups remain one click away.\n\n"
        "This is an unsigned public beta. Real-account import-to-playback, a clean Windows\n"
        "install, TV/phone access and restart behavior still require acceptance testing.\n",
        encoding="utf-8")
    with (output / "README.txt").open("a", encoding="utf-8") as guide:
        if args.guided_lan:
            guide.write("\nHOME NETWORK & RECOVERY\n\nReopen Start Stackarr.cmd and choose Home network & recovery. Prepare the home\nconnection and prepare secure access. Review activation, start the gateway, then\ncopy its address. Download the public certificate and trust it once per device.\nChoose your device in the helper for instructions. An optional local computer name\ncan be used if your devices already resolve it. Keep the local recovery address. Preparation keeps current apps and host network settings\nunchanged. The helper includes reviewed activation, gateway restart and LAN\nrollback. Certificate trust, firewall access and signed-out Windows startup still\nneed acceptance on a spare host; no system settings are installed automatically.\n\n")
        guide.write("\n\nADVANCED REFERENCE\n\n" + technical_guide)
    docker = executable()
    bundled = bundled_catalog()
    def call(arguments):
        return subprocess.check_output([docker, *arguments], text=True)
    for row in bundled.values():
        verify_bundled(call, row["image"])
    # Docker save by digest alone loses the repository association on load.
    # Save the reviewed tag too, after binding it to the exact immutable image.
    app_tags = []
    for row in bundled.values():
        tag = row["image"].split("@", 1)[0] + ":" + row["version"]
        if call(["image", "inspect", tag, "--format", "{{.Id}}"]).strip() != call(["image", "inspect", row["image"], "--format", "{{.Id}}"]).strip():
            raise SystemExit("The packaged app tag does not match its reviewed immutable image.")
        app_tags.append(tag)
    subprocess.run([docker, "save", "--output", str(output / "stackarr-image.tar"), args.image,
                    *app_tags], check=True, timeout=300)
    image_id = subprocess.check_output([docker, "image", "inspect", args.image, "--format", "{{.Id}}"], text=True).strip()
    manifest = {"schema": 1, "image": args.image, "image_id": image_id,
                "bundled_app_images": [{"app": key, "image": row["image"], "image_id": call(["image", "inspect", row["image"], "--format", "{{.Id}}"]).strip()} for key, row in bundled.items()],
                "release": output.name, "maintenance": {"protocol": 1, "state_schema": 1}, "runtime_repair": 1, "lan_access": 1, "signin_startup": 1,
                "source_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
                "source_dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()),
                "signed": False, "files": {path.name: digest(path) for path in output.iterdir() if path.is_file()},
                "scope": "Docker Desktop preview, no runtime data, enrollment, credentials or media included"}
    if args.alpha_test:
        manifest["alpha_test"] = {"version": "0.1", "state": "alpha-data/docker", "media": "alpha-data/media",
                                  "library_layout": "one Movies folder and one TV folder", "default_request_quality": "1080p"}
    if args.guided_lan:
        manifest["guided_lan"] = 1
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    archive = output.parent / (output.name + ".zip")
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
        for path in sorted(output.iterdir()):
            bundle.write(path, output.name + "/" + path.name)
    archive.with_suffix(".zip.sha256").write_text(digest(archive) + "  " + archive.name + "\n", encoding="ascii")
    print("Docker preview package: " + str(archive))


if __name__ == "__main__":
    main()
