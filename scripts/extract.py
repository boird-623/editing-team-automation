#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract.py
用途：当豆包无法直接理解某个视频文件时，由技能A/C调用本脚本，
      对视频做"抽帧 + 语音转写"，输出图片帧和 transcript.txt，
      供豆包基于文字和截图继续分析。

用法：
    python extract.py <视频路径> [--interval 1] [--out 输出目录]

依赖（需提前装好，脚本不负责自动安装）：
    - ffmpeg / ffprobe（需加入系统 PATH）
    - Python 包：无强制依赖；若要调用本地语音转写，
      可自行接入 faster-whisper 或其他已安装的ASR工具，
      本脚本默认只做抽帧，语音转写部分留了接口位置。

输出：
    <输出目录>/frames/frame_0001.jpg, frame_0002.jpg, ...
    <输出目录>/transcript.txt   （逐行格式：[秒数] 文本）
    <输出目录>/meta.txt         （分辨率、时长、帧率等基本信息）
"""

import argparse
import os
import subprocess
import sys


def run(cmd):
    """执行命令，失败时打印错误但不中断整体流程（由调用方决定是否继续）。"""
    print(f"[执行] {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[警告] 命令执行失败: {result.stderr}", file=sys.stderr)
    return result


def get_meta(video_path):
    """用 ffprobe 读取基础元信息。"""
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate,duration",
        "-of", "default=noprint_wrappers=1",
        video_path,
    ]
    result = run(cmd)
    return result.stdout


def extract_frames(video_path, out_dir, interval):
    """按固定间隔（秒）抽帧，输出为 jpg。"""
    frames_dir = os.path.join(out_dir, "frames")
    os.makedirs(frames_dir, exist_ok=True)
    fps_expr = f"fps=1/{interval}"
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", fps_expr,
        "-q:v", "2",
        os.path.join(frames_dir, "frame_%04d.jpg"),
    ]
    run(cmd)
    return frames_dir


def extract_audio_and_transcribe(video_path, out_dir):
    """
    提取音轨，并尝试转写。
    默认只做音频提取；如果本机已安装 faster-whisper 等ASR库，
    可以在下面标注的位置接入，否则 transcript.txt 会写明"未配置ASR，需人工听写"。
    """
    audio_path = os.path.join(out_dir, "audio.wav")
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-ac", "1", "-ar", "16000",
        audio_path,
    ]
    run(cmd)

    transcript_path = os.path.join(out_dir, "transcript.txt")

    # ---- ASR 接入位置（可选） ----
    # 如需启用本地转写，取消注释并确保已安装 faster-whisper：
    #
    # try:
    #     from faster_whisper import WhisperModel
    #     model = WhisperModel("small", device="cpu", compute_type="int8")
    #     segments, _ = model.transcribe(audio_path, language="zh")
    #     with open(transcript_path, "w", encoding="utf-8") as f:
    #         for seg in segments:
    #             f.write(f"[{seg.start:.1f}s] {seg.text.strip()}\n")
    #     return transcript_path
    # except ImportError:
    #     pass
    # ---- 接入位置结束 ----

    with open(transcript_path, "w", encoding="utf-8") as f:
        f.write("# 未配置本地ASR（faster-whisper等），以下为占位内容。\n")
        f.write("# 音频已提取到 audio.wav，可人工听写，或在本脚本中接入ASR模型。\n")

    return transcript_path


def main():
    parser = argparse.ArgumentParser(description="视频抽帧与转写辅助脚本")
    parser.add_argument("video", help="视频文件路径")
    parser.add_argument("--interval", type=float, default=1.0, help="抽帧间隔秒数，默认1秒")
    parser.add_argument("--out", default=None, help="输出目录，默认视频同目录下 <文件名>_extract")
    args = parser.parse_args()

    video_path = args.video
    if not os.path.isfile(video_path):
        print(f"[错误] 找不到视频文件: {video_path}", file=sys.stderr)
        sys.exit(1)

    base = os.path.splitext(os.path.basename(video_path))[0]
    out_dir = args.out or os.path.join(os.path.dirname(video_path), f"{base}_extract")
    os.makedirs(out_dir, exist_ok=True)

    meta = get_meta(video_path)
    with open(os.path.join(out_dir, "meta.txt"), "w", encoding="utf-8") as f:
        f.write(meta)

    frames_dir = extract_frames(video_path, out_dir, args.interval)
    transcript_path = extract_audio_and_transcribe(video_path, out_dir)

    print("完成。")
    print(f"帧目录: {frames_dir}")
    print(f"转写文件: {transcript_path}")
    print(f"元信息: {os.path.join(out_dir, 'meta.txt')}")


if __name__ == "__main__":
    main()
