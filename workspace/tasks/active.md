# Active Tasks

## LoRA_Easy_Training_Scripts → WSL 安装 + Runpod GUI Docker 镜像
- 状态：暂存中 / 待继续
- 来源：用户希望在本地 WSL 评估并准备 `67372a/LoRA_Easy_Training_Scripts`，最终做成可 push 的 Docker image，供 Runpod 等云 GPU 平台直接 pull 使用，且最好带 GUI
- 当前结论：
  - 项目本体是 **PySide6 桌面 GUI**，不是 Web UI
  - Linux 文档主推 Python 3.11，但代码检查看起来**未严格限制死 3.11**，本机 Python 3.12.3 也值得尝试
  - 当前 WSL Ubuntu 已确认 GPU 透传可用，`/usr/lib/wsl/lib/nvidia-smi` 可识别 RTX 3080 Ti Laptop GPU
  - 当前 Ubuntu 发行版里 `docker` CLI 还不可用，后续需确认 Docker Desktop integration
  - Runpod 社区/官方常见 GUI 方案是 **Desktop Template / KasmVNC / noVNC / 浏览器远程桌面**，因此目前推荐路线是**保留现有 PySide6 GUI**，而不是重写整套前端
- 下一步：
  1. 检查并打通当前 Ubuntu WSL 对 Docker Desktop 的 integration
  2. 在 KasmVNC / noVNC 之间选更合适的 GUI 容器方案
  3. 设计 Runpod 用 Dockerfile（CUDA 基础镜像、Python 版本策略、桌面环境、Qt 依赖、项目安装与启动）
  4. 本地验证 GUI 可启动后，再准备 push 与 Runpod 部署
- 阻塞点：
  - 当前 Ubuntu WSL 内 `docker` / `docker compose` 命令不可用
  - 尚未验证该项目在 Python 3.12 下的实际安装兼容性
- 最近更新：2026-03-19

## 小红书生图模块（Doubao）
- 状态：进行中
- 目标：给参考图做改图/生图，先走豆包/在线链路，后续再扩展本地 ComfyUI / SD。
- 当前进度：
  - 已安装 `skills/doubao-img`
  - browser 配置已开启
  - `cdpPort=18800` 当前未监听，豆包链路尚未实测跑通
- 下一步：
  1. 确认可 attach 的浏览器 session / CDP
  2. 验证豆包登录态与实际出图
  3. 接入“返回候选图→挑选→裁剪→发布”流程
- 最近更新：2026-03-25

## Windows 训练进度查询脚本
- 状态：已完成首版
- 来源：用户希望我在被问到“最新/当前项目进度”时，优先自动查询当前正在训练的项目，也支持按名称查询
- 已完成：
  - 新增脚本：`scripts/check_train_progress.py`
  - 默认行为：不传参数时自动读取当前训练进程对应的 `config.toml`，并查询当前项目
  - 可选行为：支持 `--name <output_name>` 查询指定项目
  - 输出内容：项目名、step/total、百分比、avr_loss、ETA、status
  - 已实测：当前 `waifu_I20` 可正常返回进度
- 用法：
  1. 当前项目：`python3 scripts/check_train_progress.py`
  2. 指定项目：`python3 scripts/check_train_progress.py --name waifu_I20`
  3. JSON：`python3 scripts/check_train_progress.py --json`
- 后续可选增强：
  1. 做一个更短的 shell 包装命令
  2. 支持从更多训练后端/日志格式提取进度
  3. 加入最近一次 sample/save checkpoint 信息
  4. 完善 Windows shared VRAM / per-process GPU memory 采集兼容性
- 最近更新：2026-03-24

