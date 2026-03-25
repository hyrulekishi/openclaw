# 小红书 MCP 接入与发布验证

## 目的

沉淀当前机器上可复用的小红书 MCP 接入方式，避免以后每次都从头排查。

## 当前可用方案

### 接入链路
- `mcporter` 配置名：`xiaohongshu`
- MCP 地址：`http://localhost:18060/mcp`
- 当前配置文件：`/home/user/.openclaw/workspace/config/mcporter.json`

### 后端实现
当前已验证：**不必依赖 Docker**，可直接使用本地 Linux 二进制常驻运行。

本地安装目录：
- `/home/user/.openclaw/tools/xiaohongshu-mcp/`

二进制文件：
- `xiaohongshu-mcp-linux-amd64`
- `xiaohongshu-login-linux-amd64`

来源：
- `xpzouying/xiaohongshu-mcp`
- Linux amd64 release 包可直接下载解压使用

## 已验证流程

1. 下载并解压 Linux 二进制版到本地目录
2. 直接运行 `xiaohongshu-mcp-linux-amd64`
3. 服务监听 `:18060`
4. `mcporter list` 可识别 `xiaohongshu` 为 `ok`
5. 通过 `get_login_qrcode` 获取登录二维码
6. 扫码登录后，`check_login_status` 返回 `✅ 已登录`

## 登录与可见性经验

- 二维码在当前 webchat 界面中不一定能稳定显示
- 更稳的做法是把二维码图片导出到本地文件，再在本机打开
- 本次实践中，将二维码落到 Windows 桌面后可顺利扫码登录

## 发布验证

已完成多次图文发布测试：
- 类型：图文
- 图片：已验证单图、4图，以及 3 张散图组合发布
- 状态：MCP 均可返回 `发布完成`
- 问题：未稳定返回 PostID，后续通过搜索反查结果不稳定、容易超时

### 已验证的发布实践
- 对带明显底部水印的图片，先本地小幅裁掉底部再发，流程可用
- 多图可按指定顺序发布（例如 3 → 2 → 1）
- 对散图/混风格图片，正文可以极短，甚至只保留一句感觉锚点

## 当前结论

- 小红书 MCP 本地二进制方案可用
- Docker 不是必需项
- 登录链路可用
- 发布链路可用
- 但发布后的回查能力目前不稳定，不应假设每次都能立即通过搜索确认
- **正文研究/竞品采样时，优先用 `list_feeds()` 首页流，再接 `get_feed_detail()`**
- **当前已确认：`search_feeds()` 可以拿到搜索卡片，但用其返回结果再调用 `get_feed_detail()` 时，存在 `feed not found in noteDetailMap` 的不稳定问题**
- 因此：
  - 看标题/互动趋势 → `search_feeds()` 仍可参考
  - 抓正文/评论/图片详情 → 优先 `list_feeds()` → `get_feed_detail()`

## 后续建议

- 若只是发布内容：当前方案已可实际使用
- 若需要稳定运营/复查：后续应补一套“发布后核验”流程
- 建议把关键发布素材与文案同时保存在本地，避免只依赖平台侧可见性反馈
