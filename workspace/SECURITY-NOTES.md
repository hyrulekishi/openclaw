# SECURITY-NOTES.md

> 本文件是安全规范的补充参考，不在每次会话自动加载，按需读取。
> 核心执行规则在 AGENTS.md 中，本文件存放背景说明、已知局限和简报示例。

---

## 已知局限性

1. **Agent 认知层脆弱性**：精心构造的复杂文档可绕过行为规范。Human-in-the-loop 是最后防线
2. **同 UID 读取**：OpenClaw 以当前用户运行，`chmod 600` 无法阻止同用户读取，彻底隔离需容器化
3. **哈希基线非实时**：每晚才校验，最长约 24h 发现延迟
4. **WSL2 mirrored 网络**：Windows 侧网络变化（如 Clash 规则）直接影响 WSL2 连接行为
5. **巡检推送依赖外部 API**：Telegram 偶发故障会导致推送失败，报告始终保存本地

---

## 巡检简报格式示例

```
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
13. 灾备备份:     ✅ 已自动推送至私有仓库

📝 详细报告已保存：/tmp/openclaw/security-reports/report-YYYY-MM-DD.txt
```

---

## 巡检脚本维护流程

```bash
# 解锁 → 修改 → 测试 → 复锁
sudo chattr -i ~/.openclaw/workspace/scripts/nightly-security-audit.sh
# 修改脚本...
bash ~/.openclaw/workspace/scripts/nightly-security-audit.sh
sudo chattr +i ~/.openclaw/workspace/scripts/nightly-security-audit.sh
# 记录到当日 memory（黄线操作）
```

---

## 防御矩阵

| 风险场景 | 事前 | 事中 | 事后 |
|---|---|---|---|
| 高危命令直调 | ⚡ 红线拦截 | — | ✅ 巡检简报 |
| 隐性指令投毒 | ⚡ 全文本审计 | ⚠️ 同UID风险 | ✅ 进程/网络监测 |
| 凭证窃取 | ⚡ 外发红线 | ⚠️ 提示词注入风险 | ✅ DLP扫描 |
| 核心配置篡改 | — | ✅ chmod 600 | ✅ SHA256校验 |
| 巡检系统破坏 | — | ✅ chattr +i | ✅ 脚本哈希一致性 |
| 操作痕迹抹除 | — | ⚡ 强制审计日志 | ✅ Git灾备 |

图例：✅ 硬控制 · ⚡ 行为规范（依赖Agent配合）· ⚠️ 已知缺口
