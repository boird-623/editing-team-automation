#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
素材预审：确定性违禁/风险词扫描。
读取口播/字幕/标题文本（.txt/.srt/.vtt/.json），按词库 wordlib.json 命中
广告法绝对化用语、食品功效与医疗禁忌、资质类、导流、价格欺诈等，输出带时间点、
风险等级、依据、修改建议的 Markdown 或 JSON。隐含/谐音/语义类违规需由模型另行复核。

用法:
  python scan_words.py asr.txt ocr.txt title.txt --lib ../assets/wordlib.json -o 命中.md
  python scan_words.py asr.txt --source 口播 --lib ../assets/wordlib.json --json
"""
import argparse
import glob
import json
import os
import re
import sys

RISK_ORDER = {"high": 0, "medium": 1, "low": 2}
RISK_LABEL = {"high": "高", "medium": "中", "low": "低"}
WS = re.compile(r"[\s\u3000]+")


def norm(t):
    return WS.sub("", t or "")


def load_lib(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        lib = json.load(f)
    for c in lib["categories"]:
        c["_words"] = [norm(w) for w in c.get("words", [])]
        c["_patterns"] = [re.compile(p) for p in c.get("patterns", [])]
    lib["_white"] = [norm(w) for w in lib.get("whitelist", [])]
    return lib


def mask_whitelist(t, white):
    m = t
    for w in white:
        if w:
            m = m.replace(w, "〇" * len(w))
    return m


def parse_time_srt(ts):
    try:
        h, m, s = ts.replace(",", ".").split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)
    except Exception:
        return None


def extract_segments(path):
    """返回 [(start_sec_or_None, text)]，支持 txt/srt/vtt/json。"""
    with open(path, "r", encoding="utf-8-sig", errors="ignore") as f:
        raw = f.read()
    ext = os.path.splitext(path)[1].lower()
    segs = []
    if ext == ".srt":
        for block in re.split(r"\n\s*\n", raw.strip()):
            lines = [l for l in block.splitlines() if l.strip()]
            tm = next((l for l in lines if "-->" in l), None)
            if not tm:
                continue
            start = parse_time_srt(tm.split("-->")[0].strip())
            text = " ".join(l for l in lines if "-->" not in l and not l.strip().isdigit())
            if text.strip():
                segs.append((start, text))
    elif ext == ".vtt":
        for block in re.split(r"\n\s*\n", raw.strip()):
            lines = [l for l in block.splitlines() if l.strip()]
            tm = next((l for l in lines if "-->" in l), None)
            if not tm:
                continue
            start = parse_time_srt(tm.split("-->")[0].strip().split()[0])
            text = " ".join(l for l in lines if "-->" not in l and not l.startswith("WEBVTT"))
            if text.strip():
                segs.append((start, text))
    elif ext == ".json":
        data = json.loads(raw)
        found = []

        def walk(o):
            if isinstance(o, dict):
                txt = o.get("text") or o.get("content") or o.get("transcript")
                if isinstance(txt, str) and txt.strip():
                    st = o.get("start") or o.get("start_time") or o.get("begin")
                    st = float(st) if isinstance(st, (int, float)) else None
                    found.append((st, txt))
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)
            elif isinstance(o, str):
                if len(o) > 4:
                    found.append((None, o))
        walk(data)
        segs = found if found else [(None, raw)]
    else:
        for line in raw.splitlines():
            if line.strip():
                segs.append((None, line))
    return segs or [(None, raw)]


def context(text_n, idx, span=14):
    a = max(0, idx - span)
    b = min(len(text_n), idx + span)
    return text_n[a:b]


def fmt_time(s):
    if s is None:
        return "-"
    s = int(s)
    return f"{s//60:02d}:{s%60:02d}"


def scan_file(path, source, lib):
    hits = []
    for start, text in extract_segments(path):
        t = norm(text)
        masked = mask_whitelist(t, lib["_white"])  # 白名单仅用于抑制变体正则的误报
        for c in lib["categories"]:
            spans = []
            # 明确违规词在原文上精确匹配（优先级最高，不受白名单影响）
            for w in c["_words"]:
                idx = t.find(w)
                while idx >= 0:
                    spans.append((idx, idx + len(w), w))
                    idx = t.find(w, idx + 1)
            # 变体正则在屏蔽文本上匹配（避免"最新鲜/最后"等被通用 pattern 误报）
            for p in c["_patterns"]:
                for m in p.finditer(masked):
                    spans.append((m.start(), m.end(), m.group(0)))
            # 同类最长匹配：区间被更长命中包含时丢弃较短者，消除"最低/最低价/全网最低价"重复
            spans.sort(key=lambda s: (s[0], -(s[1] - s[0])))
            kept = []
            for s0, s1, w in spans:
                if any(k0 <= s0 and s1 <= k1 for k0, k1, _ in kept):
                    continue
                kept.append((s0, s1, w))
            for idx, _, w in kept:
                hits.append({
                    "source": source,
                    "time": fmt_time(start),
                    "risk": c["risk"],
                    "category": c["name"],
                    "hit": w,
                    "snippet": context(t, idx),
                    "basis": c["basis"],
                    "suggestion": c["suggestion"],
                })
    # 去重（同来源+类别+词+片段）
    uniq, seen = [], set()
    for h in hits:
        k = (h["source"], h["category"], h["hit"], h["snippet"])
        if k not in seen:
            seen.add(k)
            uniq.append(h)
    return uniq


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+", help="文本文件，可多个（支持 .txt/.srt/.vtt/.json，支持通配符）")
    ap.add_argument("--lib", required=True, help="wordlib.json 路径")
    ap.add_argument("--source", default="", help="来源标签，默认用文件名")
    ap.add_argument("-o", "--output", default="")
    ap.add_argument("--json", action="store_true", help="输出 JSON 而非 Markdown")
    args = ap.parse_args()

    files = []
    for pat in args.files:
        files.extend(glob.glob(pat) if any(ch in pat for ch in "*?[") else [pat])
    if not files:
        sys.exit("未找到输入文件")
    lib = load_lib(args.lib)

    all_hits = []
    for path in files:
        source = args.source or os.path.basename(path)
        all_hits.extend(scan_file(path, source, lib))
    all_hits.sort(key=lambda h: (RISK_ORDER.get(h["risk"], 9), h["source"], h["time"]))

    if args.json:
        out = json.dumps(all_hits, ensure_ascii=False, indent=2)
    else:
        counts = {"high": 0, "medium": 0, "low": 0}
        for h in all_hits:
            counts[h["risk"]] = counts.get(h["risk"], 0) + 1
        L = []
        L.append("# 素材预审命中清单（词库扫描）")
        L.append("")
        L.append(f"共命中 {len(all_hits)} 项：高风险 {counts['high']} / 中风险 {counts['medium']} / 低风险 {counts['low']}。")
        L.append("")
        L.append("> 本结果为词库确定性扫描，覆盖字面违禁词；隐含功效，谐音/拆字变体、语义擦边需再做语义复核。")
        L.append("")
        for risk in ["high", "medium", "low"]:
            sub = [h for h in all_hits if h["risk"] == risk]
            if not sub:
                continue
            L.append(f"## {RISK_LABEL[risk]}风险（{len(sub)}）")
            L.append("| 来源 | 时间 | 命中词 | 类别 | 原文片段 | 依据 | 修改建议 |")
            L.append("|---|---|---|---|---|---|---|")
            for h in sub:
                L.append(f"| {h['source']} | {h['time']} | **{h['hit']}** | {h['category']} | "
                         f"{h['snippet']} | {h['basis']} | {h['suggestion']} |")
            L.append("")
        out = "\n".join(L)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(out)
        print(f"已写入 {args.output}，命中 {len(all_hits)} 项")
    else:
        print(out)


if __name__ == "__main__":
    main()
