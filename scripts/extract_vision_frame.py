#!/usr/bin/env python3
"""
基于视觉分析的智能截图选择工具 v3
使用 AI 视觉模型分析人物动作，选择最匹配的帧
"""

import subprocess
import sys
import os
from pathlib import Path
import json
import base64

def extract_frame(video_path, timestamp, output_path):
    """提取单帧"""
    cmd = [
        'ffmpeg', '-ss', timestamp, '-i', video_path,
        '-frames:v', '1', '-q:v', '2', '-update', '1',
        output_path, '-y'
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0

def analyze_frame_with_vision(image_path, action_name):
    """
    使用 Claude 视觉模型分析帧内容
    返回：(is_action_demo, confidence_score, description)
    """
    try:
        # 读取图片并转换为 base64
        with open(image_path, 'rb') as f:
            image_data = base64.b64encode(f.read()).decode()
        
        # 构建提示词
        prompt = f"""分析这张健身视频截图，判断是否是"{action_name}"动作的演示画面。

请回答：
1. 画面中的人物在做什么？（简短描述）
2. 这是动作演示还是讲解画面？
3. 如果是动作演示，是否匹配"{action_name}"？
4. 评分（0-100）：这张图作为"{action_name}"动作截图的合适度

请用JSON格式回答：
{{
  "description": "人物动作描述",
  "is_demo": true/false,
  "matches_action": true/false,
  "score": 0-100,
  "reason": "评分理由"
}}"""

        # 调用 Claude API
        payload = {
            "model": "claude-opus-4-6",
            "max_tokens": 500,
            "messages": [{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": image_data
                        }
                    },
                    {
                        "type": "text",
                        "text": prompt
                    }
                ]
            }]
        }
        
        # 使用 curl 调用 API
        result = subprocess.run(
            ['curl', '-s', 'https://codeflow.asia/v1/messages',
             '-H', 'Content-Type: application/json',
             '-H', 'x-api-key: REMOVED_API_KEY',
             '-H', 'anthropic-version: 2023-06-01',
             '-d', json.dumps(payload)],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            return False, 0, "API调用失败"
        
        response = json.loads(result.stdout)
        content = response['content'][0]['text']
        
        # 提取 JSON
        import re
        json_match = re.search(r'\{[^}]+\}', content, re.DOTALL)
        if json_match:
            analysis = json.loads(json_match.group())
            return (
                analysis.get('is_demo', False) and analysis.get('matches_action', False),
                analysis.get('score', 0),
                analysis.get('description', '')
            )
        
        return False, 0, "解析失败"
        
    except Exception as e:
        print(f"      ⚠️  视觉分析失败: {e}")
        return False, 0, str(e)

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

def extract_best_frame_with_vision(video_path, base_timestamp, output_path, action_name,
                                   offsets=[-10, -5, 0, 5, 10, 15, 20, 25, 30, 32, 35, 40, 45, 50, 55, 60]):
    """
    使用视觉分析提取最佳帧
    """
    base_seconds = time_to_seconds(base_timestamp)
    temp_dir = Path(output_path).parent
    candidates = []
    
    print(f"📸 智能提取最佳帧（视觉分析）: {action_name}")
    print(f"   基准时间: {base_timestamp}")
    print(f"   采样范围: {offsets}")
    print()
    
    # 提取多帧并分析
    for offset in offsets:
        timestamp_seconds = max(0, base_seconds + offset)
        timestamp = seconds_to_time(timestamp_seconds)
        temp_frame = temp_dir / f"temp_frame_{offset:+d}.jpg"
        
        print(f"  [{offset:+3d}s] 提取帧...", end=' ')
        
        if not extract_frame(video_path, timestamp, str(temp_frame)):
            print("❌ 提取失败")
            continue
        
        file_size = os.path.getsize(str(temp_frame))
        print(f"✓ ({file_size:,}B)", end=' ')
        
        # 视觉分析
        print("→ 分析中...", end=' ')
        is_demo, score, description = analyze_frame_with_vision(str(temp_frame), action_name)
        
        if is_demo:
            print(f"✅ 得分={score} - {description}")
        else:
            print(f"⚪ 得分={score} - {description}")
        
        candidates.append({
            'frame': temp_frame,
            'offset': offset,
            'score': score,
            'is_demo': is_demo,
            'description': description,
            'file_size': file_size
        })
    
    if not candidates:
        print("\n❌ 所有帧提取失败")
        return False
    
    # 选择得分最高的动作演示帧
    demo_frames = [c for c in candidates if c['is_demo']]
    
    if demo_frames:
        best = max(demo_frames, key=lambda x: x['score'])
        print(f"\n✅ 最佳帧: {best['offset']:+d}s (得分={best['score']}, {best['description']})")
    else:
        # 如果没有识别为动作演示的帧，选择得分最高的
        best = max(candidates, key=lambda x: x['score'])
        print(f"\n⚠️  未找到明确的动作演示帧，选择得分最高的: {best['offset']:+d}s (得分={best['score']})")
    
    # 复制最佳帧到输出路径
    subprocess.run(['cp', str(best['frame']), output_path])
    
    # 清理临时文件
    for c in candidates:
        try:
            c['frame'].unlink()
        except:
            pass
    
    return True

if __name__ == '__main__':
    if len(sys.argv) < 4:
        print("用法: python3 extract_vision_frame.py <video_path> <timestamp> <output_path> <action_name> [offsets...]")
        print("示例: python3 extract_vision_frame.py video.mp4 01:37 output.jpg 'Clean' -10 0 10 20 30")
        sys.exit(1)
    
    video_path = sys.argv[1]
    timestamp = sys.argv[2]
    output_path = sys.argv[3]
    action_name = sys.argv[4] if len(sys.argv) > 4 else ""
    
    if len(sys.argv) > 5:
        try:
            offsets = [int(x) for x in sys.argv[5:]]
        except ValueError:
            offsets = [-10, -5, 0, 5, 10, 15, 20, 25, 30, 32, 35, 40, 45, 50, 55, 60]
    else:
        offsets = [-10, -5, 0, 5, 10, 15, 20, 25, 30, 32, 35, 40, 45, 50, 55, 60]
    
    success = extract_best_frame_with_vision(video_path, timestamp, output_path, action_name, offsets)
    sys.exit(0 if success else 1)
