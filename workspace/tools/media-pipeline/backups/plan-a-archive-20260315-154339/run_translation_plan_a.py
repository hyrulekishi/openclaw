#!/home/user/.openclaw/workspace/tools/media-pipeline/.venv/bin/python
import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
VENV_PYTHON = PROJECT_ROOT / '.venv' / 'bin' / 'python'
NORMALIZE = ROOT / 'normalize_input.py'
TRANSLATE = ROOT / 'translate_segments_plan_a.py'
EMIT = ROOT / 'emit_outputs.py'


def run(cmd):
    return subprocess.run(cmd, check=True, text=True)


def default_out_dir(input_value: str, is_url: bool) -> Path:
    if is_url:
        return (Path.cwd() / 'output' / 'translation-run-plan-a').resolve()
    return Path(input_value).expanduser().resolve().parent


def main():
    p = argparse.ArgumentParser(description='Unified normalize -> translate -> emit pipeline (plan A)')
    p.add_argument('--input', required=True)
    p.add_argument('--type', choices=['auto', 'text', 'transcript', 'json', 'web', 'pdf', 'docx', 'ocr'], default='auto')
    p.add_argument('--out-dir', default=None)
    p.add_argument('--source-lang', default='auto')
    p.add_argument('--target-lang', required=True)
    p.add_argument('--chunk-size', type=int, default=20)
    p.add_argument('--context-window', type=int, default=2)
    p.add_argument('--sleep-ms', type=int, default=300)
    p.add_argument('--translate-max-chars', type=int, default=1500)
    p.add_argument('--translate-retries', type=int, default=2)
    p.add_argument('--refine', dest='refine', action='store_true', default=True)
    p.add_argument('--no-refine', dest='refine', action='store_false')
    p.add_argument('--refine-base-url', default='http://127.0.0.1:1235')
    p.add_argument('--refine-chunk-size', type=int, default=8)
    p.add_argument('--refine-max-chars', type=int, default=2200)
    p.add_argument('--refine-retries', type=int, default=2)
    p.add_argument('--refine-ready-timeout', type=float, default=10.0)
    p.add_argument('--refine-timeout', type=float, default=40.0)
    p.add_argument('--refine-strict', action='store_true')
    p.add_argument('--srt-mode', choices=['translated', 'bilingual'], default='translated')
    p.add_argument('--debug', action='store_true')
    args = p.parse_args()

    is_url = args.input.startswith('http://') or args.input.startswith('https://')
    out_dir = Path(args.out_dir).expanduser().resolve() if args.out_dir else default_out_dir(args.input, is_url)
    out_dir.mkdir(parents=True, exist_ok=True)
    translated_path = out_dir / 'translated.json'

    temp_path = None
    if args.debug:
        normalized_path = out_dir / 'normalized.json'
    else:
        fd, tmp_name = tempfile.mkstemp(prefix='normalized-', suffix='.json', dir=str(out_dir))
        os.close(fd)
        normalized_path = Path(tmp_name)
        temp_path = normalized_path

    try:
        python_bin = str(VENV_PYTHON if VENV_PYTHON.exists() else Path(sys.executable).resolve())
        run([python_bin, str(NORMALIZE), '--input', args.input, '--type', args.type, '--output', str(normalized_path)])
        translate_cmd = [
            python_bin, str(TRANSLATE),
            '--input', str(normalized_path),
            '--output', str(translated_path),
            '--source-lang', args.source_lang,
            '--target-lang', args.target_lang,
            '--chunk-size', str(args.chunk_size),
            '--context-window', str(args.context_window),
            '--sleep-ms', str(args.sleep_ms),
            '--translate-max-chars', str(args.translate_max_chars),
            '--translate-retries', str(args.translate_retries),
        ]
        if args.refine:
            translate_cmd.extend([
                '--refine',
                '--refine-base-url', args.refine_base_url,
                '--refine-chunk-size', str(args.refine_chunk_size),
                '--refine-max-chars', str(args.refine_max_chars),
                '--refine-retries', str(args.refine_retries),
                '--refine-ready-timeout', str(args.refine_ready_timeout),
                '--refine-timeout', str(args.refine_timeout),
            ])
            if args.refine_strict:
                translate_cmd.append('--refine-strict')
        if args.debug:
            translate_cmd.append('--debug')
        run(translate_cmd)
        emit_cmd = [python_bin, str(EMIT), '--input', str(translated_path), '--out-dir', str(out_dir), '--srt-mode', args.srt_mode]
        if args.debug:
            emit_cmd.append('--debug')
        run(emit_cmd)
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass


if __name__ == '__main__':
    main()
