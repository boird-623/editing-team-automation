#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_env.py
用途：剪辑团队自动化技能「一次性初始化」时，检查本机依赖是否就绪。
      只检测并报告，绝不自动下载、安装任何东西（缺什么由用户手动安装）。

用法：
    python check_env.py
    python check_env.py --json     # 以 JSON 输出，便于其他流程读取

检查项：
    必需：python、ffmpeg、ffprobe
    可选：realesrgan-ncnn-vulkan（技能B 本地超分）、faster_whisper（extract.py 语音转写）
"""

import argparse
import json
import shutil
import sys


def version_of(cmd, args=("--version",)):
    """尝试取版本号；取不到返回 None。"""
    import subprocess
    try:
        r = subprocess.run([cmd, *args], capture_output=True, text=True, timeout=15)
        out = (r.stdout or r.stderr or "").strip().splitlines()
        return out[0].strip() if out else "(已安装，未取到版本)"
    except Exception:
        return None


def check_optional_module(module):
    try:
        m = __import__(module)
        return getattr(m, "__version__", "(已安装)")
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = ap.parse_args()

    results = []

    # 必需：Python
    results.append({
        "name": "python", "required": True,
        "ok": True, "detail": "Python %s" % sys.version.split()[0],
        "hint": "",
    })

    # 必需：ffmpeg / ffprobe
    for name in ("ffmpeg", "ffprobe"):
        path = shutil.which(name) or shutil.which(name + ".exe")
        if path:
            ver = version_of(name)
            results.append({"name": name, "required": True, "ok": True,
                            "detail": ver or path, "hint": ""})
        else:
            results.append({"name": name, "required": True, "ok": False,
                            "detail": "未找到", "hint": "安装 ffmpeg 并加入系统 PATH（ffprobe 一般随 ffmpeg 提供）"})

    # 可选：Real-ESRGAN
    re_path = shutil.which("realesrgan-ncnn-vulkan") or shutil.which("realesrgan-ncnn-vulkan.exe")
    results.append({
        "name": "realesrgan-ncnn-vulkan", "required": False,
        "ok": bool(re_path),
        "detail": re_path or "未找到（本地超分不可用，技能B将走云端画质增强）",
        "hint": "需要时从 https://github.com/xinntao/Real-ESRGAN/releases 下载并加入 PATH",
    })

    # 可选：faster-whisper
    fw = check_optional_module("faster_whisper")
    results.append({
        "name": "faster_whisper", "required": False,
        "ok": bool(fw),
        "detail": fw or "未安装（extract.py 只抽帧，口播转写需人工听写或走云端转写）",
        "hint": "需要时执行 pip install faster-whisper",
    })

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        missing_required = [r for r in results if r["required"] and not r["ok"]]
        for r in results:
            tag = "必需" if r["required"] else "可选"
            mark = "OK " if r["ok"] else "缺失"
            print("[%s|%s] %-24s %s" % (mark, tag, r["name"], r["detail"]))
            if not r["ok"] and r["hint"]:
                print("        -> %s" % r["hint"])
        print("-" * 60)
        if missing_required:
            print("结论：缺少必需依赖 %d 项：%s，请先手动安装。"
                  % (len(missing_required), "、".join(r["name"] for r in missing_required)))
            sys.exit(1)
        print("结论：必需依赖已就绪；可选项按需要安装。")


if __name__ == "__main__":
    main()
