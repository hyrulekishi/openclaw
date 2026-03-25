#!/home/user/.openclaw/workspace/tools/media-pipeline/.venv/bin/python
import argparse
import json
import re
import socket
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path


def google_translate(text: str, source_lang: str, target_lang: str) -> str:
    sl = source_lang if source_lang and source_lang != 'auto' else 'auto'
    q = urllib.parse.urlencode({'client': 'gtx', 'sl': sl, 'tl': target_lang, 'dt': 't', 'q': text})
    url = 'https://translate.googleapis.com/translate_a/single?' + q
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode('utf-8', errors='replace'))
    return ''.join(item[0] for item in data[0] if item and item[0]).strip()


def google_translate_retry(text: str, source_lang: str, target_lang: str, retries: int = 2) -> str:
    delays = [1, 2, 4]
    last_err = None
    for i in range(max(1, retries)):
        try:
            return google_translate(text, source_lang, target_lang)
        except Exception as e:
            last_err = e
            if i < max(1, retries) - 1:
                time.sleep(delays[min(i, len(delays) - 1)])
    raise last_err


def batched_by_chars(segs, max_chars):
    max_chars = max(1, max_chars)
    chunk = []
    current_chars = 0
    for seg in segs:
        text = (seg.get('text') or '').strip()
        seg_chars = len(text)
        if chunk and current_chars + seg_chars > max_chars:
            yield chunk
            chunk = []
            current_chars = 0
        chunk.append(seg)
        current_chars += seg_chars
    if chunk:
        yield chunk


def batched_for_refine(segs, max_chars):
    max_chars = max(1, max_chars)
    chunk = []
    current_chars = 0
    for seg in segs:
        seg_chars = len((seg.get('text') or '').strip()) + len((seg.get('translation') or '').strip())
        if chunk and current_chars + seg_chars > max_chars:
            yield chunk
            chunk = []
            current_chars = 0
        chunk.append(seg)
        current_chars += seg_chars
    if chunk:
        yield chunk


def translate_batch(texts, source_lang, target_lang, separator, retries=2):
    joined = f"\n{separator}\n".join(texts)
    translated = google_translate_retry(joined, source_lang, target_lang, retries=retries)
    return [p.strip() for p in translated.split(separator)]


def load_partial(path: Path):
    if not path.exists():
        return {}
    try:
        obj = json.loads(path.read_text(encoding='utf-8'))
        return {str(s.get('id')): s.get('translation', '') for s in obj.get('segments', []) if s.get('id') is not None and s.get('translation')}
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


def cleanup_file(path: Path):
    try:
        if path.exists():
            path.unlink()
    except Exception:
        pass


def wait_for_lmstudio(base_url: str, ready_timeout: float = 10.0, probe_timeout: float = 2.0):
    parsed = urllib.parse.urlparse(base_url)
    host = parsed.hostname or '127.0.0.1'
    port = parsed.port or 80
    deadline = time.time() + ready_timeout
    last_err = None
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=probe_timeout):
                return True
        except Exception as e:
            last_err = e
            time.sleep(0.5)
    raise TimeoutError(f'LM Studio not ready within {ready_timeout:.0f}s: {last_err}')


def is_noisy_segment(text: str, translation: str) -> bool:
    text = (text or '').strip()
    translation = (translation or '').strip()
    merged = text + translation
    if not merged:
        return False
    punct_like = set('~～…!！?？♡❤♥🖤「」『』【】（）()')
    punct_ratio = sum(1 for ch in merged if ch in punct_like) / max(1, len(merged))
    max_run = 1
    current_run = 1
    for i in range(1, len(merged)):
        if merged[i] == merged[i - 1]:
            current_run += 1
            max_run = max(max_run, current_run)
        else:
            current_run = 1
    repeated_char_ratio = len(translation) / max(1, len(text)) if text else 1.0
    return punct_ratio > 0.18 or max_run >= 8 or (len(text) <= 60 and len(translation) >= 220) or (repeated_char_ratio >= 5.0 and len(translation) >= 180)


def lmstudio_refine_batch(batch, base_url: str, request_timeout: float):
    url = base_url.rstrip('/') + '/v1/chat/completions'
    payload = {
        'model': 'qwen3.5-9B',
        'temperature': 0.15,
        'messages': [
            {
                'role': 'system',
                'content': (
                    'You are a Japanese-to-Chinese translation refiner for noisy extracted documents. '
                    'Keep segment count and order unchanged. '
                    'Do not add, remove, summarize, censor, or invent information. '
                    'Use the source text to correct mistranslations, restore proper reading order when the MT is awkward, '
                    'and eliminate leftover Japanese unless it is a name or unavoidable quoted term. '
                    'Normalize scream-like punctuation and decorative symbols into readable Chinese prose where possible. '
                    'Preserve names, scene logic, and explicit content faithfully. '
                    'Return exactly one line per input segment. '
                    'Each line must start with REFINE::<id>:: and then the final Chinese text. '
                    'Do not output JSON, numbering, notes, or extra lines.'
                )
            },
            {
                'role': 'user',
                'content': '\n'.join(
                    f"SEG::{s.get('id')}\\nSRC::{(s.get('text') or '').strip()}\\nMT::{(s.get('translation') or '').strip()}"
                    for s in batch
                )
            }
        ]
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=request_timeout) as r:
        data = json.loads(r.read().decode('utf-8', errors='replace'))
    content = data['choices'][0]['message']['content'].strip()
    if content.startswith('```'):
        lines = content.splitlines()
        if lines and lines[0].startswith('```'):
            lines = lines[1:]
        if lines and lines[-1].startswith('```'):
            lines = lines[:-1]
        content = '\n'.join(lines).strip()

    parsed = {}
    markers = list(re.finditer(r'REFINE::\s*(\d+)::', content))
    for i, match in enumerate(markers):
        seg_id = match.group(1).strip()
        start = match.end()
        end = markers[i + 1].start() if i + 1 < len(markers) else len(content)
        refined = content[start:end].strip()
        refined = re.split(r'REFINE::\s*\d+::', refined, maxsplit=1)[0].strip()
        refined = ' '.join(part.strip() for part in refined.splitlines() if part.strip())
        if refined:
            parsed[seg_id] = refined
    return parsed


def main():
    p = argparse.ArgumentParser(description='Translate normalized segments (plan B)')
    p.add_argument('--input', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--source-lang', default='auto')
    p.add_argument('--target-lang', required=True)
    p.add_argument('--chunk-size', type=int, default=20)
    p.add_argument('--context-window', type=int, default=2)
    p.add_argument('--sleep-ms', type=int, default=300)
    p.add_argument('--translate-max-chars', type=int, default=1200)
    p.add_argument('--translate-retries', type=int, default=2)
    p.add_argument('--refine', action='store_true')
    p.add_argument('--refine-base-url', default='http://127.0.0.1:1235')
    p.add_argument('--refine-chunk-size', type=int, default=8)
    p.add_argument('--refine-max-chars', type=int, default=900)
    p.add_argument('--refine-retries', type=int, default=2)
    p.add_argument('--refine-ready-timeout', type=float, default=10.0)
    p.add_argument('--refine-timeout', type=float, default=40.0)
    p.add_argument('--refine-strict', action='store_true')
    p.add_argument('--debug', action='store_true')
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
    separator = '<<<SEG_BREAK_PLAN_B>>>'
    translate_status = 'ok'
    translate_error = None
    translate_elapsed_ms = 0
    translate_started_at = time.time()

    try:
        for chunk in batched_by_chars(segs, args.translate_max_chars):
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
                print(f"[translate][plan_b] batch segments={len(pending_texts)} chars={sum(len(t) for t in pending_texts)} max_chars={args.translate_max_chars}", file=sys.stderr)
                batch_parts = translate_batch(pending_texts, source_lang, args.target_lang, separator, retries=args.translate_retries)
                if len(batch_parts) != len(pending_texts):
                    raise RuntimeError('batch translate segment count mismatch')
                for seg, t in zip(pending, batch_parts):
                    item = dict(seg)
                    item['translation'] = t.strip()
                    translated.append(item)
                    partial_map[str(seg.get('id'))] = item['translation']
                if args.debug:
                    save_partial(partial_path, source_type, source_lang, args.target_lang, has_timestamps, translated)
            if args.sleep_ms:
                time.sleep(args.sleep_ms / 1000.0)
    except Exception as e:
        translate_status = 'failed'
        translate_error = str(e)
        translate_elapsed_ms = round((time.time() - translate_started_at) * 1000)
        print(f"[translate][plan_b] failed fast after {translate_elapsed_ms} ms: {translate_error}", file=sys.stderr)
        raise
    else:
        translate_elapsed_ms = round((time.time() - translate_started_at) * 1000)

    translated.sort(key=lambda x: x.get('id', 0))

    refine_applied = False
    refine_status = 'not_requested'
    refine_error = None
    refine_elapsed_ms = 0
    refine_chunk_size_used = 0
    refine_skipped_noisy = 0
    refine_partial_missing = 0
    if args.refine and translated:
        refine_status = 'requested'
        started = time.time()
        try:
            print(f"[refine][plan_b] waiting for local model at {args.refine_base_url} (timeout={args.refine_ready_timeout:.0f}s)", file=sys.stderr)
            wait_for_lmstudio(args.refine_base_url, ready_timeout=args.refine_ready_timeout)
            refined = []
            changed_count = 0
            refine_candidates = []
            for seg in translated:
                if is_noisy_segment(seg.get('text', ''), seg.get('translation', '')):
                    refine_skipped_noisy += 1
                    refined.append(dict(seg))
                else:
                    refine_candidates.append(seg)
            refine_batches = list(batched_for_refine(refine_candidates, args.refine_max_chars))
            refine_chunk_size_used = max((len(chunk) for chunk in refine_batches), default=0)
            total_chunks = len(refine_batches)
            for idx, chunk in enumerate(refine_batches, start=1):
                chunk_chars = sum(len((seg.get('text') or '').strip()) + len((seg.get('translation') or '').strip()) for seg in chunk)
                refined_map = None
                for attempt in range(1, max(1, args.refine_retries) + 1):
                    chunk_started_at = time.time()
                    print(f"[refine][plan_b] chunk {idx}/{total_chunks} attempt {attempt}/{max(1, args.refine_retries)} size={len(chunk)} chars={chunk_chars} max_chars={args.refine_max_chars} timeout={args.refine_timeout:.0f}s", file=sys.stderr)
                    try:
                        refined_map = lmstudio_refine_batch(chunk, args.refine_base_url, args.refine_timeout)
                        missing_ids = [str(seg.get('id')) for seg in chunk if str(seg.get('id')) not in refined_map]
                        if missing_ids:
                            for seg in chunk:
                                sid = str(seg.get('id'))
                                if sid in refined_map:
                                    continue
                                single_map = lmstudio_refine_batch([seg], args.refine_base_url, args.refine_timeout)
                                if sid in single_map:
                                    refined_map[sid] = single_map[sid]
                        elapsed = round((time.time() - chunk_started_at) * 1000)
                        missing_ids = [str(seg.get('id')) for seg in chunk if str(seg.get('id')) not in refined_map]
                        print(f"[refine][plan_b] chunk {idx}/{total_chunks} done in {elapsed} ms missing={len(missing_ids)}", file=sys.stderr)
                        break
                    except Exception as e:
                        elapsed = round((time.time() - chunk_started_at) * 1000)
                        print(f"[refine][plan_b] chunk {idx}/{total_chunks} attempt {attempt} failed in {elapsed} ms: {e}", file=sys.stderr)
                        if attempt >= max(1, args.refine_retries):
                            raise
                for seg in chunk:
                    item = dict(seg)
                    sid = str(seg.get('id'))
                    new_text = (refined_map or {}).get(sid, '').strip() or (seg.get('translation') or '')
                    if sid not in (refined_map or {}):
                        refine_partial_missing += 1
                    item['translation'] = new_text
                    if new_text != (seg.get('translation') or ''):
                        changed_count += 1
                    refined.append(item)
            if changed_count > 0:
                translated = sorted(refined, key=lambda x: x.get('id', 0))
                refine_applied = True
                refine_status = 'applied'
            else:
                translated = sorted(refined, key=lambda x: x.get('id', 0))
                refine_status = 'no_change'
        except Exception as e:
            refine_error = str(e)
            msg = str(e).lower()
            if 'not ready within' in msg:
                refine_status = 'not_ready'
            elif isinstance(e, socket.timeout) or isinstance(e, TimeoutError) or 'timed out' in msg or 'timeout' in msg:
                refine_status = 'timeout'
            else:
                refine_status = 'failed'
            print(f"[refine][plan_b] skipped: {e}", file=sys.stderr)
            if args.refine_strict:
                raise
        finally:
            refine_elapsed_ms = round((time.time() - started) * 1000)
            print(f"[refine][plan_b] total elapsed={refine_elapsed_ms} ms status={refine_status}", file=sys.stderr)

    result = {
        'source_type': source_type,
        'source_lang': source_lang,
        'target_lang': args.target_lang,
        'has_timestamps': has_timestamps,
        'translate_status': translate_status,
        'translate_error': translate_error,
        'translate_elapsed_ms': translate_elapsed_ms,
        'translate_max_chars_used': args.translate_max_chars,
        'refine_requested': args.refine,
        'refine_applied': refine_applied,
        'refine_status': refine_status,
        'refine_error': refine_error,
        'refine_elapsed_ms': refine_elapsed_ms,
        'refine_chunk_size_used': refine_chunk_size_used,
        'refine_max_chars_used': args.refine_max_chars,
        'refine_skipped_noisy': refine_skipped_noisy,
        'refine_partial_missing': refine_partial_missing,
        'plan': 'b',
        'segments': translated,
    }

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    if args.debug:
        save_partial(partial_path, source_type, source_lang, args.target_lang, has_timestamps, translated)
    else:
        cleanup_file(partial_path)
    if args.json_stdout:
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
