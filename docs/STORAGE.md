# Choosing a media folder

Choose a dedicated folder on the computer that will run your applications. The
wizard shows proposed movie, TV and download folders and the paths apps will see.
Plex gets read-only media access; Sonarr, Radarr and qBittorrent need write access.
Monitoring-only setups do not require a media folder.

Do not select an entire drive or filesystem root. Paths containing parent-folder
traversal and Windows device paths are rejected. Network shares are recognized but
not certified merely because their addresses look valid. Docker and the background
host account must both be able to access a share. Application databases stay on
their separate configuration volumes.

Planning does not create folders, move files or test write access. Save & check
installation computer performs the available read-only host checks. It does not
prove container permissions or hardlink support; a disposable test-file check with
explicit user consent remains installer work. Existing installation paths are not
rewritten by this planner.
