#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
爆款视频本地特征提取：读取视频 -> 探测元信息 -> 抽取开头帧 + 全片帧 -> 提取音频。

为爆款雷达 / 素材预审官提供本地可做的素材准备；口播转写(transcript)由主流程
调用 mediakit（asr-subtitles）完成，本脚本只负责产出帧图与音频，不做云端调用。

用法:
    python extract.py <视频路径> [--outdir 输出目录] [--intro-sec 3] [--intro-step 0.5]
                                [--full-frames 16] [--no-audio]

输出（默认在视频同目录下的 <视频名>_frames/ 文件夹）:
    intro_*.jpg   开头 0~intro-sec 秒每 intro-step 秒一帧
    full_*.jpg    全片均匀 full-frames 帧
    audio.wav     16kHz 单声道音频（供 ASR；--no-audio 可关）
    manifest.json 元信息与文件清单（含 transcript_pending 标记）
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def find_ffmpeg():
    """优先用 PATH 中的 ffmpeg，否则用 imageio_ffmpeg 自带二进制。"""
    exe = None
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    for cand in (os.environ.get("FFMPEG"), "ffmpeg"):
        if cand:
            try:
                subprocess.run([cand, "-version"], capture_output=True, check=True)
                return cand
            except Exception:
                continue
    return exe


def probe_and_extract_frames(video: Path, outdir: Path, intro_sec: float,
                             intro_step: float, full_frames: int):
    import cv2
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError(f"无法打开视频: {video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    duration = (total / fps) if fps else 0.0

    # 目标时间点（秒）
    intro_ts = [round(i * intro_step, 2)
                for i in range(int(intro_sec / intro_step) + 1)]
    intro_ts = [t for t in intro_ts if t < duration]
    if duration > 0:
        full_n = max(1, full_frames)
        full_ts = [round(duration * (k + 0.5) / full_n, 2) for k in range(full_n)]
    else:
        full_ts = []
    targets = sorted(set([("intro", t) for t in intro_ts] +
                         [("full", t) for t in full_ts]), key=lambda x: x[1])

    saved = []
    for kind, t in targets:
        if fps:
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ok, frame = cap.read()
        if not ok:
            continue
        prefix = "intro" if kind == "intro" else "full"
        name = f"{prefix}_t{t:06.2f}.jpg"
        p = outdir / name
        cv2.imwrite(str(p), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
        saved.append({"kind": kind, "time": t, "file": name})
    cap.release()
    meta = {
        "video": str(video),
        "width": width, "height": height,
        "fps": round(fps, 3), "frame_count": total,
        "duration_sec": round(duration, 2),
    }
    return meta, saved


def extract_audio(video: Path, outdir: Path, ffmpeg: str):
    audio = outdir / "audio.wav"
    if not ffmpeg:
        return None, "未找到 ffmpeg，跳过音频提取"
    cmd = [ffmpeg, "-y", "-i", str(video), "-vn", "-ac", "1",
           "-ar", "16000", "-f", "wav", str(audio)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode == 0 and audio.exists():
        return str(audio), None
    return None, (r.stderr or "ffmpeg 音频提取失败")[-500:]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video", help="本地视频文件路径")
    ap.add_argument("--outdir", default="", help="输出目录，默认视频同目录 <名>_frames")
    ap.add_argument("--intro-sec", type=float, default=3.0)
    ap.add_argument("--intro-step", type=float, default=0.5)
    ap.add_argument("--full-frames", type=int, default=16)
    ap.add_argument("--no-audio", action="store_true")
    args = ap.parse_args()

    video = Path(args.video).expanduser().resolve()
    if not video.exists():
        sys.exit(f"视频不存在: {video}")
    outdir = Path(args.outdir).expanduser().resolve() if args.outdir \
        else video.parent / f"{video.stem}_frames"
    outdir.mkdir(parents=True, exist_ok=True)

    meta, saved = probe_and_extract_frames(
        video, outdir, args.intro_sec, args.intro_step, args.full_frames)

    audio, audio_err = (None, None)
    if not args.no_audio:
        audio, audio_err = extract_audio(video, outdir, find_ffmpeg())

    manifest = {
        **meta,
        "outdir": str(outdir),
        "frames": saved,
        "audio": audio,
        "audio_error": audio_err,
        # 有音频但未转写时，主流程需用 mediakit asr-subtitles 生成 transcript.txt
        "transcript_pending": bool(audio),
        "note": "口播转写请由主流程调用 mediakit asr-subtitles 完成；视频画面理解直接看帧图。",
    }
    (outdir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({
        "ok": True,
        "duration_sec": meta["duration_sec"],
        "resolution": f'{meta["width"]}x{meta["height"]}',
        "fps": meta["fps"],
        "frames": len(saved),
        "audio": audio,
        "audio_error": audio_err,
        "outdir": str(outdir),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
