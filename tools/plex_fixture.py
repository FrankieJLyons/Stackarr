"""Create an original five-second color-bar AVI for an isolated Plex library."""

import argparse
import struct
from pathlib import Path


def write_sample(path):
    width, height, rate, frames = 160, 90, 10, 50
    frame_size = width * height * 3

    def chunk(name, content):
        return name + struct.pack("<I", len(content)) + content + (b"\0" if len(content) % 2 else b"")

    def listing(name, content):
        return chunk(b"LIST", name + content)

    header = struct.pack("<14I", 1_000_000 // rate, frame_size * rate, 0, 0x10,
                         frames, 0, 1, frame_size, width, height, 0, 0, 0, 0)
    stream = struct.pack("<4s4sIHH8I4h", b"vids", b"DIB ", 0, 0, 0,
                         0, 1, rate, 0, frames, frame_size, 0xFFFFFFFF, 0, 0, 0, width, height)
    bitmap = struct.pack("<IiiHHIIiiII", 40, width, height, 1, 24, 0, frame_size, 0, 0, 0, 0)
    headers = listing(b"hdrl", chunk(b"avih", header) + listing(b"strl", chunk(b"strh", stream) + chunk(b"strf", bitmap)))
    pictures, index, offset = [], [], 4
    colors = ((255, 255, 255), (0, 255, 255), (255, 255, 0), (0, 255, 0),
              (255, 0, 255), (0, 0, 255), (255, 0, 0), (32, 32, 32))
    for frame in range(frames):
        row = b"".join(bytes((255, 255, 255) if x == frame * 3 % width else colors[x // 20]) for x in range(width))
        picture = chunk(b"00db", row * height)
        pictures.append(picture)
        index.append(struct.pack("<4sIII", b"00db", 0x10, offset, frame_size))
        offset += len(picture)
    content = b"AVI " + headers + listing(b"movi", b"".join(pictures)) + chunk(b"idx1", b"".join(index))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as output:
        output.write(b"RIFF" + struct.pack("<I", len(content)) + content)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    write_sample(parser.parse_args().output)
