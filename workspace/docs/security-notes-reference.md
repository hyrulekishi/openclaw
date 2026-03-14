# SECURITY-NOTES Reference

This file holds background material and low-frequency reference content that does not need to be auto-loaded every session.

## Known limits

1. **Agent cognition remains vulnerable**: carefully crafted documents can still try to route around behavior rules. Human review is the last defense.
2. **Same-UID read risk**: OpenClaw runs as the current user, so `chmod 600` narrows access but does not isolate from the same UID. Real isolation requires sandboxing/containerization.
3. **Hash baselines are delayed**: nightly checks mean up to ~24h detection lag.
4. **WSL2 mirrored networking**: Windows-side proxy/firewall changes directly affect WSL2 behavior.
5. **Audit delivery depends on external APIs**: Telegram delivery can fail even when the local report is generated.

## Nightly audit brief example

```text
🛡️ OpenClaw 每日安全巡检简报 (YYYY-MM-DD)

1.  平台审计:     ✅ 已执行原生扫描
2.  进程网络:     ✅ 无异常出站/监听端口
3.  目录变更:     ✅ N 个文件（位于 $OC/ 或 /etc/ 等）
4.  系统 Cron:    ✅ 未发现可疑系统级任务
5.  本地 Cron:    ✅ 内部任务列表与预期一致
6.  SSH 安全:     ✅ 0 次失败爆破尝试
7.  配置基线:     ✅ 哈希校验通过且权限合规
8.  黄线审计:     ✅ N 次 sudo（与 memory 日志比对）
9.  磁盘容量:     ✅ 根分区占用 XX%，新增 0 个大文件
10. 环境变量:     ✅ 内存凭证未发现异常泄露
11. 凭证扫描:     ✅ memory/ 等日志目录未发现明文私钥或助记词
12. Skill 基线:   ✅ 无变更
13. 灾备备份:     ✅ 已执行双轨备份（Git 脱敏轨已生成，本地加密轨已生成；Git push 由人工执行）

📝 详细报告已保存：/tmp/openclaw/security-reports/report-YYYY-MM-DD.txt
```

## Nightly audit script maintenance

```bash
# 解锁 → 修改 → 测试 → 复锁
sudo chattr -i ~/.openclaw/workspace/scripts/nightly-security-audit.sh
# 修改脚本...
bash ~/.openclaw/workspace/scripts/nightly-security-audit.sh
sudo chattr +i ~/.openclaw/workspace/scripts/nightly-security-audit.sh
# 记录到当日 memory（黄线操作）
```

## risk-worker detailed notes

### Validation result (2026-03-13)

`risk-worker` was validated as an active isolation worker.

Confirmed:
1. Sandbox active: `mode=all`, `scope=session`, `workspaceAccess=none`, `sessionIsSandboxed=true`
2. Container actually created and running
3. Working directory inside sandbox: `/workspace`
4. Host workspace not directly accessible
5. Network isolation active
6. Main Telegram workflow unaffected

Conclusion: `risk-worker` currently meets the design goal of default-no-network, default-no-real-workspace, isolated execution.

### Good fit for risk-worker

- Initial processing of untrusted text/documents
- Low-privilege dry-runs of third-party skills
- Classification, extraction, and labeling of unknown material
- Repeatable processing that benefits from isolation
- Returning intermediate results for the main agent to finalize

Rule of thumb:
- **Process materials** → `risk-worker`
- **Make final decisions** → main agent

### Never delegate to risk-worker

- Real host config/credential reads or edits
- Auth/token/refresh-token/API-key/cookie/secret tasks
- Direct edits to main workspace or formal config changes
- Anything needing elevated shell, host browser, or messaging tools
- Final high-risk judgments, external replies, or formal ops work

Rule of thumb:
- **Secrets / auth / config / external actions** → main agent or human only

### Future limited-network conditions

Default: most networked tasks stay with the main agent.

Consider limited network only if all conditions hold:
1. Main-agent handling is meaningfully less safe
2. Task does not require host secrets/auth/main workspace writes
3. Network target is clearly bounded
4. Benefit is real and worth the added surface area
5. Isolation still keeps no secret access, no host browser control, and no outbound messaging

## Defense matrix

| Risk | Before | During | After |
|---|---|---|---|
| High-risk commands | ⚡ Red-line block | — | ✅ Audit report |
| Hidden-instruction poisoning | ⚡ Full-text audit | ⚠️ Same-UID risk | ✅ Process/network checks |
| Credential theft | ⚡ Exfiltration red line | ⚠️ Prompt-injection risk | ✅ DLP scan |
| Core config tampering | — | ✅ chmod 600 | ✅ SHA256 check |
| Audit system tampering | — | ✅ chattr +i | ✅ Script hash consistency |
| Trace removal | — | ⚡ Forced audit logging | ✅ Git backup |

Legend: ✅ hard control · ⚡ behavior rule (agent must comply) · ⚠️ known gap
