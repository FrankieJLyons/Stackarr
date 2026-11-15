"""Generate original import-test media in an isolated FFmpeg container."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from stackarr.docker_runtime import executable
from tools.torznab_fixture import FFMPEG, torrent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lab", type=Path)
    args = parser.parse_args()
    root = args.lab.resolve()
    assert root.is_relative_to(Path("test-results").resolve()) and root.name.startswith("docker-core-")
    directory = root / "seed-media"
    directory.mkdir()
    fixtures = []
    for number, kind, release, duration in (
        (0, "movie", "Night.of.the.Living.Dead.1968.720p.WEB-DL.x264-StackarrFixture", 7200),
        (1, "tv", "The.Office.US.S01E01.720p.WEB-DL.x264-StackarrFixture", 1800),
    ):
        name = release + ".mkv"
        result = subprocess.run([executable(), "run", "--rm", "--network", "none", "--cpus", "2", "--memory", "512m",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
            "--mount", "type=bind,source=" + str(directory) + ",target=/output", FFMPEG,
            "-hide_banner", "-nostats", "-loglevel", "error", "-n", "-f", "lavfi", "-i", "smptebars=size=1280x720:rate=1",
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000", "-t", str(duration),
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "38", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "32k", "-metadata", "title=Stackarr original colour bars and silence",
            "/output/" + name], capture_output=True, text=True, timeout=240)
        (directory / (str(number) + ".generation.log")).write_text(result.stdout + result.stderr)
        assert result.returncode == 0
        path = directory / name
        info_hash, content = torrent(path, "http://fixture-source:8080/announce")
        with (directory / (str(number) + ".torrent")).open("xb") as output:
            output.write(content)
        with path.open("rb") as source:
            digest = hashlib.file_digest(source, "sha256").hexdigest()
        fixtures.append({"id": number, "kind": kind, "release": release, "filename": name, "duration": duration,
                         "hash": info_hash, "sha256": digest, "size": path.stat().st_size})
        print("Generated original " + kind + " fixture (" + str(path.stat().st_size) + " bytes).", flush=True)
    (directory / "fixtures.json").write_text(json.dumps(fixtures, indent=2))
    (directory / "generation.json").write_text(json.dumps({"image": FFMPEG, "network": "none",
        "scope": "Original colour bars and silence; known media names are metadata stand-ins only"}, indent=2))


if __name__ == "__main__":
    main()
