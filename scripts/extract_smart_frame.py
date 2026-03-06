#!/usr/bin/env python3
"""
智能截图选择工具 v2
1. 扩大采样范围
2. 使用 OCR 检测画面中的文字
3. 优先选择包含动作名称文字的帧
4. 评估画面质量和内容相关性
"""

import subprocess
import sys
import os
from pathlib import Path
import re

def extract_frame(video_path, timestamp, output_path):
    """提取单帧"""
    cmd = [
        'ffmpeg', '-ss', timestamp, '-i', video_path,
        '-frames:v', '1', '-q:v', '2', '-update', '1',
        output_path, '-y'
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0

def detect_text_in_image(image_path):
    """
    使用 tesseract OCR 检测图片中的文字
    如果 tesseract 不可用，返回空字符串
    """
    try:
        result = subprocess.run(
            ['tesseract', image_path, 'stdout', '--psm', '11'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return result.stdout.lower()
        return ""
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""

def get_frame_quality(image_path):
    """评估图片质量（文件大小）"""
    try:
        return os.path.getsize(image_path)
    except:
        return 0

def time_to_seconds(time_str):
    """将 HH:MM:SS 或 MM:SS 转换为秒数"""
    parts = time_str.split(':')
    if len(parts) == 3:
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + float(s)
    elif len(parts) == 2:
        m, s = parts
        return int(m) * 60 + float(s)
    else:
        return float(parts[0])

def seconds_to_time(seconds):
    """将秒数转换为 HH:MM:SS 格式"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:06.3f}"
    else:
        return f"{m:02d}:{s:06.3f}"

def score_frame(image_path, action_keywords, quality):
    """
    评分系统：
    - 基础分：质量（文件大小）
    - 加分：包含动作关键词的文字标注
    """
    score = quality
    
    # 检测文字
    text = detect_text_in_image(image_path)
    
    # 如果检测到动作关键词，大幅加分
    if text:
        for keyword in action_keywords:
            if keyword.lower() in text:
                score += quality * 2  # 加倍分数
                print(f"      ✨ 检测到关键词: {keyword}")
                break
    
    return score

def extract_best_frame(video_path, base_timestamp, output_path, action_name="", 
                      offsets=[-10, -5, 0, 5, 10, 15, 20, 25, 30, 32, 35, 40, 45, 50, 55, 60]):
    """
    智能提取最佳帧
    
    Args:
        video_path: 视频文件路径
        base_timestamp: 基准时间点 (HH:MM:SS 或 MM:SS)
        output_path: 输出图片路径
        action_name: 动作名称（用于文字检测）
        offsets: 时间偏移列表（秒）
    """
    base_seconds = time_to_seconds(base_timestamp)
    temp_dir = Path(output_path).parent
    temp_frames = []
    
    # 提取动作关键词
    action_keywords = []
    if action_name:
        # 提取主要关键词
        keywords = re.findall(r'\b[A-Za-z]+\b', action_name)
        action_keywords = [k for k in keywords if len(k) > 3]  # 只保留长度>3的词
    
    print(f"📸 智能提取最佳帧: {action_name}")
    print(f"   基准时间: {base_timestamp}")
    print(f"   关键词: {action_keywords}")
    print(f"   采样范围: {offsets}")
    
    # 提取多帧
    for offset in offsets:
        timestamp_seconds = max(0, base_seconds + offset)
        timestamp = seconds_to_time(timestamp_seconds)
        temp_frame = temp_dir / f"temp_frame_{offset:+d}.jpg"
        
        if extract_frame(video_path, timestamp, str(temp_frame)):
            quality = get_frame_quality(str(temp_frame))
            score = score_frame(str(temp_frame), action_keywords, quality)
            temp_frames.append((temp_frame, score, quality, offset))
            print(f"  ✓ {offset:+3d}s: 质量={quality:,}B, 得分={score:,}")
        else:
            print(f"  ✗ {offset:+3d}s: 提取失败")
    
    if not temp_frames:
        print("❌ 所有帧提取失败")
        return False
    
    # 选择得分最高的帧
    best_frame, best_score, best_quality, best_offset = max(temp_frames, key=lambda x: x[1])
    print(f"✅ 最佳帧: {best_offset:+d}s (得分={best_score:,}, 质量={best_quality:,}B)")
    
    # 复制最佳帧到输出路径
    subprocess.run(['cp', str(best_frame), output_path])
    
    # 清理临时文件
    for frame, _, _, _ in temp_frames:
        try:
            frame.unlink()
        except:
            pass
    
    return True

if __name__ == '__main__':
    if len(sys.argv) < 4:
        print("用法: python3 extract_smart_frame.py <video_path> <timestamp> <output_path> [action_name] [offsets...]")
        print("示例: python3 extract_smart_frame.py video.mp4 01:37 output.jpg 'Clean' -10 -5 0 5 10 15 20 30")
        sys.exit(1)
    
    video_path = sys.argv[1]
    timestamp = sys.argv[2]
    output_path = sys.argv[3]
    action_name = sys.argv[4] if len(sys.argv) > 4 else ""
    
    # 如果提供了自定义偏移量
    if len(sys.argv) > 5:
        try:
            offsets = [int(x) for x in sys.argv[5:]]
        except ValueError:
            offsets = [-10, -5, 0, 5, 10, 15, 20, 30, 40]
    else:
        offsets = [-10, -5, 0, 5, 10, 15, 20, 25, 30, 32, 35, 40, 45, 50, 55, 60]
    
    success = extract_best_frame(video_path, timestamp, output_path, action_name, offsets)
    sys.exit(0 if success else 1)
