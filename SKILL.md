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
  ├─ 是 → 使用 Gemini 结果生成 sections ✅
  └─ 否 → 降级到字幕分析
  ↓
为每个段落提取多张候选截图（ffmpeg）
  ↓
按质量 + 语义筛选最佳截图
  ↓
生成单文件 HTML（时间戳可点击跳转原视频）
  ↓
保存到桌面 → 按需发送给用户
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

#### 3. 提取候选截图（必做）
不要每个段落只截一张起始帧。必须从每个 section 的时间范围内提取多张候选截图，至少覆盖该段的前、中、后几个位置。

示例：
```bash
ffmpeg -ss HH:MM:SS -i /tmp/video.mp4 \
       -update 1 -frames:v 1 -q:v 2 /tmp/section_001_cand_01.jpg
```

#### 4. 筛选最佳截图（必做）
必须从候选截图中筛出每个 section 最合适的一张，不能直接默认使用第一张。筛选时同时考虑：

- **画面质量**：过滤黑场、转场、模糊帧、主体缺失、信息量过低、字幕遮挡严重的帧
- **内容相关性**：结合分段标题、content、tips 判断截图是否符合该段重点
- **动作代表性**：如果是动作示范/训练动作类段落，优先选动作最典型、姿态最清晰的一帧
- **主题匹配**：如果是访谈/理念/方法论段落，优先选最能体现该主题的画面，而不是机械寻找动作截图

优先方案：使用 Gemini 或其他视觉模型做多图比较和语义筛选。

#### 5. 回退策略（必做）
如果 Gemini 的视觉筛图不可用（如 503、配额、网络问题），允许降级到本地规则筛选，但必须满足：

- 仍然保留多候选截图流程
- 仍然做基础质量过滤
- 仍然输出最终 HTML
- 在运行说明中明确标注这是回退模式

#### 6. 生成 HTML（必做）
基于 Gemini 的分析结果和筛选后的最佳截图生成文档。

HTML 必须满足：

- 每个 section 的时间戳必须可点击
- 点击后跳转到原视频对应时间（YouTube 使用 `?t=` 或 `&t=` 参数）
- 最终优先生成**单文件 HTML**，截图应使用 base64 内嵌，避免引用 `/tmp` 等临时路径导致图片失效
- 最终成品 HTML 中**不要**显示“截图选择理由”或内部筛选解释

#### 7. 结果说明（推荐）
给用户的结果说明中，推荐额外说明：

- 本次是否使用了可点击时间戳
- 本次截图是 Gemini 语义筛图，还是回退规则筛图
- 如果你愿意，也可以简短说明某些段落为什么选那张图

> 注意：这些推荐说明写在 agent 回复里即可，**不要写进最终 HTML 成品里**。

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

## 输出要求

### 必做

- 必须尊重视频原有结构；有 Chapters 时按 Chapters，总结结构不能机械套模板
- 必须先下载本地视频，再上传到 Gemini，不能直接把 YouTube URL 交给 Gemini 分析
- 必须为每个 section 提取多张候选截图，不能只截一张起始帧
- 必须对候选截图做质量过滤和语义筛选
- 必须生成可点击时间戳，并跳转到原视频对应时间
- 必须优先输出单文件 HTML，图片使用 base64 内嵌，避免临时路径失效

### 推荐

- 推荐在运行说明中标注本次使用的是 Gemini 语义筛图还是回退规则筛图
- 推荐在运行说明中说明截图筛选的大致依据
- 推荐在回退模式下明确提示结果质量可能不如 Gemini 视觉筛选

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
- 如果连视觉筛图也进入回退模式，截图相关性和代表性可能不如 Gemini 语义筛选

## 全局可用性

此 skill 位于 `~/.openclaw/skills/fitness-video-summary/`，**所有 agent 都可以调用**。
