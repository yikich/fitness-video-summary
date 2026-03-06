---
name: fitness-video-summary
description: 自动总结健身教学视频，检测YouTube Chapters，提取要点和截图，生成结构化HTML文档。支持有字幕和硬字幕的视频。适用于YouTube健身视频，包括训练计划、技巧讲解、分析讲座等内容。
---

# Fitness Video Summary

自动化健身视频总结工具，将YouTube健身教学视频转换为结构化的HTML文档。

## 🎯 核心原则

### 尊重视频的原有结构

**不要把所有视频都当成"动作列表"来处理！**

- 有些视频是按多个训练动作组织的（如"5个最佳跳跃力训练"）
- 有些视频是围绕一个主题展开的（如"深蹲的好处及各种变式"）
- 有些视频是技术分析类（如"为什么你的深蹲不对"）

**总结报告的结构应该跟随视频本身的组织方式，不能机械化地套用"动作1、动作2..."模板。**

## ⚠️ YouTube Chapters 优先

很多YouTube视频有创作者自己划分的 **Chapters**（分段标记）。
如果视频有 Chapters，**必须按 Chapters 来组织总结内容**，因为这是创作者有意为之的节奏。

### 检测方式
```bash
# 用 yt-dlp --dump-json 获取 chapters
yt-dlp --dump-json --skip-download "VIDEO_URL" | python3 -c "
import json, sys
data = json.loads(sys.stdin.read())
chapters = data.get('chapters', [])
print(json.dumps(chapters, indent=2))
"
```

返回格式：
```json
[
  {"start_time": 0.0, "title": "Introduction", "end_time": 81.0},
  {"start_time": 81.0, "title": "Benefits of Squatting", "end_time": 129.0}
]
```

## 工作流程

### 决策流程

```
开始
  ↓
清理 /tmp 目录
  ↓
获取视频信息 + 检测 Chapters
  ↓
下载视频到本地 (yt-dlp)
  ↓
上传本地视频到 Gemini（client.files.upload）
  ↓
有 Chapters？
  ├─ 是 → 把 Chapters 传给 Gemini，要求按 Chapter 逐段总结
  └─ 否 → 让 Gemini 自行识别视频结构并分段
  ↓
Gemini 成功？
  ├─ 是 → 使用 Gemini 结果生成 HTML ✅
  └─ 否 → 降级到字幕分析
  ↓
为每个段落提取截图（ffmpeg）
  ↓
生成 HTML → 保存到桌面 → 发送邮件
```

### 🌟 推荐流程：Gemini 优先

#### 1. 清理旧文件（必须！）
```bash
rm -f /tmp/video*.* /tmp/exercise_*.jpg /tmp/section_*.jpg /tmp/*_video.* /tmp/*.srt
```

#### 2. 下载并使用 Gemini 分析视频

> ⚠️ **关于 YouTube URL 的严重警告**
>
> Gemini API 直接传入 `file_uri='YOUTUBE_URL'` 存在**非常严重的"幻觉"Bug**。
>
> **唯一靠谱的方案：先下载到本地，然后再用 `client.files.upload` 传给 Gemini！**

```python
from google import genai
import time
import os

client = genai.Client(api_key=os.environ.get('GEMINI_API_KEY', 'YOUR_API_KEY'))

video_path = "/tmp/video.mp4"

print("上传视频中...")
uploaded_file = client.files.upload(file=video_path)

print("等待服务器处理...")
while uploaded_file.state.name == "PROCESSING":
    time.sleep(2)
    uploaded_file = client.files.get(name=uploaded_file.name)

# prompt 根据是否有 chapters 而不同
# 有 chapters: 把 chapter 列表传入，要求按 chapter 逐段总结
# 无 chapters: 让 Gemini 自行识别视频结构

response = client.models.generate_content(
    model='gemini-2.5-flash',
    contents=[uploaded_file, prompt]
)

print(response.text)

# 务必清理服务器上的文件
client.files.delete(name=uploaded_file.name)
```

#### 3. 提取截图
从已下载的本地视频中提取截图：
```bash
ffmpeg -ss HH:MM:SS -i /tmp/video.mp4 \
       -update 1 -frames:v 1 -q:v 2 /tmp/section_001.jpg
```

#### 4. 生成 HTML
基于 Gemini 的分析结果生成文档

---

### 🔄 备选流程：字幕文件分析

**仅在以下情况使用：**
- ❌ Gemini API 配额超限
- ❌ Gemini 分析失败
- ❌ 网络问题无法访问 Gemini

## 数据模型：Sections（段落）

使用灵活的 `sections` 结构，**不是**固定的 `exercises`：

```json
{
  "title": "视频标题",
  "summary": "视频简要概述",
  "sections": [
    {
      "title": "段落标题（来自 Chapter 或 Gemini 识别）",
      "time_str": "MM:SS",
      "timestamp": 90,
      "content": ["要点1", "要点2", "要点3"],
      "tips": "注意事项"
    }
  ],
  "overall_advice": "整体建议"
}
```

## HTML 样式规范

### 固定配色方案（柔和运动风）

```css
/* 背景渐变 - 深蓝色 */
background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);

/* 主标题 - 橙色渐变 */
background: linear-gradient(135deg, #ff6b35 0%, #f7931e 100%);
border-bottom: 3px solid #ff6b35;

/* 视频信息框 - 深蓝 + 米白文字 */
background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
color: #f5f5f5;

/* 简介/建议框 - 橙色 + 米白文字 */
background: linear-gradient(135deg, #ff9a56 0%, #ff6b35 100%);
color: #f5f5f5;

/* 关键要点框 - 淡紫灰 */
background: linear-gradient(135deg, #e8eaf6 0%, #c5cae9 100%);
border-left: 5px solid #1e3c72;

/* 时间戳按钮 - 橙色 + 米白文字 */
background: linear-gradient(135deg, #ff6b35 0%, #f7931e 100%);
color: #f5f5f5;
```

**不要使用：**
- ❌ 纯白色文字（#ffffff）→ 太亮，刺眼
- ❌ 粉色系渐变 → 不适合健身主题
- ❌ 黄色背景 + 白字 → 对比度太高

## 输出位置

保存到用户桌面：
```
~/Desktop/[视频主题]_训练总结.html
```

## Gemini 配置

### 安装依赖
```bash
pip3 install --break-system-packages google-genai
```

> ⚠️ 包名是 `google-genai`（新版），不是 `google-generativeai`（旧版）

### 配置 API Key
```bash
export GEMINI_API_KEY="your-api-key-here"
```

### 可用模型
- `gemini-2.5-flash` - 推荐，速度快，配额高
- `gemini-2.5-pro` - 更强大，但配额较低

## 故障排查

### 生成的 HTML 没有文字总结内容？

如果 HTML 中只有占位符（如"段落 1"、"训练内容 1"），说明 **Gemini 分析失败**，脚本走了降级路径。

检查运行日志中的 `⚠️ [GEMINI 失败原因]` 行：

| 错误信息 | 原因 | 修复方法 |
|----------|------|----------|
| `google-genai 包未安装` | 缺少依赖 | `pip3 install --break-system-packages google-genai` |
| `GEMINI_API_KEY 未设置` | 环境变量缺失 | `export GEMINI_API_KEY='your-key'` |
| `视频文件不存在` | 下载失败 | 检查网络和 yt-dlp 版本 |
| `JSON 解析失败` | Gemini 返回格式异常 | 查看 `/tmp/gemini_analysis_raw.txt` |
| `ResourceExhausted` | API 配额超限 | 等待配额重置或换 API Key |

> ⚠️ **重要**：agent 在使用此 skill 前必须确保 `GEMINI_API_KEY` 环境变量已正确设置！

### 字幕降级模式的限制

当 Gemini 不可用时，脚本会从字幕中提取文字内容。但字幕降级模式有以下限制：
- 自动字幕质量参差不齐，可能有错字
- 无法像 Gemini 那样理解视频画面内容
- 段落标题会使用字幕原文而非优化后的标题

## 全局可用性

此 skill 位于 `~/.openclaw/skills/fitness-video-summary/`，**所有 agent 都可以调用**。
