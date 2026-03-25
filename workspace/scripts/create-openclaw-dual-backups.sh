#!/usr/bin/env bash
set -euo pipefail

OC="${OPENCLAW_STATE_DIR:-$HOME/.openclaw}"
BACKUP_ROOT="$OC/backup"
GIT_DST="$BACKUP_ROOT/git-sanitized"
FULL_STAGE="$BACKUP_ROOT/.full-stage"
FULL_DST="$BACKUP_ROOT/full-encrypted"
STAMP="$(date +%F-%H%M%S)"
FULL_TAR="$FULL_DST/openclaw-full-$STAMP.tar.gz"
FULL_GPG="$FULL_TAR.gpg"

mkdir -p "$GIT_DST" "$FULL_STAGE" "$FULL_DST"
rm -rf "$GIT_DST/openclaw"
rm -rf "$FULL_STAGE"/*
mkdir -p "$GIT_DST/openclaw" "$FULL_STAGE/openclaw"

copy_if_exists() {
  local src="$1" dst="$2"
  if [ -e "$src" ]; then
    mkdir -p "$(dirname "$dst")"
    cp -a "$src" "$dst"
  fi
}

copy_dir_contents() {
  local src="$1" dst="$2"
  if [ -d "$src" ]; then
    mkdir -p "$dst"
    cp -a "$src"/. "$dst"/
  fi
}

copy_tree_excluding_jsonl() {
  local src="$1" dst="$2"
  if [ -d "$src" ]; then
    mkdir -p "$dst"
    (cd "$src" && tar \
      --exclude='*/sessions/*.jsonl' \
      --exclude='*/sessions/*.lock' \
      --exclude='*/sessions/*.reset.*' \
      --exclude='logs' \
      --exclude='canvas' \
      --exclude='completions' \
      --exclude='sandboxes' \
      --exclude='telegram' \
      --exclude='backup' \
      --exclude='*.bak*' \
      --exclude='*.tmp' \
      --exclude='update-check.json' \
      --exclude='exec-approvals.json' \
      -cf - .) | (cd "$dst" && tar -xf -)
  fi
}

# -----------------------------
# Track A: git-sanitized
# -----------------------------
copy_if_exists "$OC/openclaw.json" "$GIT_DST/openclaw/openclaw.json"
if [ -d "$OC/workspace" ]; then
  mkdir -p "$GIT_DST/openclaw/workspace"
  (cd "$OC/workspace" && tar \
    --exclude='./backups' \
    --exclude='./memory' \
    --exclude='./tmp' \
    --exclude='./canvas' \
    --exclude='./output' \
    --exclude='./research/memory-lancedb-pro' \
    --exclude='./.clawhub' \
    --exclude='./tmp-*' \
    --exclude='*/output' \
    --exclude='*/.venv' \
    --exclude='*/__pycache__' \
    --exclude='*/.pytest_cache' \
    --exclude='*/.mypy_cache' \
    --exclude='*/.ruff_cache' \
    --exclude='*/node_modules' \
    --exclude='*/.git' \
    --exclude='*/.clawhub' \
    -cf - .) | (cd "$GIT_DST/openclaw/workspace" && tar -xf -)
fi
copy_dir_contents "$OC/cron" "$GIT_DST/openclaw/cron"
copy_if_exists "$OC/identity/device.json" "$GIT_DST/openclaw/identity/device.json"
copy_if_exists "$OC/.config-baseline.sha256" "$GIT_DST/openclaw/.config-baseline.sha256"
copy_if_exists "$OC/agents/main/agent/auth-profiles.json" "$GIT_DST/openclaw/agents/main/agent/auth-profiles.json"
copy_if_exists "$OC/agents/main/agent/models.json" "$GIT_DST/openclaw/agents/main/agent/models.json"

python3 <<'PY'
import json, pathlib
base = pathlib.Path.home() / '.openclaw' / 'backup' / 'git-sanitized' / 'openclaw'

SENSITIVE_MARKERS = ['token','secret','password','cookie','refresh','api_key','apikey','access_token','client_secret']
KEEP_AUTH_FIELDS = {'provider','mode','keyRef','key_ref','profile','baseUrl','baseURL','model','alias','name','id'}


def redact_generic(obj):
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            lk = k.lower()
            if k in {'deviceId', 'publicKeyPem', 'privateKeyPem'}:
                out[k] = 'REDACTED'
            elif any(m in lk for m in SENSITIVE_MARKERS):
                out[k] = 'REDACTED'
            else:
                out[k] = redact_generic(v)
        return out
    if isinstance(obj, list):
        return [redact_generic(x) for x in obj]
    return obj


def redact_auth(obj):
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k in KEEP_AUTH_FIELDS or 'keyref' in k.lower():
                out[k] = v
            elif isinstance(v, (dict, list)):
                out[k] = redact_auth(v)
            else:
                out[k] = 'REDACTED'
        return out
    if isinstance(obj, list):
        return [redact_auth(x) for x in obj]
    return obj

for rel, mode in [
    ('openclaw.json', 'generic'),
    ('identity/device.json', 'generic'),
    ('agents/main/agent/auth-profiles.json', 'auth'),
]:
    p = base / rel
    if not p.exists():
        continue
    try:
        data = json.loads(p.read_text(encoding='utf-8'))
        data = redact_auth(data) if mode == 'auth' else redact_generic(data)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    except Exception:
        pass
PY

rm -rf \
  "$GIT_DST/openclaw/credentials" \
  "$GIT_DST/openclaw/devices" \
  "$GIT_DST/openclaw/telegram" \
  "$GIT_DST/openclaw/sandboxes" \
  "$GIT_DST/openclaw/logs" \
  "$GIT_DST/openclaw/canvas" \
  "$GIT_DST/openclaw/completions" \
  "$GIT_DST/openclaw/agents/main/sessions" 2>/dev/null || true

find "$GIT_DST/openclaw" \( -name '*.bak*' -o -name '*.tmp' -o -name '*.lock' -o -name '*.reset.*' -o -name '.env' -o -name 'paired.json' -o -name 'pending.json' -o -name 'update-check.json' -o -name 'exec-approvals.json' -o -name '__pycache__' -o -name '.pytest_cache' -o -name '.mypy_cache' -o -name '.ruff_cache' -o -name '.venv' -o -name 'node_modules' \) -print0 2>/dev/null | while IFS= read -r -d '' f; do
  rm -rf "$f"
done

rm -rf \
  "$GIT_DST/openclaw/workspace/.clawhub" \
  "$GIT_DST/openclaw/workspace/memory" \
  "$GIT_DST/openclaw/workspace/tmp" \
  "$GIT_DST/openclaw/workspace/canvas" \
  "$GIT_DST/openclaw/workspace/output" \
  "$GIT_DST/openclaw/workspace/research/memory-lancedb-pro" 2>/dev/null || true

find "$GIT_DST/openclaw/workspace" -type d \( -name '.git' -o -name '.clawhub' \) -prune -exec rm -rf {} + 2>/dev/null || true
find "$GIT_DST/openclaw/workspace" -maxdepth 1 -type f -name 'tmp-*' -delete 2>/dev/null || true

cat > "$GIT_DST/openclaw/.gitignore" <<'EOF'
.env
**/.env
credentials/
devices/
logs/
canvas/
completions/
sandboxes/
telegram/
agents/*/sessions/
workspace/.clawhub/
workspace/memory/
workspace/tmp/
workspace/canvas/
workspace/output/
**/.venv/
**/__pycache__/
**/.pytest_cache/
**/.mypy_cache/
**/.ruff_cache/
**/node_modules/
**/.git/
*.bak*
*.tmp
*.lock
*.reset.*
update-check.json
exec-approvals.json
EOF

cat > "$GIT_DST/openclaw/README-backup.md" <<'EOF'
# OpenClaw sanitized backup

This is the Git-safe track of the dual-backup policy.

Included:
- workspace/
- cron/
- identity/device.json (redacted where applicable)
- redacted openclaw.json
- redacted agents/main/agent/
- .config-baseline.sha256

Excluded:
- .env
- credentials/
- devices/
- memory/
- all session history
- logs/
- sandboxes/
- telegram runtime state
- generated backups, temp, lock, reset files
EOF

# -----------------------------
# Track B: local full encrypted
# -----------------------------
copy_if_exists "$OC/openclaw.json" "$FULL_STAGE/openclaw/openclaw.json"
copy_if_exists "$OC/.env" "$FULL_STAGE/openclaw/.env"
copy_dir_contents "$OC/workspace" "$FULL_STAGE/openclaw/workspace"
copy_tree_excluding_jsonl "$OC/agents" "$FULL_STAGE/openclaw/agents"
copy_dir_contents "$OC/cron" "$FULL_STAGE/openclaw/cron"
copy_dir_contents "$OC/credentials" "$FULL_STAGE/openclaw/credentials"
copy_dir_contents "$OC/identity" "$FULL_STAGE/openclaw/identity"
copy_dir_contents "$OC/memory" "$FULL_STAGE/openclaw/memory"
copy_if_exists "$OC/devices/paired.json" "$FULL_STAGE/openclaw/devices/paired.json"
copy_if_exists "$OC/.config-baseline.sha256" "$FULL_STAGE/openclaw/.config-baseline.sha256"

find "$FULL_STAGE/openclaw" \( -name '*.bak*' -o -name '*.tmp' -o -name '*.lock' -o -name '*.reset.*' -o -name 'update-check.json' -o -name 'exec-approvals.json' \) -print0 2>/dev/null | while IFS= read -r -d '' f; do
  rm -rf "$f"
done

cat > "$FULL_STAGE/openclaw/RESTORE-NOTES.txt" <<'EOF'
Full local encrypted OpenClaw backup.
Contains real secrets and identity material.
Store only in trusted encrypted locations.
Session *.jsonl files are intentionally excluded by policy.
EOF

tar -C "$FULL_STAGE" -czf "$FULL_TAR" openclaw

if command -v gpg >/dev/null 2>&1; then
  echo "Encrypting full backup with gpg symmetric encryption..."
  echo "You will be prompted locally for a passphrase."
  gpg --symmetric --cipher-algo AES256 --output "$FULL_GPG" "$FULL_TAR"
  rm -f "$FULL_TAR"
  echo "Encrypted full backup ready: $FULL_GPG"
else
  echo "gpg not found; leaving unencrypted tarball at: $FULL_TAR"
fi

echo "Sanitized backup ready: $GIT_DST/openclaw"
