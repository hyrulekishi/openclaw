#!/home/user/.openclaw/workspace/tools/media-pipeline/.venv/bin/python
import argparse
import json
import socket
import sys
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


def google_translate_retry(text: str, source_lang: str, target_lang: str, retries: int = 2) -> str:
    delays = [1, 2]
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
        src = len((seg.get('text') or '').strip())
        tgt = len((seg.get('translation') or '').strip())
        seg_chars = src + tgt
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
    if punct_ratio > 0.18:
        return True
    if max_run >= 8:
        return True
    if len(text) <= 60 and len(translation) >= 220:
        return True
    if repeated_char_ratio >= 5.0 and len(translation) >= 180:
        return True
    return False


def lmstudio_refine_batch(batch, source_lang: str, target_lang: str, base_url: str, request_timeout: float):
    url = base_url.rstrip('/') + '/v1/chat/completions'
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
                    'Return exactly one line per input segment. '
                    'Each line must start with REFINE::<id>:: and then the refined Chinese text. '
                    'Do not return JSON. Do not add explanations or extra lines.'
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
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )
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
    for line in content.splitlines():
        line = line.strip()
        if not line.startswith('REFINE::'):
            continue
        parts = line.split('::', 2)
        if len(parts) != 3:
            continue
        _, seg_id, refined = parts
        parsed[str(seg_id).strip()] = refined.strip()

    return parsed


def main():
    p = argparse.ArgumentParser(description='Translate normalized segments')
    p.add_argument('--input', required=True, help='Normalized JSON path')
    p.add_argument('--output', required=True, help='Translated JSON path')
    p.add_argument('--source-lang', default='auto')
    p.add_argument('--target-lang', required=True)
    p.add_argument('--chunk-size', type=int, default=20)
    p.add_argument('--context-window', type=int, default=2)
    p.add_argument('--sleep-ms', type=int, default=300)
    p.add_argument('--translate-max-chars', type=int, default=1500, help='Maximum source characters per base translation batch')
    p.add_argument('--translate-retries', type=int, default=2, help='Retry count for base Google translation before fast-failing')
    p.add_argument('--refine', action='store_true', help='Run local qwen second-pass refinement')
    p.add_argument('--refine-base-url', default='http://127.0.0.1:1235', help='Local OpenAI-compatible endpoint for refinement')
    p.add_argument('--refine-chunk-size', type=int, default=8, help='Legacy segment-count hint for refine requests')
    p.add_argument('--refine-max-chars', type=int, default=2200, help='Maximum combined source+translation characters per refine request')
    p.add_argument('--refine-retries', type=int, default=2, help='Attempts per refine chunk before giving up')
    p.add_argument('--refine-ready-timeout', type=float, default=10.0, help='Seconds to wait before refinement for local model readiness')
    p.add_argument('--refine-timeout', type=float, default=40.0, help='Seconds to wait for each refine request')
    p.add_argument('--refine-strict', action='store_true', help='Fail instead of skipping when local refine is unavailable or times out')
    p.add_argument('--debug', action='store_true', help='Keep debug/intermediate artifacts like translated.partial.json')
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
    translate_status = 'ok'
    translate_error = None
    translate_elapsed_ms = 0
    translate_started_at = time.time()
    translate_max_chars_used = args.translate_max_chars

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
                batch_parts = []
                if any(pending_texts):
                    batch_char_count = sum(len(t) for t in pending_texts)
                    print(
                        f"[translate] batch segments={len(pending_texts)} chars={batch_char_count} max_chars={args.translate_max_chars}",
                        file=sys.stderr,
                    )
                    try:
                        batch_parts = translate_batch(
                            pending_texts,
                            source_lang,
                            args.target_lang,
                            separator,
                            retries=args.translate_retries,
                        )
                    except Exception as e:
                        translate_status = 'failed'
                        translate_error = f'batch_translate_failed: {e}'
                        raise

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
        if translate_status == 'ok':
            translate_status = 'failed'
            translate_error = str(e)
        translate_elapsed_ms = round((time.time() - translate_started_at) * 1000)
        print(f"[translate] failed fast after {translate_elapsed_ms} ms: {translate_error}", file=sys.stderr)
        raise
    else:
        translate_elapsed_ms = round((time.time() - translate_started_at) * 1000)

    translated.sort(key=lambda x: x.get('id', 0))

    refine_applied = False
    refine_status = 'not_requested'
    refine_error = None
    refine_elapsed_ms = 0
    refine_started_at = None
    refine_chunk_size_used = 0
    refine_max_chars_used = args.refine_max_chars
    refine_skipped_noisy = 0
    refine_partial_missing = 0
    if args.refine and translated:
        refine_status = 'requested'
        refine_started_at = time.time()
        try:
            print(
                f"[refine] waiting for local model at {args.refine_base_url} (timeout={args.refine_ready_timeout:.0f}s)",
                file=sys.stderr,
            )
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
                    print(
                        f"[refine] chunk {idx}/{total_chunks} attempt {attempt}/{max(1, args.refine_retries)} size={len(chunk)} chars={chunk_chars} max_chars={args.refine_max_chars} request timeout={args.refine_timeout:.0f}s",
                        file=sys.stderr,
                    )
                    try:
                        refined_map = lmstudio_refine_batch(
                            chunk,
                            source_lang,
                            args.target_lang,
                            base_url=args.refine_base_url,
                            request_timeout=args.refine_timeout,
                        )
                        chunk_elapsed_ms = round((time.time() - chunk_started_at) * 1000)
                        missing_ids = [str(seg.get('id')) for seg in chunk if str(seg.get('id')) not in refined_map]
                        print(
                            f"[refine] chunk {idx}/{total_chunks} done in {chunk_elapsed_ms} ms missing={len(missing_ids)}",
                            file=sys.stderr,
                        )
                        break
                    except Exception as e:
                        chunk_elapsed_ms = round((time.time() - chunk_started_at) * 1000)
                        print(
                            f"[refine] chunk {idx}/{total_chunks} attempt {attempt} failed in {chunk_elapsed_ms} ms: {e}",
                            file=sys.stderr,
                        )
                        if attempt >= max(1, args.refine_retries):
                            raise
                local_changes = 0
                for seg in chunk:
                    item = dict(seg)
                    sid = str(seg.get('id'))
                    if refined_map and sid in refined_map and refined_map[sid].strip():
                        new_text = refined_map[sid].strip()
                    else:
                        new_text = seg.get('translation') or ''
                        refine_partial_missing += 1
                    item['translation'] = new_text
                    if new_text != (seg.get('translation') or ''):
                        local_changes += 1
                    refined.append(item)
                changed_count += local_changes

            if changed_count > 0:
                translated = refined
                refine_applied = True
                refine_status = 'applied'
                if args.debug:
                    save_partial(partial_path, source_type, source_lang, args.target_lang, has_timestamps, translated)
            else:
                refine_status = 'no_change'
        except Exception as e:
            refine_error = str(e)
            msg = str(e).lower()
            if 'not ready within' in msg:
                refine_status = 'not_ready'
            elif isinstance(e, socket.timeout):
                refine_status = 'timeout'
            elif isinstance(e, urllib.error.URLError) and isinstance(getattr(e, 'reason', None), TimeoutError):
                refine_status = 'timeout'
            elif isinstance(e, TimeoutError):
                refine_status = 'timeout'
            elif 'timed out' in msg or 'timeout' in msg:
                refine_status = 'timeout'
            else:
                refine_status = 'failed'
            print(f"[refine] skipped: {e}", file=sys.stderr)
            if args.refine_strict:
                raise
        finally:
            if refine_started_at is not None:
                refine_elapsed_ms = round((time.time() - refine_started_at) * 1000)
                print(f"[refine] total elapsed={refine_elapsed_ms} ms status={refine_status}", file=sys.stderr)

    result = {
        'source_type': source_type,
        'source_lang': source_lang,
        'target_lang': args.target_lang,
        'has_timestamps': has_timestamps,
        'translate_status': translate_status,
        'translate_error': translate_error,
        'translate_elapsed_ms': translate_elapsed_ms,
        'translate_max_chars_used': translate_max_chars_used,
        'refine_requested': args.refine,
        'refine_applied': refine_applied,
        'refine_status': refine_status,
        'refine_error': refine_error,
        'refine_elapsed_ms': refine_elapsed_ms,
        'refine_chunk_size_used': refine_chunk_size_used,
        'refine_max_chars_used': refine_max_chars_used,
        'refine_skipped_noisy': refine_skipped_noisy,
        'refine_partial_missing': refine_partial_missing,
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
