"""Original Seerr request fixtures; inert MKV padding meets existing TV size floors."""

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from stackarr.docker_runtime import executable
from tools.torznab_fixture import FFMPEG, torrent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume", action="store_true", help="Resume the known pre-FFmpeg failure without replacing media")
    args = parser.parse_args()
    source = Path("test-results/docker-core-05cebfd84fd1/seed-media").resolve()
    root = Path("test-results/docker-seerr-request-20261017").resolve()
    root.mkdir(exist_ok=True)
    output = root / "seed-media"
    output.mkdir(exist_ok=args.resume)
    previous = json.loads((source / "fixtures.json").read_text())
    for row in previous:
        with (source / row["filename"]).open("rb") as stream:
            assert hashlib.file_digest(stream, "sha256").hexdigest() == row["sha256"]
    padding = root / "padding.bin"
    if not padding.exists():
        with padding.open("xb") as stream:
            stream.truncate(96 * 1024 * 1024)
    assert padding.stat().st_size == 96 * 1024 * 1024
    movie = previous[0]["filename"]
    if args.resume:
        assert {path.name for path in output.iterdir()} == {movie}
        with (output / movie).open("rb") as stream:
            assert hashlib.file_digest(stream, "sha256").hexdigest() == previous[0]["sha256"]
    else:
        shutil.copyfile(source / movie, output / movie)
    television = previous[1]["filename"]
    command = [executable(), "run", "--rm", "--network", "none", "--cpus", "2", "--memory", "512m",
               "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true", "--entrypoint", "ffmpeg",
               "--mount", f"type=bind,src={source},dst=/source,readonly",
               "--mount", f"type=bind,src={padding},dst=/padding.bin,readonly",
               "--mount", f"type=bind,src={output},dst=/output", FFMPEG,
               "-hide_banner", "-nostdin", "-n", "-i", "/source/" + television, "-c", "copy",
               "-attach", "/padding.bin", "-metadata:s:t", "mimetype=application/octet-stream",
               "/output/" + television]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=90,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    (root / "generation.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    assert result.returncode == 0
    files = [("movie", movie, 7200)]
    for episode in range(1, 7):
        name = television.replace("S01E01", f"S01E{episode:02d}")
        if episode > 1:
            shutil.copyfile(output / television, output / name)
        files.append(("tv", name, 1800))
    fixtures = []
    for index, (kind, name, duration) in enumerate(files):
        path = output / name
        info_hash, data = torrent(path, "http://fixture-source:8080/announce")
        (output / f"{index}.torrent").write_bytes(data)
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        fixtures.append({"id": index, "kind": kind, "release": name.removesuffix(".mkv"), "filename": name,
                         "duration": duration, "hash": info_hash, "sha256": digest, "size": path.stat().st_size})
    (output / "fixtures.json").write_text(json.dumps(fixtures, indent=2))
    (root / "generation.json").write_text(json.dumps({"original_bars_and_silence": True, "ffmpeg": FFMPEG,
        "tv_attachment_bytes": padding.stat().st_size, "existing_quality_settings_unchanged": True,
        "scope": "Original movie and six episode stand-ins; named works are not included."}, indent=2))
    print("Created one original movie and six episode fixtures; existing quality settings stay unchanged.")


if __name__ == "__main__":
    main()
