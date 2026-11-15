"""Generate original SDR quality variants for receipt-isolated download tests."""

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path

from stackarr.docker_runtime import executable
from tools.torznab_fixture import FFMPEG, torrent

SIZES = {'SD': (854, 480, '480p'), '1080p': (1920, 1080, '1080p'), '4K': (3840, 2160, '2160p')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('cases', type=Path, help='Verified metadata records; no media is fetched from a provider')
    parser.add_argument('output', type=Path)
    parser.add_argument('--tracker', required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    assert output.is_relative_to(Path('test-results').resolve()) and not output.exists()
    output.mkdir(parents=True)
    cases = json.loads(args.cases.read_text())
    assert len(cases) == 6 and {row['kind'] for row in cases} == {'movie', 'tv'}

    def ffmpeg(arguments):
        result = subprocess.run([executable(), 'run', '--rm', '--network', 'none', '--cpus', '2',
            '--memory', '768m', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true',
            '--mount', 'type=bind,source=' + str(output) + ',target=/output', '--entrypoint', 'ffmpeg', FFMPEG,
            '-hide_banner', '-nostdin', '-nostats', '-loglevel', 'error', '-n', *arguments],
            capture_output=True, text=True, encoding='utf-8', timeout=240,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        with (output / 'generation.log').open('a', encoding='utf-8') as log:
            log.write(result.stdout + result.stderr)
        assert result.returncode == 0, 'Original-media generation failed; inspect the local generation log.'

    for tier, (width, height, _) in SIZES.items():
        ffmpeg(['-f', 'lavfi', '-i', f'smptebars=size={width}x{height}:rate=24', '-f', 'lavfi', '-i',
                'anullsrc=channel_layout=stereo:sample_rate=48000', '-t', '12', '-c:v', 'libx264',
                '-threads', '2', '-preset', 'ultrafast', '-crf', '38', '-pix_fmt', 'yuv420p',
                '-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709',
                '-c:a', 'aac', '-b:a', '32k', '-movflags', '+faststart', '/output/master-' + tier + '.mp4'])
        for kind, duration in [('movie', 7200), ('tv', 1800)]:
            ffmpeg(['-stream_loop', '-1', '-i', '/output/master-' + tier + '.mp4', '-t', str(duration),
                    '-c', 'copy', '-metadata', 'title=Stackarr original quality test - colour bars and silence',
                    '/output/' + kind + '-' + tier + '.mkv'])
        print('Generated original ' + tier + ' variants.', flush=True)

    fixtures = []
    for case in cases:
        for tier, (width, height, label) in SIZES.items():
            release = case['release'] + '.' + label + '.WEB-DL.x264-StackarrQualityFixture'
            path = output / (release + '.mkv')
            os.link(output / (case['kind'] + '-' + tier + '.mkv'), path)
            digest, data = torrent(path, args.tracker)
            number = len(fixtures)
            (output / (str(number) + '.torrent')).write_bytes(data)
            with path.open('rb') as source:
                sha256 = hashlib.file_digest(source, 'sha256').hexdigest()
            fixtures.append({'id': number, 'kind': case['kind'], 'case': case['id'], 'tier': tier,
                'release': release, 'filename': path.name, 'hash': digest, 'sha256': sha256,
                'size': path.stat().st_size, 'width': width, 'height': height, 'frame_rate': 24,
                'identities': case['identities'],
                'category': ('20' if case['kind'] == 'movie' else '50') + {'SD': '30', '1080p': '40', '4K': '45'}[tier],
                **({'season': 1, 'episode': 1} if case['kind'] == 'tv' else {})})
    (output / 'fixtures.json').write_text(json.dumps(fixtures, indent=2))
    (output / 'generation.json').write_text(json.dumps({'image': FFMPEG, 'network': 'none', 'frame_rate': 24,
        'source': 'Original generated colour bars and silence, encoded at each actual resolution; SDR H.264/AAC.',
        'variants': len(fixtures), 'hardlinked_seed_copies': True}, indent=2))


if __name__ == '__main__':
    main()
