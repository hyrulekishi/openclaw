#!/usr/bin/env bash
set -euo pipefail
OC="${OPENCLAW_STATE_DIR:-$HOME/.openclaw}"
GIT_DST="$OC/backup/git-sanitized"
mkdir -p "$GIT_DST"
rm -rf "$GIT_DST"/*
TMP_FULL="${OC}/backup/full-encrypted"
# Run main script but avoid interactive gpg by shadowing it if present.
FAKEBIN="$(mktemp -d)"
trap 'rm -rf "$FAKEBIN"' EXIT
cat > "$FAKEBIN/gpg" <<'EOF'
#!/usr/bin/env bash
echo "gpg skipped in regenerate-git-sanitized.sh" >&2
exit 127
EOF
chmod +x "$FAKEBIN/gpg"
PATH="$FAKEBIN:$PATH" /home/user/.openclaw/workspace/scripts/create-openclaw-dual-backups.sh || true
rm -rf "$OC/backup/.full-stage" "$TMP_FULL"/*.tar.gz 2>/dev/null || true
