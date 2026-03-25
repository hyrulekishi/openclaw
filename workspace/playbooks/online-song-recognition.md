# 在线识曲 / 听歌识曲

## 目的

整理那些“不大到要建项目，但以后还会反复用到”的在线识曲方案与经验。

## 当前结论

### 常见在线方案

- **ACRCloud**
  - 商用品里比较常见
  - 适合正式接入
- **AudD**
  - API 简单
  - 适合快速接入
- **Shazam（非官方链路居多）**
  - 识别能力强
  - 但正式产品不建议依赖非官方接口
- **SongFromReel**
  - 适合从 Instagram Reel 链接直接识别歌曲
  - 这次实测能工作

## 本次实测

### 来源
- 用户给出 B 站视频：`https://www.bilibili.com/video/BV1m8zVBmE2u/`
- 页面中可见原始来源指向 Instagram Reel：`https://www.instagram.com/reel/DNRpkpltz5F/`

### 处理过程
- 直接抓 B 站元数据时，`yt-dlp` 返回 403
- 从页面内容中找到了 Instagram 原始链接
- 使用在线识别站 `SongFromReel` 的实际接口完成识别

### 识别结果
- 歌名：`#ChooseYourCharacter (The Original)`
- 歌手：`Jim Walter`
- Shazam：`https://www.shazam.com/track/460903024/chooseyourcharacter-the-original`

## 可复用经验

1. B 站短视频/搬运内容不一定容易直接抽音频
2. 如果页面里能看到原始平台链接，优先回源
3. Reel 类短视频可以优先尝试“链接直识别”方案，而不是先下载音频再跑本地识别
4. 这类内容不需要建独立项目，但值得保留成 playbook，方便以后复用
