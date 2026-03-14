# TOOLS.md - Local Notes

Skills define _how_ tools work. This file is for _your_ specifics — the stuff that's unique to your setup.

## What Goes Here

Things like:

- Camera names and locations
- SSH hosts and aliases
- Preferred voices for TTS
- Speaker/room names
- Device nicknames
- Anything environment-specific

## Examples

```markdown
### Cameras

- living-room → Main area, 180° wide angle
- front-door → Entrance, motion-triggered

### SSH

- home-server → 192.168.1.100, user: admin

### TTS

- Preferred voice: "Nova" (warm, slightly British)
- Default speaker: Kitchen HomePod
```

## Why Separate?

Skills are shared. Your setup is yours. Keeping them apart means you can update skills without losing your notes, and share skills without leaking your infrastructure.

---

Add whatever helps you do your job. This is your cheat sheet.

---

## Messaging / Media Delivery

### Telegram image sending

- OpenClaw 文档显示 Telegram 渠道支持带媒体的消息发送。
- 已确认存在正规发送路径：
  - CLI：`openclaw message send --channel telegram --target <chatId> --media <path-or-url> [--message <caption>]`
  - 渠道文档还提到 Telegram 发送动作支持 `sendMessage`，可带 `mediaUrl`。
- 结论：当当前任务明确要求“生成图片并发给我”时，应优先使用 OpenClaw 自带的正规媒体发送路径，而不是自行调用 Telegram HTTP API。

### 任务约定：生成结果默认发送

- 对 **明确要求产出图片/音频/文件并发给用户** 的任务：
  - 如果 OpenClaw 当前存在正规附件发送路径，**生成完成后默认直接发送给 Erika**，不需要每次再询问。
  - 仅在以下情况改为先确认：
    - 文件明显敏感
    - 接收对象不是当前直接对话用户
    - 当前发送路径不明确或不合规
- 对仅要求“测试是否可生成/可导出”的任务，默认仍可先验证，不主动发送，除非任务中明确要求交付成品。
