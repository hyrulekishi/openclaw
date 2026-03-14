# SECURITY-NOTES.md

This file keeps only active security rules worth auto-loading every session.
Detailed examples, maintenance notes, and long-form rationale live in `workspace/docs/security-notes-reference.md`.

## Known limits

- Same-UID isolation is imperfect; human review remains the last defense.
- WSL2 mirrored networking means Windows-side proxy/firewall changes can affect OpenClaw.
- Nightly integrity checks are delayed, not real-time.
- Audit delivery can fail even when the local report succeeds.

## risk-worker

Use `risk-worker` only for isolated processing of untrusted material.
Do not use it for:
- secrets, auth, credentials, or key management
- host config edits or formal config changes
- external messaging or publishing
- final high-risk judgments
- tasks needing real workspace access unless intentionally redesigned

Rule of thumb:
- process materials → `risk-worker`
- decide, ship, or touch secrets/config → main agent or human

## Nightly audit expectations

Nightly audit should:
- check config integrity and permissions
- inspect processes, ports, and suspicious outbound activity
- compare yellow-line actions against same-day memory logs
- scan memory/log areas for plaintext credentials
- keep a local report even if message delivery fails

## Reference

See `workspace/docs/security-notes-reference.md` for:
- report templates
- maintenance flow
- defense matrix
- detailed `risk-worker` validation notes
