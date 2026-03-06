#!/usr/bin/env python3
"""
多帧采样截图工具
在指定时间点前后提取多帧，选择最清晰的一帧
"""

import subprocess
import sys
import os
from pathlib import Path

def extract_frame(video_path, timestamp, output_path):
    """提取单帧"""
    cmd = [
        'ffmpeg', '-ss', timestamp, '-i', video_path,
        '-frames:v', '1', '-q:v', '2', '-update', '1',
        output_path, '-y'
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0

def get_frame_quality(image_path):
    """
    评估图片质量（使用文件大小作为简单指标）
    更清晰、内容更丰富的图片通常文件更大
    """
    try:
        size = os.path.getsize(image_path)
        return size
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

def extract_best_frame(video_path, base_timestamp, output_path, offsets=[-5, 0, 5, 10, 15]):
    """
    在基准时间点前后提取多帧，选择质量最好的一帧
    
    Args:
        video_path: 视频文件路径
        base_timestamp: 基准时间点 (HH:MM:SS 或 MM:SS)
        output_path: 输出图片路径
        offsets: 时间偏移列表（秒）
    """
    base_seconds = time_to_seconds(base_timestamp)
    temp_dir = Path(output_path).parent
    temp_frames = []
    
    print(f"📸 在时间点 {base_timestamp} 附近提取多帧...")
    
    # 提取多帧
    for offset in offsets:
        timestamp_seconds = max(0, base_seconds + offset)  # 确保不小于0
        timestamp = seconds_to_time(timestamp_seconds)
        temp_frame = temp_dir / f"temp_frame_{offset:+d}.jpg"
        
        if extract_frame(video_path, timestamp, str(temp_frame)):
            quality = get_frame_quality(str(temp_frame))
            temp_frames.append((temp_frame, quality, offset))
            print(f"  ✓ {offset:+3d}s: {quality:,} bytes")
        else:
            print(f"  ✗ {offset:+3d}s: 提取失败")
    
    if not temp_frames:
        print("❌ 所有帧提取失败")
        return False
    
    # 选择质量最好的帧（文件最大的）
    best_frame, best_quality, best_offset = max(temp_frames, key=lambda x: x[1])
    print(f"✅ 选择最佳帧: {best_offset:+d}s (质量: {best_quality:,} bytes)")
    
    # 复制最佳帧到输出路径
    subprocess.run(['cp', str(best_frame), output_path])
    
    # 清理临时文件
    for frame, _, _ in temp_frames:
        try:
            frame.unlink()
        except:
            pass
    
    return True

if __name__ == '__main__':
    if len(sys.argv) < 4:
        print("用法: python3 extract_best_frame.py <video_path> <timestamp> <output_path> [offsets...]")
        print("示例: python3 extract_best_frame.py video.mp4 01:37 output.jpg -5 0 5 10 15")
        sys.exit(1)
    
    video_path = sys.argv[1]
    timestamp = sys.argv[2]
    output_path = sys.argv[3]
    offsets = [int(x) for x in sys.argv[4:]] if len(sys.argv) > 4 else [-5, 0, 5, 10, 15]
    
    success = extract_best_frame(video_path, timestamp, output_path, offsets)
    sys.exit(0 if success else 1)
