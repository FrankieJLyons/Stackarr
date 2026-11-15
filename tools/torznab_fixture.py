"""Local Torznab and tracker fixture serving only generated test releases."""

import argparse
import hashlib
import json
import socket
import struct
import time
import xml.etree.ElementTree as ET
from email.utils import formatdate
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

FFMPEG = "lscr.io/linuxserver/ffmpeg@sha256:1f9755c920d41b30c4630eb6d54ac4d9badc4f5b0ca3e7f495a98d00e8020c3a"
NS = "http://torznab.com/schemas/2015/feed"
ET.register_namespace("torznab", NS)


def bencode(value):
    if isinstance(value, bytes):
        return str(len(value)).encode() + b":" + value
    if isinstance(value, str):
        return bencode(value.encode())
    if isinstance(value, int):
        return b"i" + str(value).encode() + b"e"
    if isinstance(value, list):
        return b"l" + b"".join(bencode(item) for item in value) + b"e"
    return b"d" + b"".join(bencode(key) + bencode(value[key]) for key in sorted(value)) + b"e"


def torrent(path, announce):
    piece_length = 16384
    pieces = []
    with path.open("rb") as source:
        while data := source.read(piece_length):
            pieces.append(hashlib.sha1(data).digest())
    info = {"length": path.stat().st_size, "name": path.name, "piece length": piece_length,
            "pieces": b"".join(pieces), "private": 1}
    raw = bencode(info)
    return hashlib.sha1(raw).hexdigest(), bencode({"announce": announce, "info": info,
        "comment": "Original generated colour fixture; not the film or episode named by test metadata."})


def attributes(row):
    """Allow multi-title/resolution labs while retaining the original two fixtures."""
    result = {"category": str(row.get("category", "2040" if row["kind"] == "movie" else "5040")),
              "seeders": "1", "peers": "1", "size": str(row["size"]), "infohash": row["hash"],
              "downloadvolumefactor": "0", "uploadvolumefactor": "1"}
    defaults = {"imdb": "0063350", "tmdbid": "10331"} if row["kind"] == "movie" else {"tvdbid": "73244"}
    result.update({key: str(value) for key, value in row.get("identities", defaults).items()})
    return result


def matching(manifest, kind, query):
    selected = []
    for row in manifest:
        if kind == "movie" and row["kind"] != "movie" or kind == "tvsearch" and row["kind"] != "tv":
            continue
        identity = attributes(row)
        if any(query.get(param) and query[param][0].removeprefix("tt") != identity.get(key, "").removeprefix("tt")
               for param, key in (("imdbid", "imdb"), ("tmdbid", "tmdbid"), ("tvdbid", "tvdbid"))):
            continue
        if any(query.get(param) and field in row and str(row[field]) != query[param][0]
               for param, field in (("season", "season"), ("ep", "episode"))):
            continue
        selected.append(row)
    return selected


def serve(directory, host, port, public_url, events_path=None, seeder_host="fixture-seeder"):
    manifest = json.loads((directory / "fixtures.json").read_text())
    events = events_path or directory / "events.jsonl"

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass  # Never record provider keys or tracker query strings.

        def reply(self, data, kind="text/xml"):
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            parsed = urlsplit(self.path)
            query = parse_qs(parsed.query, encoding="latin-1")
            kind = query.get("t", [""])[0]
            with events.open("a") as output:
                output.write(json.dumps({"route": parsed.path, "kind": kind, "time": time.time()}) + "\n")
            if parsed.path == "/health":
                return self.reply(b"ready", "text/plain")
            if parsed.path == "/announce":
                info_hash = query.get("info_hash", [""])[0].encode("latin-1").hex()
                if info_hash not in {row["hash"] for row in manifest}:
                    return self.reply(bencode({"failure reason": "Only this fixture's private torrents are supported."}), "text/plain")
                # The torrent is private, and its only peer is this isolated Docker seeder.
                address = socket.gethostbyname(seeder_host)
                peers = socket.inet_aton(address) + struct.pack("!H", 6881)
                return self.reply(bencode({"interval": 5, "min interval": 2, "complete": 1,
                                          "incomplete": 1, "peers": peers}), "text/plain")
            if parsed.path.startswith("/torrent/"):
                number = parsed.path.removeprefix("/torrent/").removesuffix(".torrent")
                if not number.isdigit() or int(number) >= len(manifest):
                    self.send_error(404)
                    return
                return self.reply((directory / (number + ".torrent")).read_bytes(), "application/x-bittorrent")
            if parsed.path != "/api":
                self.send_error(404)
                return
            expected = (directory / "fixture-key").read_text().strip()
            if query.get("apikey", [""])[0] != expected:
                self.send_error(403)
                return
            if kind == "caps":
                root = ET.Element("caps")
                ET.SubElement(root, "server", {"title": "Stackarr local original-media fixture"})
                ET.SubElement(root, "limits", {"default": "100", "max": "100"})
                searching = ET.SubElement(root, "searching")
                for name, parameters in (("search", "q"), ("movie-search", "q,imdbid,tmdbid"),
                                         ("tv-search", "q,tvdbid,season,ep")):
                    ET.SubElement(searching, name, {"available": "yes", "supportedParams": parameters})
                categories = ET.SubElement(root, "categories")
                for number, name, subs in (("2000", "Movies", (("2030", "SD"), ("2040", "HD"), ("2045", "UHD"))),
                                           ("5000", "TV", (("5030", "SD"), ("5040", "HD"), ("5045", "UHD")))):
                    category = ET.SubElement(categories, "category", {"id": number, "name": name})
                    for sub, quality in subs:
                        ET.SubElement(category, "subcat", {"id": sub, "name": name + "/" + quality})
                return self.reply(ET.tostring(root, encoding="utf-8", xml_declaration=True))
            root = ET.Element("rss", {"version": "2.0"})
            channel = ET.SubElement(root, "channel")
            ET.SubElement(channel, "title").text = "Stackarr original test releases"
            ET.SubElement(channel, "link").text = public_url
            selected = matching(manifest, kind, query)
            ET.SubElement(channel, "{" + NS + "}response", {"offset": "0", "total": str(len(selected))})
            for row in selected:
                item = ET.SubElement(channel, "item")
                ET.SubElement(item, "title").text = row["release"]
                ET.SubElement(item, "guid", {"isPermaLink": "false"}).text = "stackarr-original-" + row["hash"]
                link = public_url + "/torrent/" + str(row["id"]) + ".torrent"
                ET.SubElement(item, "link").text = link
                ET.SubElement(item, "pubDate").text = formatdate(time.time() - 60, usegmt=True)
                ET.SubElement(item, "description").text = "Original colour-bar media, using known metadata solely for an isolated import test."
                ET.SubElement(item, "size").text = str(row["size"])
                ET.SubElement(item, "enclosure", {"url": link, "length": str(row["size"]), "type": "application/x-bittorrent"})
                for name, value in attributes(row).items():
                    ET.SubElement(item, "{" + NS + "}attr", {"name": name, "value": value})
            self.reply(ET.tostring(root, encoding="utf-8", xml_declaration=True))

    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--public-url", required=True)
    parser.add_argument("--events", type=Path)
    parser.add_argument("--seeder-host", default="fixture-seeder")
    args = parser.parse_args()
    serve(args.directory, args.host, args.port, args.public_url, args.events, args.seeder_host)
