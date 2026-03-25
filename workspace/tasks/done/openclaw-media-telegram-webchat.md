# OpenClaw 媒体传输专项排查（Telegram / WebChat）

- 状态：done
- 结论：在用户 VPN 正常的前提下，Telegram 图片/文件双向收发正常，可视为当前可用媒体通道。
- 备注：WebChat 媒体链路未继续验证，暂不视为可靠通道。
- 如再异常：优先复核 gateway 日志中的 media / attachment / telegram 项。
- 最近更新：2026-03-25
