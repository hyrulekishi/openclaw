#!/home/user/.openclaw/workspace/tools/media-pipeline/.venv/bin/python
import argparse
import json
from pathlib import Path


def ts(x):
    if x is None:
        return None
    ms = round(float(x) * 1000)
    h = ms // 3600000
    ms %= 3600000
    m = ms // 60000
    ms %= 60000
    s = ms // 1000
    ms %= 1000
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def main():
    p = argparse.ArgumentParser(description='Emit text / bilingual / SRT outputs from translated segments')
    p.add_argument('--input', required=True, help='Translated JSON path')
    p.add_argument('--out-dir', required=True, help='Output directory')
    p.add_argument('--srt-mode', choices=['translated', 'bilingual'], default='translated')
    args = p.parse_args()

    inp = Path(args.input).expanduser().resolve()
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    obj = json.loads(inp.read_text(encoding='utf-8'))
    segs = obj.get('segments', [])

    translated_txt = []
    bilingual_txt = []
    srt_lines = []
    srt_index = 1

    for seg in segs:
        src = (seg.get('text') or '').strip()
        tgt = (seg.get('translation') or '').strip()
        if tgt:
            translated_txt.append(tgt)
        if src or tgt:
            bilingual_txt.extend([
                f"[{seg.get('id')}]",
                src,
                tgt,
                ''
            ])

        start = seg.get('start')
        end = seg.get('end')
        if start is not None and end is not None:
            if args.srt_mode == 'bilingual':
                text = '\n'.join([x for x in [src, tgt] if x])
            else:
                text = tgt or src
            if text:
                srt_lines.extend([
                    str(srt_index),
                    f"{ts(start)} --> {ts(end)}",
                    text,
                    ''
                ])
                srt_index += 1

    (out_dir / 'translated.txt').write_text('\n'.join(translated_txt).strip() + ('\n' if translated_txt else ''), encoding='utf-8')
    (out_dir / 'bilingual.txt').write_text('\n'.join(bilingual_txt).rstrip() + ('\n' if bilingual_txt else ''), encoding='utf-8')
    if srt_lines:
        (out_dir / 'subtitles.zh.srt').write_text('\n'.join(srt_lines), encoding='utf-8')

    summary = {
        'translated_txt': str(out_dir / 'translated.txt'),
        'bilingual_txt': str(out_dir / 'bilingual.txt'),
        'srt': str(out_dir / 'subtitles.zh.srt') if srt_lines else None,
        'segments': len(segs),
        'srt_mode': args.srt_mode,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
