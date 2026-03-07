# fitness-video-summary

将 YouTube 健身教学视频总结为结构化 HTML 文档的 OpenClaw skill。

它会尽量按视频原本结构来整理内容：
- 如果视频有 **YouTube Chapters**，优先按 Chapters 总结
- 如果没有 Chapters，则根据内容逻辑自动分段
- 为每个段落提取候选截图，并选择更有代表性的画面
- 输出带有**可点击时间戳**的单文件 HTML，方便回看原视频

## 适用场景

适合这类视频：
- 健身动作教学
- 训练计划解析
- 技术讲解 / 动作纠错
- 训练原理、恢复、热身、拉伸类内容
- 健身博主长视频总结

## 仓库内容

- `SKILL.md`：skill 说明与使用规范
- `scripts/summarize_fitness_video.py`：主脚本，负责下载、转写分析、分段和生成 HTML
- `scripts/extract_best_frame.py`：基础多帧采样截图
- `scripts/extract_smart_frame.py`：基于 OCR 的截图选择
- `scripts/extract_vision_frame.py`：基于视觉模型的截图选择

## 工作流程

1. 使用 `yt-dlp` 获取视频信息和 Chapters
2. 下载视频与字幕到本地临时目录
3. 优先用 Gemini 基于字幕/视频进行结构化总结
4. 如果失败，则回退到本地字幕分析
5. 为每个 section 提取多张候选截图
6. 生成单文件 HTML，并把截图内嵌为 base64
7. 保存到桌面，并可选通过 macOS Mail 发送

## 依赖

建议环境：macOS + Python 3.11+

需要安装：

```bash
brew install yt-dlp ffmpeg tesseract
pip3 install --break-system-packages google-genai
```

## 环境变量

### 必需

```bash
export GEMINI_API_KEY="your-gemini-api-key"
```

### 可选（视觉截图分析）

```bash
export CODEFLOW_API_KEY="your-codeflow-api-key"
export CODEFLOW_API_BASE="https://codeflow.asia"
```

如果未设置 `CODEFLOW_API_KEY`，视觉截图分析脚本会返回失败，你可以改用其他截图脚本或让主流程自动回退。

## 使用方式

直接运行主脚本：

```bash
python3 scripts/summarize_fitness_video.py "https://www.youtube.com/watch?v=VIDEO_ID"
```

输出文件默认保存在：

```bash
~/Desktop/[视频标题]_训练总结.html
```

## 设计原则

- 尊重视频原始结构，不强行套动作列表模板
- 有 Chapters 时优先按 Chapters 组织
- 优先本地下载后再做分析，避免直接把 YouTube URL 丢给模型造成幻觉
- 截图不能只取起始帧，应进行多候选筛选
- 最终 HTML 应可离线打开，图片不依赖临时路径

## 已清理的敏感信息

这个仓库在整理发布前，已移除一处**硬编码 API key**：

- `scripts/extract_vision_frame.py` 中原本写死的 `x-api-key`

现在已改为通过环境变量读取：

- `CODEFLOW_API_KEY`
- `CODEFLOW_API_BASE`（可选）

这样做的目的：
- 避免把真实密钥提交到 GitHub
- 让仓库可以公开分享
- 让不同环境用各自的凭证配置

## 注意事项

- `send_email()` 目前使用 macOS `Mail` + AppleScript，非 macOS 环境需要自行替换
- Gemini 配额不足时会自动回退，但结果质量可能下降
- 自动字幕本身可能带来错字或误识别
- 视觉截图质量会受视频清晰度、字幕遮挡和动作节奏影响

## License

暂未指定。若准备公开给他人使用，建议补充 MIT 或 Apache-2.0。
