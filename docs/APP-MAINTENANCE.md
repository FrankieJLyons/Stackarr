# Repair or remove a Docker app

Open **Apps → Start, stop & recover → Check installation**. Controls apply only to
apps installed and owned by this Stackarr installation. Apps connected for
monitoring keep their separate management tools.

Choose **Review repair** to recreate one app's container from its saved image,
ports and folders. Review the explanation, then choose **Repair app**. Stackarr
stops that app, saves and verifies an encrypted configuration backup, recreates
the container and checks readiness with the saved credentials where available.
The same image is used without downloading a replacement. Its settings volume,
login, media and downloads remain in place. An existing stopped app stays stopped;
a missing container starts from its retained settings. Stopped-app repair creates
the replacement without starting its background jobs. Repair does not reset an
account, choose new ports or upgrade an app.

Choose **Review remove**, then **Remove app, keep settings** to remove only its
container. Stackarr saves a verified settings backup first. It keeps the
configuration volume, image, private network, generated login, Stackarr connection
settings, backups, media and downloads. The app stays listed so **Review repair**
can bring it back. Monitoring and dependent apps may report it offline while its
container is absent. Reopening Stackarr does not reinstall it automatically.
There is no permanent-data deletion option in these controls.

Plex's image-declared anonymous `/transcode` scratch volume is retained and reused
when its original identity and exclusive ownership can be verified. An unknown,
shared or host-bound extra volume is never adopted. Scratch data is excluded from
configuration snapshots and whole-host recovery, alongside media files.

Both actions interrupt active work in the selected app. Other app containers stay
unchanged. The review and approval are bound to your signed-in session, expire
after five minutes and can be used only once. Changed container identities,
images, environment, mounts or privileges require inspection. Shared configuration
volumes, missing settings, linked/unavailable media folders and changed ownership
block maintenance. A repair also requires its saved ports to be free. Stop
another service yourself if you want to release a conflicting port; Stackarr does
not move or stop that service.

Safety snapshots appear in **Backups** as before-repair, before-removal or
before-recovery copies. They include app databases/configuration and protected
credentials; media/download files are excluded. A configured separate backup disk
receives a verified copy of the initial safety snapshot before container removal.
Retained configuration volumes can still be backed up while their app containers
are absent, without starting them. Repair a missing container before an ordinary
configuration restore. Whole-host recovery includes retained installation receipts
and reconstructs their apps, including containers removed with settings retained.

If repair checks fail, Stackarr saves the candidate configuration separately,
restores the verified pre-repair configuration and recovers the app's previous
running state. A missing app stays absent if repair fails. If Docker/storage is
unavailable or recovery cannot be verified, the result remains **needs-recovery**;
other mutations and scheduled backups wait. Your media and checkpoints remain.

After a process or host interruption, reopen **Start Stackarr.cmd**, then check the
installation and choose **Review maintenance recovery → Recover maintenance**.
Read the review: it can replace newer app settings with the before-repair
checkpoint. A completed removal stays removed. Interrupted app maintenance is
never replayed automatically. Keep the entire Stackarr state directory and its
encryption key so snapshots and installation receipts remain usable.

These controls repair the container runtime around intact retained settings. They
do not reconstruct a lost settings volume, repair corrupt application databases,
adopt changed/external containers or perform an image upgrade. Use a verified
app backup or [whole-host recovery](HOST-RECOVERY.md) for lost data, and reviewed
Updates for a supported image change. Signing, clean-Windows/LAN certification
and broader runtime/account migrations remain separate release gates.

Packaged Docker acceptance exercises qBittorrent repair/removal, retained-settings
backup, stopped-state preservation and recovery after actual candidate writes and
worker interruption in a four-app original-sample lab. All nine main apps pass
read-only ownership/repair reviews; their containers and data are preserved.
The additional isolated five-app matrix covers actual repair and failed-repair
configuration writes, distinct-image update/rollback, failed/interrupted update
recovery and encrypted restore for Plex, Seerr, Tautulli, Kuma and Cleanuparr.
See [PROGRESS.md](PROGRESS.md) for the exact package and test evidence, and
[Plex, Seerr and companion maintenance](OPTIONAL-APP-MAINTENANCE.md) for the
additional five-app matrix and account boundaries.
