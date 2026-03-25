#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

DEFAULT_CONFIG = Path('/mnt/e/Flux/LoRA_Easy_Training_Scripts_exp/backend/runtime_store/config.toml')
DEFAULT_WINDOWS_POWERSHELL = Path('/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe')

STEP_RE = re.compile(rb'steps:\s*([^\r\n]{0,240}?)(\d+)/(\d+)[^\r\n]{0,240}?avr_loss=([0-9.]+)')
S_IT_RE = re.compile(rb'(\d+(?:\.\d+)?)s/it')
RUNTIME_RE = re.compile(rb'_runtime[^\x00-\x1f]{0,8}(\d+(?:\.\d+)?)')
TIMESTAMP_RE = re.compile(rb'_timestamp[^\x00-\x1f]{0,8}(\d+(?:\.\d+)?)')
CONFIG_RE = re.compile(r'--config_file=([^\s]+config\.toml)')


@dataclass
class Progress:
    name: str
    step: int
    total: int
    percent: float
    avr_loss: float
    seconds_per_step: Optional[float]
    eta_seconds: Optional[float]
    status: str
    source_log_dir: Optional[str] = None


@dataclass
class GpuStats:
    name: Optional[str] = None
    dedicated_total_mb: Optional[int] = None
    dedicated_used_mb: Optional[int] = None
    dedicated_free_mb: Optional[int] = None
    gpu_util_percent: Optional[int] = None
    temperature_c: Optional[int] = None
    shared_used_mb: Optional[int] = None
    shared_limit_mb: Optional[int] = None
    dedicated_train_mb: Optional[int] = None
    shared_train_mb: Optional[int] = None
    train_pid: Optional[int] = None
    risk: Optional[str] = None
    risk_reason: Optional[str] = None
    speed_ratio: Optional[float] = None
    baseline_seconds_per_step: Optional[float] = None


def windows_to_wsl_path(path_str: str) -> Path:
    s = path_str.strip().strip('"').replace('\\', '/')
    if re.match(r'^[A-Za-z]:/', s):
        drive = s[0].lower()
        return Path(f'/mnt/{drive}{s[2:]}')
    return Path(s)


def run_powershell(script: str) -> str:
    if not DEFAULT_WINDOWS_POWERSHELL.exists():
        return ''
    try:
        result = subprocess.run(
            [str(DEFAULT_WINDOWS_POWERSHELL), '-NoProfile', '-Command', script],
            capture_output=True,
            text=True,
            timeout=25,
            check=False,
        )
        return (result.stdout or '') + ('\n' + result.stderr if result.stderr else '')
    except Exception:
        return ''


def detect_current_config_path() -> Optional[Path]:
    ps_script = r"""
$ErrorActionPreference='SilentlyContinue'
Get-CimInstance Win32_Process |
  Where-Object {
    $_.CommandLine -and (
      $_.CommandLine -match 'sdxl_train_network.py' -or
      $_.CommandLine -match 'flux_train_network.py' -or
      $_.CommandLine -match 'train_network.py'
    )
  } |
  Select-Object -ExpandProperty CommandLine
""".strip()
    output = run_powershell(ps_script)
    for line in output.splitlines():
        m = CONFIG_RE.search(line)
        if m:
            p = windows_to_wsl_path(m.group(1))
            if p.exists():
                return p
    return DEFAULT_CONFIG if DEFAULT_CONFIG.exists() else None


def detect_train_pid() -> Optional[int]:
    ps_script = r"""
$ErrorActionPreference='SilentlyContinue'
Get-CimInstance Win32_Process |
  Where-Object {
    $_.CommandLine -and (
      $_.CommandLine -match 'sdxl_train_network.py' -or
      $_.CommandLine -match 'flux_train_network.py' -or
      $_.CommandLine -match 'train_network.py'
    )
  } |
  Sort-Object ProcessId -Descending |
  Select-Object -First 1 -ExpandProperty ProcessId
""".strip()
    out = run_powershell(ps_script).strip()
    m = re.search(r'(\d+)', out)
    return int(m.group(1)) if m else None


def load_config(config_path: Path) -> dict:
    with config_path.open('rb') as f:
        return tomllib.load(f)


def latest_log_dir(logging_dir: Path) -> Optional[Path]:
    dirs = [p for p in logging_dir.iterdir() if p.is_dir()]
    return max(dirs, key=lambda p: p.stat().st_mtime) if dirs else None


def find_log_dir_for_name(logging_dir: Path, name: str) -> Optional[Path]:
    candidates = sorted([p for p in logging_dir.iterdir() if p.is_dir()], key=lambda p: p.stat().st_mtime, reverse=True)
    encoded = name.encode('utf-8', 'ignore')
    for d in candidates:
        for wf in d.rglob('*.wandb'):
            try:
                data = wf.read_bytes()
            except Exception:
                continue
            if encoded in data:
                return d
    return None


def parse_latest_progress(log_dir: Path) -> Optional[dict]:
    best = None
    for wf in sorted(log_dir.rglob('*.wandb')):
        try:
            data = wf.read_bytes()
        except Exception:
            continue
        matches = list(STEP_RE.finditer(data))
        if not matches:
            continue
        m = matches[-1]
        step = int(m.group(2))
        total = int(m.group(3))
        loss = float(m.group(4))
        segment_start = max(0, m.start() - 256)
        segment_end = min(len(data), m.end() + 256)
        segment = data[segment_start:segment_end]
        s_it_matches = list(S_IT_RE.finditer(segment))
        sec_per_step = float(s_it_matches[-1].group(1)) if s_it_matches else None
        runtime_matches = list(RUNTIME_RE.finditer(segment))
        runtime = float(runtime_matches[-1].group(1)) if runtime_matches else None
        ts_matches = list(TIMESTAMP_RE.finditer(segment))
        timestamp = float(ts_matches[-1].group(1)) if ts_matches else None
        item = {
            'file': str(wf),
            'step': step,
            'total': total,
            'loss': loss,
            'sec_per_step': sec_per_step,
            'runtime': runtime,
            'timestamp': timestamp,
        }
        if best is None:
            best = item
            continue
        best_key = (best['step'], best['timestamp'] or 0, best['runtime'] or 0)
        item_key = (item['step'], item['timestamp'] or 0, item['runtime'] or 0)
        if item_key > best_key:
            best = item
    return best


def baseline_seconds_per_step(log_dir: Path) -> Optional[float]:
    values = []
    for wf in sorted(log_dir.rglob('*.wandb')):
        try:
            data = wf.read_bytes()
        except Exception:
            continue
        for m in STEP_RE.finditer(data):
            step = int(m.group(2))
            segment_start = max(0, m.start() - 256)
            segment_end = min(len(data), m.end() + 256)
            segment = data[segment_start:segment_end]
            s_it_matches = list(S_IT_RE.finditer(segment))
            sec_per_step = float(s_it_matches[-1].group(1)) if s_it_matches else None
            if sec_per_step is None:
                runtime_matches = list(RUNTIME_RE.finditer(segment))
                runtime = float(runtime_matches[-1].group(1)) if runtime_matches else None
                if runtime and step:
                    sec_per_step = runtime / step
            if sec_per_step is not None and 10 <= step <= 60:
                values.append(sec_per_step)
    if not values:
        return None
    values.sort()
    mid = len(values) // 2
    return values[mid] if len(values) % 2 == 1 else (values[mid - 1] + values[mid]) / 2


def build_progress(name: str, parsed: dict, log_dir: Path) -> Progress:
    step = parsed['step']
    total = parsed['total']
    percent = (step / total * 100.0) if total else 0.0
    sec_per_step = parsed.get('sec_per_step')
    if sec_per_step is None and parsed.get('runtime') and step:
        sec_per_step = parsed['runtime'] / step
    eta = None
    if sec_per_step is not None and total >= step:
        eta = (total - step) * sec_per_step
    status = 'running' if step < total else 'finished'
    return Progress(name, step, total, percent, parsed['loss'], sec_per_step, eta, status, str(log_dir))


def get_gpu_stats(train_pid: Optional[int], baseline_s: Optional[float], current_s: Optional[float]) -> GpuStats:
    ps_script = r"""
$ErrorActionPreference='SilentlyContinue'
$gpu = Get-Counter '\GPU Adapter Memory(*)\Dedicated Usage','\GPU Adapter Memory(*)\Shared Usage','\GPU Local Adapter Memory(*)\Local Usage','\GPU Non Local Adapter Memory(*)\Non Local Usage' -SampleInterval 1 -MaxSamples 1
$proc = Get-Counter '\GPU Process Memory(*)\Dedicated Usage','\GPU Process Memory(*)\Shared Usage','\GPU Process Memory(*)\Local Usage','\GPU Process Memory(*)\Non Local Usage' -SampleInterval 1 -MaxSamples 1
$gpuCounters = @()
foreach ($c in $gpu.CounterSamples) {
  $gpuCounters += [pscustomobject]@{ Path=$c.Path; CookedValue=[double]$c.CookedValue }
}
$procCounters = @()
foreach ($c in $proc.CounterSamples) {
  $procCounters += [pscustomobject]@{ Path=$c.Path; CookedValue=[double]$c.CookedValue }
}
[pscustomobject]@{
  gpuCounters = $gpuCounters
  procCounters = $procCounters
} | ConvertTo-Json -Depth 6 -Compress
""".strip()
    stats = GpuStats()

    try:
        smi = subprocess.run(
            ['/usr/lib/wsl/lib/nvidia-smi', '--query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu', '--format=csv,noheader,nounits'],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        ).stdout.strip()
        if smi:
            parts = [p.strip() for p in smi.split(',')]
            if len(parts) >= 6:
                stats.name = parts[0]
                stats.dedicated_total_mb = int(parts[1])
                stats.dedicated_used_mb = int(parts[2])
                stats.dedicated_free_mb = int(parts[3])
                stats.gpu_util_percent = int(parts[4])
                stats.temperature_c = int(parts[5])
    except Exception:
        pass

    raw = run_powershell(ps_script).strip()
    if raw:
        try:
            obj = json.loads(raw)
            gpu_counters = obj.get('gpuCounters') or []
            proc_counters = obj.get('procCounters') or []
            shared_values = []
            shared_limit_values = []
            for c in gpu_counters:
                path = c.get('Path', '')
                val_mb = int(round(float(c.get('CookedValue', 0)) / (1024 * 1024)))
                if 'Shared Usage' in path or 'Non Local Usage' in path:
                    shared_values.append(val_mb)
                    m = re.search(r'\((\d+)\)', path)
                    if m:
                        shared_limit_values.append(int(m.group(1)))
            if shared_values:
                stats.shared_used_mb = max(shared_values)
            if shared_limit_values:
                stats.shared_limit_mb = max(shared_limit_values)

            if train_pid is not None:
                dvals, svals = [], []
                for c in proc_counters:
                    path = c.get('Path', '')
                    if f'pid_{train_pid}_' not in path.lower():
                        continue
                    val_mb = int(round(float(c.get('CookedValue', 0)) / (1024 * 1024)))
                    if 'Dedicated Usage' in path or 'Local Usage' in path:
                        dvals.append(val_mb)
                    elif 'Shared Usage' in path or 'Non Local Usage' in path:
                        svals.append(val_mb)
                if dvals:
                    stats.dedicated_train_mb = max(dvals)
                if svals:
                    stats.shared_train_mb = max(svals)
        except Exception:
            pass

    stats.train_pid = train_pid
    stats.baseline_seconds_per_step = round(baseline_s, 3) if baseline_s is not None else None
    if baseline_s and current_s and baseline_s > 0:
        stats.speed_ratio = current_s / baseline_s

    risk = 'normal'
    reasons = []
    shared = stats.shared_train_mb if stats.shared_train_mb is not None else stats.shared_used_mb
    free = stats.dedicated_free_mb
    ratio = stats.speed_ratio

    if shared is not None and shared >= 1024:
        risk = 'high'
        reasons.append(f'shared {shared}MB')
    elif shared is not None and shared >= 512:
        risk = 'warn'
        reasons.append(f'shared {shared}MB')
    elif shared is not None and shared >= 300:
        reasons.append(f'shared {shared}MB')

    if free is not None and free <= 512:
        risk = 'high'
        reasons.append(f'free {free}MB')
    elif free is not None and free <= 1024 and risk != 'high':
        risk = 'warn'
        reasons.append(f'free {free}MB')

    if ratio is not None and ratio >= 1.6:
        risk = 'high'
        reasons.append(f'speed x{ratio:.2f}')
    elif ratio is not None and ratio >= 1.35 and risk != 'high':
        risk = 'warn'
        reasons.append(f'speed x{ratio:.2f}')

    stats.risk = risk
    stats.risk_reason = ', '.join(reasons) if reasons else 'within expected range'
    return stats


def format_eta(seconds: Optional[float]) -> Optional[str]:
    if seconds is None:
        return None
    seconds = max(0, int(round(seconds)))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f'{h}h{m:02d}m'
    if m:
        return f'{m}m{s:02d}s'
    return f'{s}s'


def main() -> int:
    ap = argparse.ArgumentParser(description='Check current or named training progress from config + wandb offline logs.')
    ap.add_argument('--name', help='Training/output name to query, e.g. waifu_I20')
    ap.add_argument('--config', help='Explicit config.toml path')
    ap.add_argument('--json', action='store_true', help='Print JSON output')
    args = ap.parse_args()

    config_path = Path(args.config) if args.config else detect_current_config_path()
    if not config_path or not config_path.exists():
        msg = {'status': 'not_found', 'error': 'Could not locate active config.toml'}
        print(json.dumps(msg, ensure_ascii=False) if args.json else msg['error'])
        return 1

    cfg = load_config(config_path)
    logging_dir = windows_to_wsl_path(str(cfg.get('logging_dir', '')))
    current_name = str(cfg.get('output_name') or cfg.get('wandb_run_name') or '').strip()
    target_name = (args.name or current_name).strip()
    if not target_name:
        msg = {'status': 'not_found', 'error': 'Could not determine current training name'}
        print(json.dumps(msg, ensure_ascii=False) if args.json else msg['error'])
        return 1
    if not logging_dir.exists():
        msg = {'status': 'not_found', 'error': f'Logging dir not found: {logging_dir}'}
        print(json.dumps(msg, ensure_ascii=False) if args.json else msg['error'])
        return 1

    log_dir = find_log_dir_for_name(logging_dir, target_name) if args.name else latest_log_dir(logging_dir)
    if log_dir is None:
        msg = {'status': 'not_found', 'error': f'No matching log directory found for {target_name}'}
        print(json.dumps(msg, ensure_ascii=False) if args.json else msg['error'])
        return 1

    parsed = parse_latest_progress(log_dir)
    if not parsed:
        msg = {'status': 'not_found', 'error': f'Could not parse progress from {log_dir}'}
        print(json.dumps(msg, ensure_ascii=False) if args.json else msg['error'])
        return 1

    progress = build_progress(target_name, parsed, log_dir)
    baseline_s = baseline_seconds_per_step(log_dir)
    gpu = get_gpu_stats(detect_train_pid(), baseline_s, progress.seconds_per_step)

    payload = {
        'name': progress.name,
        'step': progress.step,
        'total': progress.total,
        'percent': round(progress.percent, 2),
        'avr_loss': progress.avr_loss,
        'seconds_per_step': round(progress.seconds_per_step, 3) if progress.seconds_per_step is not None else None,
        'baseline_seconds_per_step': gpu.baseline_seconds_per_step,
        'speed_ratio': round(gpu.speed_ratio, 3) if gpu.speed_ratio is not None else None,
        'eta_seconds': round(progress.eta_seconds, 1) if progress.eta_seconds is not None else None,
        'eta_human': format_eta(progress.eta_seconds),
        'status': progress.status,
        'gpu_name': gpu.name,
        'dedicated_total_mb': gpu.dedicated_total_mb,
        'dedicated_used_mb': gpu.dedicated_used_mb,
        'dedicated_free_mb': gpu.dedicated_free_mb,
        'dedicated_train_mb': gpu.dedicated_train_mb,
        'shared_used_mb': gpu.shared_used_mb,
        'shared_limit_mb': gpu.shared_limit_mb,
        'shared_train_mb': gpu.shared_train_mb,
        'gpu_util_percent': gpu.gpu_util_percent,
        'temperature_c': gpu.temperature_c,
        'train_pid': gpu.train_pid,
        'risk': gpu.risk,
        'risk_reason': gpu.risk_reason,
        'config_path': str(config_path),
        'log_dir': progress.source_log_dir,
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        parts = [
            progress.name,
            f'{progress.step}/{progress.total}',
            f'{progress.percent:.1f}%',
            f'avr_loss {progress.avr_loss:.3f}',
        ]
        eta_h = format_eta(progress.eta_seconds)
        if eta_h:
            parts.append(f'ETA {eta_h}')
        if gpu.dedicated_used_mb is not None and gpu.dedicated_total_mb is not None:
            parts.append(f'VRAM {gpu.dedicated_used_mb}/{gpu.dedicated_total_mb}MB')
        if gpu.shared_train_mb is not None:
            parts.append(f'Shared(train) {gpu.shared_train_mb}MB')
        elif gpu.shared_used_mb is not None:
            parts.append(f'Shared {gpu.shared_used_mb}MB')
        if gpu.speed_ratio is not None:
            parts.append(f'speed x{gpu.speed_ratio:.2f}')
        if gpu.risk:
            parts.append(f'risk {gpu.risk}')
        parts.append(progress.status)
        print(' | '.join(parts))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
