#!/home/user/.openclaw/workspace/tools/media-pipeline/.venv/bin/python
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


def run(cmd):
    return subprocess.run(cmd, check=True, text=True, capture_output=True)


def main():
    p = argparse.ArgumentParser(description='Fetch media from URL to local file via yt-dlp')
    p.add_argument('url')
    p.add_argument('--output-dir', default=None)
    p.add_argument('--print-json', action='store_true')
    args = p.parse_args()

    if not shutil.which('yt-dlp'):
        print('Error: yt-dlp not found', file=sys.stderr)
        sys.exit(1)

    out_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else Path.cwd() / 'downloaded-media'
    out_dir.mkdir(parents=True, exist_ok=True)
    out_tpl = str(out_dir / '%(title)s---%(id)s.%(ext)s')

    cmd = [
        'yt-dlp',
        '--no-playlist',
        '-o', out_tpl,
        args.url,
    ]
    res = run(cmd)

    info_cmd = ['yt-dlp', '--dump-json', '--no-warnings', '--no-playlist', args.url]
    info = json.loads(run(info_cmd).stdout)
    expected = out_dir / f"{info.get('title','media')}---{info.get('id','unknown')}.{info.get('ext','mp4')}"

    payload = {
        'url': args.url,
        'title': info.get('title'),
        'id': info.get('id'),
        'ext': info.get('ext'),
        'path': str(expected),
        'exists': expected.exists(),
    }
    if args.print_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(str(expected))


if __name__ == '__main__':
    main()
