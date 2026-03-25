#!/home/user/.openclaw/workspace/tools/media-pipeline/.venv/bin/python
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path.home() / ".openclaw" / "workspace" / "tools" / "media-pipeline"
DEFAULT_CONFIG = ROOT / "config" / "default.yaml"
VENV_PYTHON = ROOT / ".venv" / "bin" / "python"

# Auto-reexec inside the media-pipeline venv if available.
if os.environ.get("MEDIA_PIPELINE_REEXEC") != "1":
    if VENV_PYTHON.exists() and Path(sys.executable).resolve() != VENV_PYTHON.resolve():
        env = os.environ.copy()
        env["MEDIA_PIPELINE_REEXEC"] = "1"
        os.execve(str(VENV_PYTHON), [str(VENV_PYTHON), __file__, *sys.argv[1:]], env)

try:
    import yaml
except Exception:
    yaml = None

from faster_whisper import WhisperModel


def load_config(path: Path):
    if yaml is None or not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def resolve_model(args, cfg):
    if args.model:
        return args.model
    profile = args.profile or cfg.get("default_profile", "balanced")
    return cfg.get("model_profiles", {}).get(profile, "distil-large-v3")


def choose_device_and_compute(device_arg, compute_arg):
    if device_arg != "auto":
        device = device_arg
    else:
        try:
            import ctranslate2
            device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
        except Exception:
            device = "cpu"

    if compute_arg != "auto":
        compute_type = compute_arg
    else:
        compute_type = "float16" if device == "cuda" else "int8"

    return device, compute_type


def build_output_paths(audio_path: Path, out_dir: Path | None):
    if out_dir is None:
        out_dir = audio_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    return {
        "txt": out_dir / "transcript.txt",
        "json": out_dir / "transcript.json",
        "meta": out_dir / "meta.json",
    }


def main():
    parser = argparse.ArgumentParser(description="Local media transcription with faster-whisper")
    parser.add_argument("audio", help="Path to audio file")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Path to config YAML")
    parser.add_argument("--profile", choices=["fast", "balanced", "best"], help="Model profile")
    parser.add_argument("--model", help="Explicit model name override")
    parser.add_argument("--language", default=None, help="Language code, e.g. zh, ja, en")
    parser.add_argument("--vad", action="store_true", help="Enable VAD filtering")
    parser.add_argument("--word-timestamps", action="store_true", help="Include word timestamps")
    parser.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda"], help="Compute device")
    parser.add_argument("--compute-type", default="auto", choices=["auto", "int8", "float16", "float32"], help="Compute type")
    parser.add_argument("--beam-size", type=int, default=5)
    parser.add_argument("--output-dir", default=None, help="Directory for transcript outputs")
    parser.add_argument("--json-stdout", action="store_true", help="Print transcript JSON to stdout")
    parser.add_argument("--debug", action="store_true", help="Keep extra debug artifacts like transcript.txt and meta.json")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    audio_path = Path(args.audio).expanduser().resolve()
    if not audio_path.exists():
        print(f"Error: audio file not found: {audio_path}", file=sys.stderr)
        sys.exit(1)

    cfg = load_config(Path(args.config).expanduser())
    model_name = resolve_model(args, cfg)
    device, compute_type = choose_device_and_compute(args.device, args.compute_type)
    output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else None
    out = build_output_paths(audio_path, output_dir)

    vad_enabled = args.vad or bool(cfg.get("vad_filter", False))
    word_ts = args.word_timestamps or bool(cfg.get("word_timestamps", False))

    if not args.quiet:
        print(f"Loading model={model_name} device={device} compute_type={compute_type}", file=sys.stderr)

    model = WhisperModel(model_name, device=device, compute_type=compute_type)
    segments, info = model.transcribe(
        str(audio_path),
        language=args.language,
        beam_size=args.beam_size,
        vad_filter=vad_enabled,
        word_timestamps=word_ts,
    )

    result = {
        "source": str(audio_path),
        "model": model_name,
        "device": device,
        "compute_type": compute_type,
        "language": info.language,
        "language_probability": getattr(info, "language_probability", None),
        "duration": getattr(info, "duration", None),
        "text": "",
        "segments": [],
    }

    texts = []
    for seg in segments:
        seg_item = {
            "start": seg.start,
            "end": seg.end,
            "text": seg.text.strip(),
        }
        if word_ts and getattr(seg, "words", None):
            seg_item["words"] = [
                {
                    "word": w.word,
                    "start": w.start,
                    "end": w.end,
                    "probability": getattr(w, "probability", None),
                }
                for w in seg.words
            ]
        result["segments"].append(seg_item)
        if seg_item["text"]:
            texts.append(seg_item["text"])

    result["text"] = "\n".join(texts).strip()

    out["json"].write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.debug:
        out["txt"].write_text(result["text"] + ("\n" if result["text"] else ""), encoding="utf-8")
        meta = {
            "source": str(audio_path),
            "model": model_name,
            "device": device,
            "compute_type": compute_type,
            "output_dir": str(out["txt"].parent),
        }
        out["meta"].write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.json_stdout:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result["text"])


if __name__ == "__main__":
    main()
