#!/usr/bin/env python3
"""
健身视频总结工具 - 主执行脚本
自动下载YouTube视频、检测chapters、智能截图并生成HTML文档

核心逻辑：
1. 检测视频是否有 YouTube Chapters
2. 有 chapters → 按 chapter 结构让 Gemini 逐段总结
3. 无 chapters → 让 Gemini 自行识别视频结构并分段
4. 数据模型为 "sections"（灵活的段落），不是固定的 "exercises"
"""

import subprocess
import re
import os
import sys
import json
import base64
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = Path(__file__).parent

def clean_temp_files():
    """清理临时文件"""
    temp_patterns = [
        "/tmp/video.*",
        "/tmp/exercise_*.jpg",
        "/tmp/section_*.jpg",
        "/tmp/*_video.*",
        "/tmp/*.jpg",
        "/tmp/temp_frame_*.jpg"
    ]
    for pattern in temp_patterns:
        subprocess.run(f"rm -f {pattern}", shell=True, capture_output=True)
    print("✓ 清理临时文件完成")

def download_video_and_subtitles(video_url):
    """下载视频和字幕"""
    print(f"正在下载视频: {video_url}")

    # 下载字幕
    print("  - 下载字幕...")
    subtitle_cmd = [
        "yt-dlp",
        "--skip-download",
        "--write-auto-sub",
        "--sub-lang", "en,zh-Hans,zh-Hant",
        "--convert-subs", "srt",
        "--ignore-errors",
        "--output", "/tmp/video",
        video_url
    ]
    subprocess.run(subtitle_cmd, capture_output=True)

    # 下载视频
    print("  - 下载视频文件...")
    video_cmd = [
        "yt-dlp",
        "-f", "bestvideo[height<=480]+bestaudio/best[height<=480]",
        "--output", "/tmp/video.%(ext)s",
        "--merge-output-format", "mp4",
        video_url
    ]
    result = subprocess.run(video_cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"错误: 视频下载失败\n{result.stderr}")
        return False

    print("✓ 视频和字幕下载完成")
    return True

def get_video_info(video_url):
    """获取视频信息"""
    cmd = [
        "yt-dlp",
        "--print", "%(title)s|||%(duration)s|||%(id)s",
        video_url
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        parts = result.stdout.strip().split("|||")
        return {
            "title": parts[0] if len(parts) > 0 else "未知标题",
            "duration": int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0,
            "video_id": parts[2] if len(parts) > 2 else ""
        }
    return {"title": "未知标题", "duration": 0, "video_id": ""}

def get_video_chapters(video_url):
    """获取视频的 YouTube Chapters"""
    print("  检测 YouTube Chapters...")
    cmd = [
        "yt-dlp",
        "--dump-json",
        "--skip-download",
        video_url
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        try:
            data = json.loads(result.stdout)
            chapters = data.get('chapters', [])
            if chapters:
                print(f"  ✓ 检测到 {len(chapters)} 个 Chapters:")
                for ch in chapters:
                    start = int(ch['start_time'])
                    mm, ss = start // 60, start % 60
                    print(f"    {mm:02d}:{ss:02d} - {ch['title']}")
                return chapters
        except (json.JSONDecodeError, KeyError):
            pass
    print("  - 没有检测到 Chapters")
    return []

def build_gemini_prompt(chapters, transcript):
    """根据是否有 chapters 构建不同的 Gemini prompt"""

    if chapters:
        # 有 chapters：按 chapter 结构要求 Gemini 逐段总结
        chapters_text = "\n".join([
            f"  - {int(ch['start_time'])//60:02d}:{int(ch['start_time'])%60:02d} {ch['title']}"
            for ch in chapters
        ])
        prompt = f"""请非常详细地分析这个健身视频的文稿，用中文写出完整的总结。

这个视频有以下分段（Chapters）：
{chapters_text}

以下是视频的完整字幕文稿：
{transcript}

请严格按照视频自身的 Chapters 结构来总结内容。每个 Chapter 作为一个 section。
请按以下 JSON 格式返回：

```json
{{
  "title": "视频的中文标题（如果原标题是英文，请翻译成中文）",
  "summary": "视频的详细概述（2-3句话，说清楚视频在讲什么、适合什么人群）",
  "sections": [
    {{
      "title": "段落的中文标题（如果 chapter 标题是英文，请翻译成中文，可以保留英文术语作为补充，如：深蹲的好处 (Benefits of Squatting)）",
      "time_str": "MM:SS",
      "timestamp": 秒数,
      "content": ["详细要点1", "详细要点2", "详细要点3", "详细要点4"],
      "tips": "注意事项或补充说明（如果有的话）"
    }}
  ],
  "overall_advice": "整体训练建议或总结（2-3句话）"
}}
```

⚠️ 严格要求：
1. 所有内容必须用**中文**书写，包括 title、summary、content、tips、overall_advice
2. 如果原视频文稿是英文的，必须将所有内容翻译成中文（专业术语可以中英对照，如"深蹲 (Squat)"）
3. sections 的数量和顺序必须严格对应上面列出的 Chapters
4. 每个 section 的 content 至少要有 **4-6 个要点**，要详尽地总结该段落的核心知识，不要太简略
5. content 每个要点要写成完整的句子（15-30字），不要只写几个词
6. time_str 格式为 MM:SS（如 01:30），timestamp 为对应的总秒数（如 90）
7. 请确保返回有效的 JSON，只返回 JSON，不要有其他内容"""
    else:
        # 无 chapters：让 Gemini 自行判断视频结构
        prompt = f"""请非常详细地分析这个健身视频的文稿，用中文写出完整的总结。

以下是视频的完整字幕文稿：
{transcript}

请根据视频的实际内容结构来组织总结。
- 如果视频是按多个不同的训练动作来组织的，就按动作分段
- 如果视频是围绕一个主题展开讲解的（比如某个动作的技术分析、训练原理等），就按视频的逻辑结构分段
- 不要强行按"动作1、动作2"来拆分，要尊重视频本身的叙述结构

请严格按以下 JSON 格式返回：

```json
{{
  "title": "视频的中文标题（如果原标题是英文，请翻译成中文）",
  "summary": "视频的详细概述（2-3句话，说清楚视频在讲什么、适合什么人群）",
  "sections": [
    {{
      "title": "段落的中文标题（专业术语可以中英对照，如：深蹲 (Squat)）",
      "time_str": "MM:SS",
      "timestamp": 秒数,
      "content": ["详细要点1", "详细要点2", "详细要点3", "详细要点4"],
      "tips": "注意事项或补充说明（如果有的话）"
    }}
  ],
  "overall_advice": "整体训练建议或总结（2-3句话）"
}}
```

⚠️ 严格要求：
1. 所有内容必须用**中文**书写，包括 title、summary、content、tips、overall_advice
2. 如果原视频文稿是英文的，必须将所有内容翻译成中文（专业术语可以中英对照，如"深蹲 (Squat)"）
3. 每个 section 的 content 至少要有 **4-6 个要点**，要详尽地总结该段落的核心知识，不要太简略
4. content 每个要点要写成完整的句子（15-30字），不要只写几个词
5. time_str 格式为 MM:SS（如 01:30），timestamp 为对应的总秒数（如 90）
6. 请确保返回有效的 JSON，只返回 JSON，不要有其他内容"""

    return prompt

def analyze_with_gemini(video_path, chapters, subtitles):
    """使用 Gemini API 分析字幕文本内容"""
    try:
        from google import genai
    except ImportError:
        print("  ⚠️ [GEMINI 失败原因] google-genai 包未安装")
        print("  修复方法: pip3 install --break-system-packages google-genai")
        print("  → 将降级到纯本地 Regex 字幕分析模式")
        return None

    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        print("  ⚠️ [GEMINI 失败原因] 环境变量 GEMINI_API_KEY 未设置")
        print("  修复方法: export GEMINI_API_KEY='your-api-key'")
        print("  → 将降级到纯本地 Regex 字幕分析模式")
        return None
    else:
        print(f"  ✓ GEMINI_API_KEY 已设置 (前8位: {api_key[:8]}...)")

    if not subtitles:
        print("  ⚠️ [GEMINI 失败原因] 没有提供字幕文本进行分析")
        print("  → 我们将尝试回退到上传原视频进行分析的昂贵模式...")
        return fallback_analyze_video_with_gemini(video_path, chapters)

    print(f"  准备使用 Gemini 分析视频转写文稿 (低 Token 消耗模式)...")
    
    # 将字幕合并为长文本，带上时间戳增强上下文
    transcript_lines = []
    for sub in subtitles:
        if sub['text'].strip():
            transcript_lines.append(f"[{sub['time_str']}] {sub['text']}")
    transcript = "\n".join(transcript_lines)
    
    print(f"  ✓ 整理文稿完成，共 {len(transcript)} 个字符")

    prompt = build_gemini_prompt(chapters, transcript)

    client = genai.Client(api_key=api_key)

    try:
        print("  - 正在请求 Gemini API 分析文稿内容...")
        # 因为现在只是传文本，改用 gemini-2.5-flash 会非常快且便宜
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )

        result_text = response.text
        print(f"  ✓ Gemini 分析完成，返回 {len(result_text)} 字符")

        # 提取 JSON
        json_match = re.search(r'```json\s*(.+?)\s*```', result_text, re.DOTALL)
        if json_match:
            result_text = json_match.group(1)
        else:
            json_match = re.search(r'\{.+\}', result_text, re.DOTALL)
            if json_match:
                result_text = json_match.group(0)

        data = json.loads(result_text)
        sections = data.get('sections', [])
        print(f"  ✓ 解析到 {len(sections)} 个段落")

        # 保存原始分析结果
        with open('/tmp/gemini_analysis.txt', 'w', encoding='utf-8') as f:
            f.write(response.text)

        return data

    except json.JSONDecodeError as e:
        print(f"  ⚠️ [GEMINI 失败原因] 返回的 JSON 解析失败: {e}")
        with open('/tmp/gemini_analysis_raw.txt', 'w', encoding='utf-8') as f:
            f.write(result_text)
        print(f"  原始结果已保存到 /tmp/gemini_analysis_raw.txt")
        print(f"  → 将降级到纯本地 Regex 字幕分析模式")
        return None
    except Exception as e:
        print(f"  ⚠️ [GEMINI 失败原因] {type(e).__name__}: {e}")
        print(f"  → 将降级到纯本地 Regex 字幕分析模式")
        return None

def fallback_analyze_video_with_gemini(video_path, chapters):
    """(回退方案) 如果完全没有字幕，则上传完整原视频让 Gemini 分析 (消耗极大)"""
    try:
        import time
        from google import genai
        api_key = os.environ.get('GEMINI_API_KEY')
        client = genai.Client(api_key=api_key)
    except:
        return None

    if not Path(video_path).exists():
        print(f"  ⚠️ 视频文件不存在: {video_path}")
        return None
    else:
        file_size_mb = Path(video_path).stat().st_size / (1024 * 1024)
        print(f"  ✓ 视频文件存在: {video_path} ({file_size_mb:.1f} MB)")

    print(f"  ⚠️ 将使用昂贵的完整的视频上传模式...")

    # 在Fallback纯视频分析下，transcript 为空
    prompt = build_gemini_prompt(chapters, transcript="（无字幕，请直接基于视频画面和原生音频分析）")

    uploaded_file = None
    try:
        print("  - 正在上传视频到 Gemini 服务器...")
        uploaded_file = client.files.upload(file=video_path)
        print(f"  ✓ 上传完成 (URI: {uploaded_file.uri})")

        print("  - 等待视频处理...", end="", flush=True)
        while uploaded_file.state.name == "PROCESSING":
            print(".", end="", flush=True)
            time.sleep(2)
            uploaded_file = client.files.get(name=uploaded_file.name)
        if uploaded_file.state.name == "FAILED":
            raise Exception("Gemini 无法处理该视频。")
        print("\n  ✓ 视频准备就绪，开始分析内容...")

        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[uploaded_file, prompt]
        )

        result_text = response.text
        
        json_match = re.search(r'```json\s*(.+?)\s*```', result_text, re.DOTALL)
        if json_match:
            result_text = json_match.group(1)
        else:
            json_match = re.search(r'\{.+\}', result_text, re.DOTALL)
            if json_match:
                result_text = json_match.group(0)

        data = json.loads(result_text)
        return data

    except Exception as e:
        print(f"  ⚠️ [GEMINI 视频分析失败] {e}")
        return None
    finally:
        if uploaded_file:
            try:
                client.files.delete(name=uploaded_file.name)
                print("  - 已清理 Gemini 服务器上的视频缓存")
            except Exception:
                pass

def gemini_data_to_sections(gemini_data):
    """将 Gemini 分析结果转换为 sections 格式"""
    sections = []
    for sec in gemini_data.get('sections', []):
        time_str = sec.get('time_str', '00:00')
        # 确保 time_str 格式正确，转为 HH:MM:SS（用于 ffmpeg）
        parts = time_str.split(':')
        if len(parts) == 2:
            time_str_ffmpeg = f"00:{parts[0].zfill(2)}:{parts[1].zfill(2)}"
        elif len(parts) == 3:
            time_str_ffmpeg = f"{parts[0].zfill(2)}:{parts[1].zfill(2)}:{parts[2].zfill(2)}"
        else:
            time_str_ffmpeg = "00:00:00"

        sections.append({
            "title": sec.get('title', '未知段落'),
            "timestamp": sec.get('timestamp', 0),
            "time_str": time_str_ffmpeg,
            "time_str_display": sec.get('time_str', '00:00'),
            "content": sec.get('content', []),
            "tips": sec.get('tips', '')
        })
    return sections

def parse_subtitles():
    """解析字幕文件"""
    # yt-dlp 在没有 post-processor 的情况下会输出 .vtt 而不是 .srt
    subtitle_files = list(Path("/tmp").glob("video.*.srt")) + list(Path("/tmp").glob("video.*.vtt"))
    if not subtitle_files:
        print("警告: 未找到字幕文件")
        return []

    subtitle_file = subtitle_files[0]
    print(f"  - 解析字幕: {subtitle_file.name}")

    with open(subtitle_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # 兼容 SRT (00:00:00,000) 和 VTT (00:00:00.000) 格式的正则
    # 忽略前面的序号或其他内容，直接匹配时间戳和内容
    pattern = r'(\d{2}):(\d{2}):(\d{2})[.,]\d+ --> \d{2}:\d{2}:\d{2}[.,]\d+\n(.*?)(?=\n\n|\Z|\n\d{2}:)'
    matches = re.findall(pattern, content, re.DOTALL)

    subtitles = []
    for match in matches:
        hours, minutes, seconds = int(match[0]), int(match[1]), int(match[2])
        timestamp = hours * 3600 + minutes * 60 + seconds
        # 移除 <c> 等 vtt 标签
        text = re.sub(r'<[^>]+>', '', match[3])
        text = text.replace('\n', ' ').strip()
        
        if text:
            subtitles.append({
                "timestamp": timestamp,
                "time_str": f"{hours:02d}:{minutes:02d}:{seconds:02d}",
                "text": text
            })

    print(f"✓ 解析了 {len(subtitles)} 条字幕")
    return subtitles

def _merge_subtitle_texts(subtitles, start_ts, end_ts, max_points=6):
    """合并指定时间范围内的字幕文本，去重后分成有意义的要点"""
    texts = []
    seen = set()
    for sub in subtitles:
        if start_ts <= sub["timestamp"] < end_ts:
            text = sub["text"].strip()
            # 去掉重复的文本（自动字幕经常有重复）
            normalized = re.sub(r'\s+', ' ', text.lower())
            if normalized and normalized not in seen and len(text) > 3:
                seen.add(normalized)
                texts.append(text)

    if not texts:
        return []

    # 把短字幕合并成较长的句子（每个要点 30-80 字左右）
    merged = []
    current = ""
    for t in texts:
        if len(current) + len(t) < 80:
            current = (current + " " + t).strip() if current else t
        else:
            if current:
                merged.append(current)
            current = t
    if current:
        merged.append(current)

    return merged[:max_points]


def extract_sections_from_subtitles(subtitles):
    """从字幕中提取段落信息（降级方案）"""
    sections = []

    exercise_keywords = [
        r'第[一二三四五六七八九十\d]+个动作',
        r'动作[一二三四五六七八九十\d]+',
        r'exercise \d+',
        r'movement \d+',
        r'\d+\.\s*[A-Z]',
    ]

    for i, sub in enumerate(subtitles):
        text = sub["text"]
        for keyword in exercise_keywords:
            if re.search(keyword, text, re.IGNORECASE):
                sections.append({
                    "title": text[:50],
                    "timestamp": sub["timestamp"],
                    "time_str": sub["time_str"],
                    "time_str_display": f"{sub['timestamp']//60:02d}:{sub['timestamp']%60:02d}",
                    "content": [],
                    "tips": ""
                })
                for j in range(i + 1, min(i + 6, len(subtitles))):
                    sections[-1]["content"].append(subtitles[j]["text"])
                break

    # 如果没有找到明确的标记，按时间间隔分段，并从字幕提取真实内容
    if len(sections) < 2:
        print("  - 未找到明确段落标记，按时间分段并提取字幕内容...")
        if not subtitles:
            print("  ⚠️ 没有字幕数据可用，生成空内容")
            return [{
                "title": "视频内容",
                "timestamp": 0,
                "time_str": "00:00:00",
                "time_str_display": "00:00",
                "content": ["（字幕和 Gemini 分析均不可用，请观看原视频）"],
                "tips": ""
            }]

        duration = subtitles[-1]["timestamp"] if subtitles else 600
        num_segments = max(3, min(8, duration // 120))
        sections = []
        for i in range(num_segments):
            start_ts = int((duration / num_segments) * i)
            end_ts = int((duration / num_segments) * (i + 1))

            # 从该时间段的字幕中提取真实文字内容
            segment_content = _merge_subtitle_texts(subtitles, start_ts, end_ts)

            # 尝试从第一条内容生成更有意义的标题
            if segment_content:
                # 取第一句作为标题（截断到合理长度）
                first_text = segment_content[0]
                title = first_text[:40] + ("..." if len(first_text) > 40 else "")
            else:
                title = f"段落 {i + 1}"
                segment_content = [f"（该时间段无字幕内容）"]

            sections.append({
                "title": title,
                "timestamp": start_ts,
                "time_str": f"{start_ts // 3600:02d}:{(start_ts % 3600) // 60:02d}:{start_ts % 60:02d}",
                "time_str_display": f"{start_ts // 60:02d}:{start_ts % 60:02d}",
                "content": segment_content,
                "tips": ""
            })

    print(f"✓ 识别了 {len(sections)} 个段落")
    return sections

def extract_screenshot_smart(timestamp, output_path, section_title):
    """使用智能视觉分析提取截图"""
    vision_script = SCRIPT_DIR / "extract_vision_frame.py"

    if not vision_script.exists():
        print(f"    ⚠️  视觉分析脚本不存在，使用简单提取")
        return extract_screenshot_simple(timestamp, output_path)

    cmd = [
        "python3",
        str(vision_script),
        "/tmp/video.mp4",
        timestamp,
        output_path,
        section_title
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    print(result.stdout)

    return result.returncode == 0 and Path(output_path).exists()

def extract_screenshot_simple(timestamp, output_path):
    """简单截图提取（降级方案）"""
    video_files = list(Path("/tmp").glob("video.*"))
    video_files = [f for f in video_files if f.suffix in ['.mp4', '.webm', '.mkv'] and 'srt' not in f.name]
    if not video_files:
        return False

    video_path = str(video_files[0])

    cmd = [
        "ffmpeg",
        "-ss", timestamp,
        "-i", video_path,
        "-frames:v", "1",
        "-q:v", "2",
        "-y",
        output_path
    ]
    result = subprocess.run(cmd, capture_output=True)
    return result.returncode == 0

def image_to_base64(image_path):
    """将图片转换为base64"""
    try:
        with open(image_path, 'rb') as f:
            return base64.b64encode(f.read()).decode('utf-8')
    except:
        return ""

def generate_html(video_info, sections, video_url, summary="", overall_advice=""):
    """生成HTML文档"""
    print("正在生成HTML文档...")

    # 为每个段落提取截图
    for i, section in enumerate(sections):
        screenshot_path = f"/tmp/section_{i + 1}.jpg"
        print(f"  - 提取截图 {i + 1}/{len(sections)}: {section['title']}")

        if extract_screenshot_smart(section['time_str'], screenshot_path, section['title']):
            section['screenshot'] = image_to_base64(screenshot_path)
        else:
            section['screenshot'] = ""

    duration = video_info.get('duration', 0)
    if isinstance(duration, str) and duration.isdigit():
        duration = int(duration)
    elif not isinstance(duration, int):
        duration = 0

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{video_info['title']} - 视频总结</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            line-height: 1.6;
            max-width: 900px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        .header {{
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            color: #f5f5f5;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 20px;
        }}
        .header h1 {{
            margin: 0 0 10px 0;
            border-bottom: 3px solid #ff6b35;
            padding-bottom: 10px;
        }}
        .header a {{
            color: #f5f5f5;
            text-decoration: none;
            opacity: 0.9;
        }}
        .summary-box {{
            background: linear-gradient(135deg, #ff9a56 0%, #ff6b35 100%);
            color: #f5f5f5;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            font-size: 15px;
        }}
        .summary-box strong {{
            display: block;
            margin-bottom: 8px;
            font-size: 16px;
        }}
        .section-card {{
            background: white;
            border-left: 5px solid #1e3c72;
            padding: 20px;
            margin-bottom: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .section-card h2 {{
            color: #1e3c72;
            margin-top: 0;
            font-size: 20px;
        }}
        .timestamp {{
            display: inline-block;
            background: linear-gradient(135deg, #ff6b35 0%, #f7931e 100%);
            color: #f5f5f5;
            padding: 5px 15px;
            border-radius: 20px;
            text-decoration: none;
            font-size: 14px;
            margin: 10px 0;
            transition: opacity 0.3s;
            cursor: pointer;
        }}
        .timestamp:hover {{
            opacity: 0.85;
        }}
        .video-thumbnail {{
            width: 100%;
            max-width: 640px;
            height: auto;
            border-radius: 8px;
            margin: 15px 0;
        }}
        .content-box {{
            background: linear-gradient(135deg, #e8eaf6 0%, #c5cae9 100%);
            border-left: 5px solid #1e3c72;
            padding: 15px;
            border-radius: 5px;
            margin: 10px 0;
        }}
        .content-box ul {{
            margin: 5px 0;
            padding-left: 20px;
        }}
        .content-box li {{
            margin-bottom: 5px;
        }}
        .tips {{
            background: #fff3e0;
            border-left: 4px solid #ff6b35;
            padding: 10px 15px;
            border-radius: 4px;
            margin: 10px 0;
            font-size: 14px;
            color: #333;
        }}
        .tips::before {{
            content: "💡 ";
        }}
        .advice-box {{
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            color: #f5f5f5;
            padding: 20px;
            border-radius: 8px;
            margin-top: 20px;
        }}
        .advice-box strong {{
            display: block;
            margin-bottom: 8px;
            font-size: 16px;
        }}
        .footer {{
            text-align: center;
            color: #999;
            font-size: 12px;
            margin-top: 30px;
            padding: 10px;
        }}
        @media (max-width: 768px) {{
            body {{
                padding: 10px;
            }}
            .header {{
                padding: 20px;
            }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{video_info['title']}</h1>
        <p>📹 <a href="{video_url}" target="_blank">观看原视频</a></p>
        <p>⏱️ 视频时长: {duration // 60} 分钟</p>
        <p>📅 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
    </div>
"""

    # 添加视频简介
    if summary:
        html += f"""
    <div class="summary-box">
        <strong>📋 视频简介</strong>
        {summary}
    </div>
"""

    # 添加每个段落
    for i, section in enumerate(sections, 1):
        join_char = '&' if '?' in video_url else '?'
        timestamp_link = f"{video_url}{join_char}t={section['timestamp']}s"
        display_time = section.get('time_str_display', section.get('time_str', '00:00'))

        html += f"""
    <div class="section-card">
        <h2>{section['title']}</h2>
        <a href="{timestamp_link}" class="timestamp" target="_blank">
            ⏱️ {display_time} - 点击跳转
        </a>
"""
        if section.get('screenshot'):
            html += f"""
        <img src="data:image/jpeg;base64,{section['screenshot']}"
             alt="{section['title']}"
             class="video-thumbnail">
"""
        if section.get('content'):
            html += """
        <div class="content-box">
            <ul>
"""
            for point in section['content']:
                html += f"                <li>{point}</li>\n"
            html += """            </ul>
        </div>
"""
        if section.get('tips'):
            html += f"""
        <div class="tips">{section['tips']}</div>
"""
        html += "    </div>\n"

    # 添加整体建议
    if overall_advice:
        html += f"""
    <div class="advice-box">
        <strong>📝 整体建议</strong>
        {overall_advice}
    </div>
"""

    html += """
    <div class="footer">
        由 fitness-video-summary skill 自动生成
    </div>
</body>
</html>
"""
    return html

def save_html(html, video_title):
    """保存HTML文件到桌面"""
    desktop = Path.home() / "Desktop"
    safe_title = re.sub(r'[^\w\s-]', '', video_title)[:50]
    filename = f"{safe_title}_训练总结.html"
    filepath = desktop / filename

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"✓ HTML文件已保存: {filepath}")
    return str(filepath)

def send_email(html_path, video_title, video_url):
    """通过macOS Mail发送邮件"""
    print("正在发送邮件...")

    applescript = f'''
tell application "Mail"
    set theMessage to make new outgoing message with properties {{subject:"健身视频总结 - {video_title}", content:"Hi Ryan,

这是你请求的健身视频总结文档。

视频链接：{video_url}

文档已作为附件发送。

Best,
Nana", visible:false}}

    tell theMessage
        make new to recipient at end of to recipients with properties {{address:"your-email@example.com"}}
        make new attachment with properties {{file name:POSIX file "{html_path}"}}
    end tell

    send theMessage
end tell
'''

    result = subprocess.run(['osascript', '-e', applescript], capture_output=True, text=True)

    if result.returncode == 0:
        print("✓ 邮件发送成功")
        return True
    else:
        print(f"警告: 邮件发送失败\n{result.stderr}")
        return False

def main():
    if len(sys.argv) < 2:
        print("用法: python3 summarize_fitness_video.py <YouTube视频URL>")
        sys.exit(1)

    video_url = sys.argv[1]

    print("=" * 60)
    print("健身视频总结工具")
    print("=" * 60)

    # 1. 清理临时文件
    clean_temp_files()

    # 2. 获取视频信息
    print("\n获取视频信息...")
    video_info = get_video_info(video_url)
    if not video_info:
        video_info = {"title": "未知标题", "duration": 0, "video_id": ""}
    title = video_info.get('title', '未知标题')
    duration = video_info.get('duration', 0)
    if isinstance(duration, str) and duration.isdigit():
        duration = int(duration)
    elif not isinstance(duration, int):
        duration = 0
    print(f"  标题: {title}")
    print(f"  时长: {duration // 60} 分钟")

    # 3. 检测 YouTube Chapters
    print("\n检测 Chapters...")
    chapters = get_video_chapters(video_url)

    # 4. 下载视频和字幕
    print("\n下载视频和字幕...")
    if not download_video_and_subtitles(video_url):
        print("错误: 下载失败")
        sys.exit(1)

    # 5. 查找下载的视频文件
    video_files = list(Path("/tmp").glob("video.*"))
    video_files = [f for f in video_files if f.suffix in ['.mp4', '.webm', '.mkv'] and 'srt' not in f.name]
    video_path = str(video_files[0]) if video_files else "/tmp/video.mp4"

    # 新增流程：先解析字幕，如果能拿到字幕就丢给Gemini纯文本分析（省token）
    print("\n获取视频文稿(Subtitles)...")
    subtitles = parse_subtitles()

    # 6. Gemini 分析（传入 chapters 和 subtitles 信息）
    print("\n尝试 Gemini 视频分析...")
    gemini_data = analyze_with_gemini(video_path, chapters, subtitles)

    summary = ""
    overall_advice = ""

    if gemini_data:
        print("\n✓ 使用 Gemini 分析结果")
        sections = gemini_data_to_sections(gemini_data)
        summary = gemini_data.get('summary', '')
        overall_advice = gemini_data.get('overall_advice', '')
        if gemini_data.get('title') and video_info:
            video_info['title'] = gemini_data['title']
    else:
        # 7. 降级到纯正则字幕分析（最差情况，不再消耗API）
        print("\n降级到纯本地匹配模式...")
        if not subtitles:
            print("解析字幕...")
            subtitles = parse_subtitles()
        print("\n提取段落信息...")
        sections = extract_sections_from_subtitles(subtitles)

    # 8. 生成HTML
    print("\n生成HTML文档...")
    html = generate_html(video_info, sections, video_url, summary, overall_advice)

    # 9. 保存文件
    print("\n保存文件...")
    html_path = save_html(html, video_info['title'])

    # 10. 发送邮件
    print("\n发送邮件...")
    send_email(html_path, video_info['title'], video_url)

    print("\n" + "=" * 60)
    print("✓ 完成！")
    print(f"文件位置: {html_path}")
    print("=" * 60)

if __name__ == "__main__":
    main()
