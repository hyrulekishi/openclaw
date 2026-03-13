# OpenClaw Backup Policy

根目录：`~/.openclaw/`

已确认策略：**方案 3（双轨）**
- `backup/git-sanitized/`：用于 Git 私有仓库，轻量、脱敏、可审查
- `backup/full-encrypted/`：用于本地完整加密备份，尽量完整
- **`session *.jsonl` 完全不进备份**
- `memory/`：**只进本地加密轨，不进 Git 轨**
- `identity/`：Git 轨**只保留 `device.json`**，排除 `device-auth.json`
- 自动化约定：**本地加密自动执行，Git 轨只自动生成，不自动 push**
- `sandbox worker`：列入下一阶段事项，不在当前主 agent 上直接启用全局 sandbox

---

## 目录约定

- Git 轨：`~/.openclaw/backup/git-sanitized/`
- 本地加密轨：`~/.openclaw/backup/full-encrypted/`

---

## 轨 A：Git 私有仓库备份

目标：
- 可版本管理
- 可人工审查
- 不直接包含高敏感运行态和噪音文件

### 纳入

```text
openclaw.json            # 脱敏版
workspace/
agents/main/agent/       # 脱敏版
cron/
identity/device.json     # 必要时脱敏
.config-baseline.sha256
README-backup.md
.gitignore
```

### 排除

```text
.env
credentials/
devices/paired.json
devices/pending.json
agents/main/sessions/
logs/
canvas/
completions/
sandboxes/
telegram/
openclaw.json.bak*
*.tmp
*.lock
*.reset.*
update-check.json
exec-approvals.json
```

---

## 轨 B：本地完整加密备份

目标：
- 真正灾备恢复
- 尽量保留关键状态
- 排除明显可重建、脏运行态和高噪音文件

### 纳入

```text
openclaw.json
.env
workspace/
agents/
cron/
credentials/
identity/
devices/paired.json
memory/
.config-baseline.sha256
```

### 排除

```text
agents/*/sessions/*.jsonl
agents/*/sessions/*.lock
agents/*/sessions/*.reset.*
devices/*.tmp
logs/
canvas/
completions/
sandboxes/
telegram/
openclaw.json.bak*
*.tmp
update-check.json
exec-approvals.json
```

---

## 恢复原则

### 从 Git 轨恢复
适用于：
- 恢复工作区、技能、配置结构
- 审查配置变化
- 快速重建非敏感部分
- 自动生成后由你人工 review，再决定是否 push 到私有仓库

### 从本地加密轨恢复
适用于：
- 机器损坏或配置严重损坏后的完整灾备
- 恢复真实凭证、identity、paired 信息与 memory 数据

恢复后建议：
1. 检查关键文件权限（尤其 `openclaw.json`、`auth-profiles.json`、`paired.json`、`.env`）
2. 如果恢复场景涉及潜在泄漏或入侵，优先轮换 token / key / refresh token
3. 验证 gateway、channels、skills、memory 是否正常

---

## 备注

- `session *.jsonl` 明确不进任何备份
- `logs/`、`sandboxes/`、`telegram/` 视为运行态缓存/临时状态，不纳入备份
- Git 轨默认只生成脱敏版本，不自动 push；真实 secret 仅保留在本地加密备份中
- `sandbox worker` 已列入下一阶段事项，待单独设计并落地
