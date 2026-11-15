"""Generate original AV1/HEVC/HDR playback samples in a fresh test-results folder."""

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path

from stackarr.docker_runtime import executable
from tools.torznab_fixture import FFMPEG

CASES = (
    ('hevc-1080p-sdr', 1920, 1080, 8, False),
    ('hevc-1080p-sdr10', 1920, 1080, 10, False),
    ('hevc-4k-sdr', 3840, 2160, 8, False),
    ('hevc-4k-sdr10', 3840, 2160, 10, False),
    ('hevc-1080p-hdr10', 1920, 1080, 10, True),
    ('hevc-4k-hdr10', 3840, 2160, 10, True),
    ('hevc-1080p-hlg', 1920, 1080, 10, True),
    ('hevc-4k-hlg', 3840, 2160, 10, True),
    ('av1-1080p-sdr', 1920, 1080, 8, False),
    ('av1-1080p-sdr10', 1920, 1080, 10, False),
    ('av1-4k-sdr', 3840, 2160, 8, False),
    ('av1-4k-sdr10', 3840, 2160, 10, False),
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--case', action='append', choices=[row[0] for row in CASES], dest='cases')
    parser.add_argument('--pattern', choices=['testsrc2', 'smptebars'], default='testsrc2',
                        help='Moving playback pattern, or small static bars for long import fixtures')
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(Path('test-results').resolve()) or output.exists():
        parser.error('Use a new folder inside test-results.')
    output.mkdir(parents=True)

    def run(program, arguments):
        result = subprocess.run([executable(), 'run', '--rm', '--network', 'none', '--cpus', '2',
            '--memory', '2048m', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true',
            '--mount', 'type=bind,source=' + str(output) + ',target=/output', '--entrypoint', program,
            FFMPEG, *arguments], capture_output=True, text=True, encoding='utf-8', timeout=600,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        with (output / 'generation.log').open('a', encoding='utf-8') as log:
            log.write(result.stderr)
        if result.returncode:
            raise RuntimeError(f'Sample generation exited {result.returncode}; see generation.log.')
        return result.stdout

    manifest = []
    for name, width, height, depth, hdr in CASES:
        if args.cases and name not in args.cases:
            continue
        pix_fmt = 'yuv420p10le' if depth == 10 else 'yuv420p'
        codec = 'av1' if name.startswith('av1-') else 'hevc'
        tag = 'av01' if codec == 'av1' else 'hvc1'
        hlg = name.endswith('-hlg')
        transfer = 'arib-std-b67' if hlg else 'smpte2084' if hdr else 'bt709'
        # Convert the pixels, not just their tags: decode BT.709 into linear
        # light, increase peak luminance from 100 to 1000 nits, then encode PQ or HLG
        # in a BT.2020 container. The synthetic pattern is not a calibrated TV.
        filters = ('zscale=pin=bt709:tin=bt709:min=bt709:rin=limited:p=bt709:t=linear:m=gbr:r=full:npl=100,'
            'format=gbrpf32le,'
            f'zscale=pin=bt709:tin=linear:min=gbr:rin=full:p=bt2020:t={transfer}:m=bt2020nc:r=limited:npl=1000,'
            'format=yuv420p10le'
            if hdr else 'format=' + pix_fmt)
        params = 'pools=2:frame-threads=1:log-level=error:keyint=48:min-keyint=48:scenecut=0:rc-lookahead=0:bframes=0'
        params += (f':colorprim=bt2020:transfer={transfer}:colormatrix=bt2020nc'
            if hdr else ':colorprim=bt709:transfer=bt709:colormatrix=bt709')
        if hdr and not hlg:
            # BT.2020 mastering primaries; 0.0001–1000 nit mastering range.
            params += (':hdr10=1:hdr10-opt=1:repeat-headers=1:'
                'master-display=G(8500,39850)B(6550,2300)R(35400,14600)WP(15635,16450)L(10000000,1)'
                ':max-cll=1000,1000')
        common = ['-hide_banner', '-nostdin', '-nostats', '-loglevel', 'error', '-n']
        encoder = (['-c:v', 'libsvtav1', '-preset', '9', '-crf', '38', '-g', '48',
                    '-svtav1-params', 'lp=2:lookahead=0:color-primaries=1:transfer-characteristics=1:matrix-coefficients=1:color-range=0'] if codec == 'av1' else
                   ['-c:v', 'libx265', '-preset', 'ultrafast', '-crf', '28', '-x265-params', params])
        run('ffmpeg', [*common, '-f', 'lavfi', '-i', f'{args.pattern}=size={width}x{height}:rate=24',
            '-t', '4', '-filter_threads', '1', '-vf', filters, '-threads', '2',
            *encoder, '-pix_fmt', pix_fmt,
            '-color_primaries', 'bt2020' if hdr else 'bt709',
            '-color_trc', transfer,
            '-colorspace', 'bt2020nc' if hdr else 'bt709', '-color_range', 'tv',
            '-an', '-tag:v', tag, '-movflags', '+faststart',
            '/output/master-' + name + '.mp4'])
        filename = 'Stackarr ' + name + '.mp4'
        run('ffmpeg', [*common, '-stream_loop', '-1', '-i', '/output/master-' + name + '.mp4',
            '-f', 'lavfi', '-i', 'anullsrc=channel_layout=stereo:sample_rate=48000',
            '-t', '120', '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '32k',
            '-tag:v', tag, '-movflags', '+faststart',
            '-metadata', 'title=Stackarr original ' + name + ' ' + args.pattern + ' test pattern',
            '/output/' + filename])
        probe = json.loads(run('ffprobe', ['-v', 'error', '-show_streams', '-show_format',
            '-show_frames', '-select_streams', 'v:0', '-read_intervals', '%+#8', '-of', 'json', '/output/' + filename]))
        video = next(row for row in probe['streams'] if row['codec_type'] == 'video')
        assert video['codec_name'] == codec and (video['width'], video['height']) == (width, height)
        assert video['pix_fmt'] == pix_fmt and video['color_transfer'] == transfer
        assert video['color_primaries'] == ('bt2020' if hdr else 'bt709')
        side_data = probe['frames'][0].get('side_data_list', [])
        if hdr and not hlg:
            assert any(row['side_data_type'] == 'Mastering display metadata' for row in side_data)
            assert any(row['side_data_type'] == 'Content light level metadata' for row in side_data)
        path = output / filename
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        manifest.append({'id': name, 'filename': filename, 'width': width, 'height': height,
            'video_codec': codec, 'bit_depth': depth, 'hdr10': hdr and not hlg, 'hlg': hlg, 'sha256': digest, 'size': path.stat().st_size,
            'probe': probe})
        (output / 'manifest.json').write_text(json.dumps(manifest, indent=2))
        print('Generated and probed ' + name, flush=True)
    (output / 'generation.json').write_text(json.dumps({'image': FFMPEG, 'network': 'none',
        'fps': 24, 'encoded_seconds': 4, 'looped_seconds': 120,
        'source': 'Original FFmpeg ' + args.pattern + ' test patterns with silent AAC audio.',
        'hdr': 'Pixel-converted BT.2020/PQ HDR10 with static metadata, or BT.2020/HLG, Main 10, 1000 nit reference.',
        'scope': 'Short synthetic compatibility samples; not sustained feature-film or HDR display calibration.'},
        indent=2))


if __name__ == '__main__':
    main()
