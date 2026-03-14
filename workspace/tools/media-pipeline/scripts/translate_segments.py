#!/home/user/.openclaw/workspace/tools/media-pipeline/.venv/bin/python
import argparse
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path


def google_translate(text: str, source_lang: str, target_lang: str) -> str:
    sl = source_lang if source_lang and source_lang != 'auto' else 'auto'
    q = urllib.parse.urlencode({
        'client': 'gtx',
        'sl': sl,
        'tl': target_lang,
        'dt': 't',
        'q': text,
    })
    url = 'https://translate.googleapis.com/translate_a/single?' + q
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode('utf-8', errors='replace'))
    return ''.join(item[0] for item in data[0] if item and item[0]).strip()


def google_translate_retry(text: str, source_lang: str, target_lang: str, retries: int = 3) -> str:
    delays = [1, 2, 4]
    last_err = None
    for i in range(retries):
        try:
            return google_translate(text, source_lang, target_lang)
        except Exception as e:
            last_err = e
            if i < retries - 1:
                time.sleep(delays[i])
    raise last_err


def batched(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def translate_batch(texts, source_lang, target_lang, separator):
    joined = f"\n{separator}\n".join(texts)
    translated = google_translate_retry(joined, source_lang, target_lang)
    return [p.strip() for p in translated.split(separator)]


def load_partial(path: Path):
    if not path.exists():
        return {}
    try:
        obj = json.loads(path.read_text(encoding='utf-8'))
        return {
            str(s.get('id')): s.get('translation', '')
            for s in obj.get('segments', [])
            if s.get('id') is not None and s.get('translation')
        }
    except Exception:
        return {}


def save_partial(path: Path, source_type: str, source_lang: str, target_lang: str, has_timestamps: bool, segments: list):
    payload = {
        'source_type': source_type,
        'source_lang': source_lang,
        'target_lang': target_lang,
        'has_timestamps': has_timestamps,
        'segments': segments,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def lmstudio_refine_batch(batch, source_lang: str, target_lang: str):
    url = 'http://127.0.0.1:1235/v1/chat/completions'
    payload = {
        'model': 'qwen3.5-9B',
        'temperature': 0.2,
        'messages': [
            {
                'role': 'system',
                'content': (
                    'You are a subtitle translation refiner. '
                    'Keep segment count and order unchanged. '
                    'Do not add, remove, or invent information. '
                    'Rewrite the Chinese translations to sound natural, fluent, and human. '
                    'Avoid machine-translation phrasing, stiff wording, promotional tone, and repetitive patterns. '
                    'Keep names, titles, and key terms accurate and consistent across context. '
                    'If a name is uncertain, preserve the original form rather than guessing. '
                    'Prefer plain, natural Chinese over literal translation. '
                    'Return JSON array only, one refined Chinese string per input segment.'
                )
            },
            {
                'role': 'user',
                'content': json.dumps({
                    'source_lang': source_lang,
                    'target_lang': target_lang,
                    'segments': [
                        {'id': s.get('id'), 'text': s.get('text', ''), 'translation': s.get('translation', '')}
                        for s in batch
                    ]
                }, ensure_ascii=False)
            }
        ]
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.loads(r.read().decode('utf-8', errors='replace'))
    content = data['choices'][0]['message']['content'].strip()
    if content.startswith('```'):
        content = content.strip('`')
        if content.startswith('json'):
            content = content[4:].strip()
    arr = json.loads(content)
    if not isinstance(arr, list) or len(arr) != len(batch):
        raise ValueError('refine output invalid')
    return [str(x).strip() for x in arr]


def main():
    p = argparse.ArgumentParser(description='Translate normalized segments')
    p.add_argument('--input', required=True, help='Normalized JSON path')
    p.add_argument('--output', required=True, help='Translated JSON path')
    p.add_argument('--source-lang', default='auto')
    p.add_argument('--target-lang', required=True)
    p.add_argument('--chunk-size', type=int, default=20)
    p.add_argument('--context-window', type=int, default=2)
    p.add_argument('--sleep-ms', type=int, default=300)
    p.add_argument('--refine', action='store_true', help='Run local qwen second-pass refinement')
    p.add_argument('--json-stdout', action='store_true')
    args = p.parse_args()

    inp = Path(args.input).expanduser().resolve()
    out = Path(args.output).expanduser().resolve()
    partial_path = out.with_suffix('.partial.json')

    obj = json.loads(inp.read_text(encoding='utf-8'))
    segs = obj.get('segments', [])
    source_type = obj.get('source_type')
    source_lang = args.source_lang if args.source_lang != 'auto' else obj.get('language', 'auto')
    has_timestamps = obj.get('has_timestamps', False)

    partial_map = load_partial(partial_path)
    translated = []
    separator = '<<<SEG_BREAK_7f3c2a>>>'

    for chunk in batched(segs, args.chunk_size):
        pending = []
        pending_texts = []
        for seg in chunk:
            sid = str(seg.get('id'))
            if sid in partial_map and partial_map[sid]:
                item = dict(seg)
                item['translation'] = partial_map[sid]
                translated.append(item)
            else:
                pending.append(seg)
                pending_texts.append((seg.get('text') or '').strip())

        if pending:
            batch_parts = []
            if any(pending_texts):
                try:
                    batch_parts = translate_batch(pending_texts, source_lang, args.target_lang, separator)
                except Exception:
                    batch_parts = []

            if len(batch_parts) != len(pending_texts):
                batch_parts = []
                for text in pending_texts:
                    if not text:
                        batch_parts.append('')
                    else:
                        batch_parts.append(google_translate_retry(text, source_lang, args.target_lang))
                        if args.sleep_ms:
                            time.sleep(args.sleep_ms / 1000.0)

            for seg, t in zip(pending, batch_parts):
                item = dict(seg)
                item['translation'] = t.strip()
                translated.append(item)
                partial_map[str(seg.get('id'))] = item['translation']

            save_partial(partial_path, source_type, source_lang, args.target_lang, has_timestamps, translated)

        if args.sleep_ms:
            time.sleep(args.sleep_ms / 1000.0)

    translated.sort(key=lambda x: x.get('id', 0))

    refine_applied = False
    if args.refine and translated:
        refined = []
        changed_count = 0
        refine_chunk = max(1, min(args.chunk_size, 12))
        for chunk in batched(translated, refine_chunk):
            try:
                refined_texts = lmstudio_refine_batch(chunk, source_lang, args.target_lang)
                local_changes = 0
                for seg, rt in zip(chunk, refined_texts):
                    item = dict(seg)
                    new_text = rt.strip() or (seg.get('translation') or '')
                    item['translation'] = new_text
                    if new_text != (seg.get('translation') or ''):
                        local_changes += 1
                    refined.append(item)
                changed_count += local_changes
            except Exception:
                refined.extend(chunk)
        if changed_count > 0:
            translated = refined
            refine_applied = True
            save_partial(partial_path, source_type, source_lang, args.target_lang, has_timestamps, translated)

    result = {
        'source_type': source_type,
        'source_lang': source_lang,
        'target_lang': args.target_lang,
        'has_timestamps': has_timestamps,
        'refine_requested': args.refine,
        'refine_applied': refine_applied,
        'segments': translated,
    }

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    save_partial(partial_path, source_type, source_lang, args.target_lang, has_timestamps, translated)

    if args.json_stdout:
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
