#!/home/user/.openclaw/workspace/tools/media-pipeline/.venv/bin/python
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


def run(cmd):
    return subprocess.run(cmd, check=True, text=True, capture_output=True)


def ffmpeg_subtitles_filter(path: Path) -> str:
    s = str(path.resolve())
    s = s.replace('\\', '/')
    s = s.replace(':', '\\:')
    s = s.replace("'", r"\'")
    s = s.replace(',', r'\,')
    s = s.replace('[', r'\[').replace(']', r'\]')
    return f"subtitles='{s}'"


def main():
    p = argparse.ArgumentParser(description='Compose a subtitle video using ffmpeg')
    p.add_argument('--video', required=True, help='Source video path')
    p.add_argument('--srt', required=True, help='Subtitle SRT path')
    p.add_argument('--output', required=True, help='Output video path')
    p.add_argument('--mode', choices=['burn', 'soft'], default='burn', help='Burn subtitles into video or mux as soft subtitles')
    p.add_argument('--overwrite', action='store_true')
    p.add_argument('--json-stdout', action='store_true')
    args = p.parse_args()

    if not shutil.which('ffmpeg'):
        print('Error: ffmpeg not found', file=sys.stderr)
        sys.exit(1)

    video = Path(args.video).expanduser().resolve()
    srt = Path(args.srt).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()

    if not video.exists():
        print(f'Error: video not found: {video}', file=sys.stderr)
        sys.exit(1)
    if not srt.exists():
        print(f'Error: subtitle not found: {srt}', file=sys.stderr)
        sys.exit(1)

    output.parent.mkdir(parents=True, exist_ok=True)

    cmd = ['ffmpeg', '-hide_banner', '-loglevel', 'error']
    if args.overwrite:
        cmd.append('-y')
    else:
        cmd.append('-n')

    if args.mode == 'burn':
        cmd += [
            '-i', str(video),
            '-vf', ffmpeg_subtitles_filter(srt),
            '-c:v', 'libx264',
            '-preset', 'medium',
            '-crf', '18',
            '-c:a', 'copy',
            str(output),
        ]
    else:
        cmd += [
            '-i', str(video),
            '-i', str(srt),
            '-map', '0:v:0',
            '-map', '0:a?',
            '-map', '1:0',
            '-c:v', 'copy',
            '-c:a', 'copy',
            '-c:s', 'mov_text',
            '-metadata:s:s:0', 'language=zho',
            '-metadata:s:s:0', 'title=Chinese',
            '-disposition:s:0', 'default',
            str(output),
        ]

    run(cmd)

    payload = {
        'video': str(video),
        'srt': str(srt),
        'output': str(output),
        'mode': args.mode,
        'exists': output.exists(),
    }
    if args.json_stdout:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(str(output))


if __name__ == '__main__':
    main()
