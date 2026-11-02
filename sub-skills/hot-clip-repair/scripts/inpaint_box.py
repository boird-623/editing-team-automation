#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
逐帧擦除视频中固定位置的"图形类"叠加（纯色块、爆款/热销角标、卡通贴纸、手绘标记），
自动合回原音频，输出 H.264。文字类叠加请先用 mediakit erase-video-subtitle-pro。

依赖（首次运行）:
  python -m pip install opencv-python-headless numpy imageio-ffmpeg

用法:
  python inpaint_box.py input.mp4 output.mp4 --box x,y,w,h[,top|bottom] [--box ...]
                            [--method inpaint|patch] [--radius 5] [--feather 10]

--box 坐标为归一化值（0-1）：x,y=左上角，w,h=宽高；末尾可选 top/bottom 表示 patch 取样方向。
  例：底部右侧色块  --box 0.55,0.93,0.30,0.06
      右侧竖排贴纸  --box 0.82,0.16,0.16,0.42
--method:
  inpaint（默认）OpenCV TELEA 修复，适合复杂背景上的小块；
  patch          从框正上方/正下方取同样大小的干净条带、羽化合成，适合纯色/渐变背景上的大色块。
"""
import argparse
import os
import subprocess
import sys
import tempfile

import cv2
import numpy as np
import imageio_ffmpeg


def parse_box(s, W, H):
    parts = [p.strip() for p in s.split(",")]
    if len(parts) not in (4, 5):
        raise ValueError(f"--box 格式应为 x,y,w,h[,top|bottom]，得到 {s}")
    x, y, w, h = map(float, parts[:4])
    direction = parts[4].lower() if len(parts) == 5 else "top"
    if direction not in ("top", "bottom"):
        raise ValueError("box 方向只能是 top 或 bottom")
    x0 = max(0, int(round(x * W)))
    y0 = max(0, int(round(y * H)))
    x1 = min(W, int(round((x + w) * W)))
    y1 = min(H, int(round((y + h) * H)))
    if x1 <= x0 or y1 <= y0:
        raise ValueError(f"box 宽高无效: {s}")
    return (x0, y0, x1, y1, direction)


def repair_frame(frame, boxes, method, radius, feather):
    out = frame
    for (x0, y0, x1, y1, direction) in boxes:
        bh, bw = y1 - y0, x1 - x0
        if method == "patch":
            # 从正上方/正下方取同尺寸干净条带
            if direction == "top":
                sy0, sy1 = y0 - bh, y0
            else:
                sy0, sy1 = y1, y1 + bh
            if sy0 < 0 or sy1 > frame.shape[0]:
                # 越界则改用另一侧
                sy0, sy1 = (y1, y1 + bh) if sy0 < 0 else (y0 - bh, y0)
            if sy0 < 0 or sy1 > frame.shape[0] or sy1 <= sy0:
                patch = cv2.inpaint(out, _mask(frame.shape, x0, y0, x1, y1), radius, cv2.INPAINT_TELEA)
                out = patch
                continue
            patch = out[sy0:sy1, x0:x1].copy()
            region = out[y0:y1, x0:x1]
            if patch.shape[:2] != region.shape[:2]:
                patch = cv2.resize(patch, (region.shape[1], region.shape[0]))
            alpha = _feather_alpha(bh, bw, feather)
            blended = (patch.astype(np.float32) * alpha + region.astype(np.float32) * (1 - alpha)).astype(np.uint8)
            out[y0:y1, x0:x1] = blended
        else:
            mask = _mask(frame.shape, x0, y0, x1, y1)
            filled = cv2.inpaint(out, mask, radius, cv2.INPAINT_TELEA)
            alpha = _feather_alpha(bh, bw, feather)
            region_f = filled[y0:y1, x0:x1].astype(np.float32)
            region_o = out[y0:y1, x0:x1].astype(np.float32)
            out[y0:y1, x0:x1] = (region_f * alpha + region_o * (1 - alpha)).astype(np.uint8)
    return out


def _mask(shape, x0, y0, x1, y1):
    m = np.zeros(shape[:2], np.uint8)
    m[y0:y1, x0:x1] = 255
    return m


def _feather_alpha(h, w, feather):
    """框内 1、边缘用高斯羽化到 0 的 alpha，形状 (h,w,1)。"""
    f = max(1, min(feather, h // 2, w // 2))
    a = np.ones((h, w), np.float32)
    pad = f * 2
    a = cv2.copyMakeBorder(a, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)
    k = f * 2 + 1
    a = cv2.GaussianBlur(a, (k, k), f * 0.6)
    # 裁回并把中心归一到 1
    a = a[pad:-pad, pad:-pad]
    a = np.clip(a / (a.max() + 1e-6), 0, 1)
    return a[:, :, None]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--box", action="append", default=[], required=True)
    ap.add_argument("--method", choices=["inpaint", "patch"], default="inpaint")
    ap.add_argument("--radius", type=int, default=5)
    ap.add_argument("--feather", type=int, default=10)
    args = ap.parse_args()

    cap = cv2.VideoCapture(args.input)
    if not cap.isOpened():
        sys.exit(f"无法打开输入: {args.input}")
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    boxes = [parse_box(b, W, H) for b in args.box]
    print(f"视频 {W}x{H} @ {fps:.2f}fps, {total} 帧; 修复框 {boxes}")

    tmpdir = tempfile.mkdtemp(prefix="inpaint_")
    tmp_video = os.path.join(tmpdir, "video.mp4")
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(tmp_video, fourcc, fps, (W, H))
    n = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        writer.write(repair_frame(frame, boxes, args.method, args.radius, args.feather))
        n += 1
        if total and n % max(1, total // 10) == 0:
            print(f"  进度 {n}/{total} ({100*n//total}%)")
    cap.release()
    writer.release()
    print(f"修复 {n} 帧，合回音频并转 H.264 ...")

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    # 先尝试取原音频；原片无音轨时退化为只转视频
    cmd = [ffmpeg, "-y", "-i", tmp_video, "-i", args.input,
           "-map", "0:v:0", "-map", "1:a:0?", "-c:v", "libx264", "-pix_fmt", "yuv420p",
           "-crf", "18", "-c:a", "aac", "-b:a", "128k", "-shortest", args.output]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(args.output):
        print(r.stderr[-1500:])
        sys.exit("ffmpeg 合成失败")
    print(f"完成: {args.output} ({os.path.getsize(args.output):,} bytes)")


if __name__ == "__main__":
    main()
