#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
行业/对标爆款筛选器：对多平台采集到的候选素材做
  去重(平台+视频ID) → 时间窗过滤 → 行业关键词过滤 → 点赞阈值过滤 → 只新增(对比历史)，
按平台分开输出达标清单（Markdown）与结构化结果（JSON，供增量/写表复用）。

候选输入 JSON 数组（字段可缺省，缺省用空/0）：
  {
    "platform": "douyin|kuaishou|tencent|baidu|wechat",
    "video_id": "视频ID（抖音 aweme_id）",
    "material_id": "有米有数素材ID（与 video_id 二选一）",
    "author": "作者/账号",
    "title": "标题",
    "likes": 1200, "comments": 30, "shares": 8, "plays": 0,
    "ad_days": 12,                 # 投放天数（有米有数）
    "publish_time": "2026-10-13",  # 也支持 2026/10/13、3天前、昨天
    "url": "https://...",
    "product": "关联商品/广告主",
    "source": "youmi|web"
  }

用法示例：
  # 直接指定参数
  python filter_hotlist.py candidates.json --min-likes 100 --days 1 \\
      --platforms douyin,kuaishou,tencent --keywords 食用油,花生油,洗发水 \\
      --json out.json -o 行业爆款.md

  # 从 config.json 的 hot_radar.industry_tasks 读任务（推荐，定时任务用）
  python filter_hotlist.py candidates.json --config D:\\豆包工作区\\config.json \\
      --task 食品饮料 --existing 上次结果.json -o 行业爆款_食品饮料.md
"""
import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta

PLATFORM_LABEL = {
    "douyin": "抖音", "kuaishou": "快手", "tencent": "视频号",
    "wechat": "视频号", "baidu": "百度", "youmi": "有米有数",
}
PLATFORM_ORDER = ["douyin", "kuaishou", "tencent", "baidu", "wechat"]


def parse_num(v):
    """12000 / '1.2w' / '13万' / '1.2亿' → int；无法解析返回 0。"""
    if v is None:
        return 0
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v).strip().replace(",", "").replace("，", "")
    if not s:
        return 0
    m = re.search(r"(\d+(?:\.\d+)?)\s*([万w亿])?", s)
    if not m:
        return 0
    n = float(m.group(1))
    unit = m.group(2)
    if unit in ("万", "w"):
        n *= 10000
    elif unit == "亿":
        n *= 100000000
    return int(n)


def parse_date(v):
    """解析发布时间，返回 date；解析不了返回 None。"""
    if not v:
        return None
    if isinstance(v, (datetime, date)):
        return v.date() if isinstance(v, datetime) else v
    s = str(v).strip()
    # 相对时间
    rel = {
        "今天": 0, "今日": 0, "昨天": 1, "昨日": 1,
        "前天": 2, "刚刚": 0,
    }
    for k, d in rel.items():
        if k in s:
            return date.today() - timedelta(days=d)
    m = re.search(r"(\d+)\s*(分钟|小时|天|周)前", s)
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        if "周" in unit:
            n *= 7
        if "分钟" in unit or "小时" in unit:
            return date.today()
        return date.today() - timedelta(days=n)
    # 绝对时间
    m = re.search(r"(20\d{2})[\-/年.](\d{1,2})[\-/月.](\d{1,2})", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = re.search(r"(?:^|[^\d])(\d{1,2})[\-/月.](\d{1,2})(?:日|号)?", s)
    if m:
        try:
            return date(date.today().year, int(m.group(1)), int(m.group(2)))
        except ValueError:
            return None
    return None


def item_key(it):
    """去重键：平台+视频ID/素材ID；都没有时用 平台+链接 / 平台+标题。"""
    p = it.get("platform") or "other"
    vid = it.get("video_id") or it.get("material_id") or it.get("id")
    if vid:
        return f"{p}|{vid}"
    if it.get("url"):
        return f"{p}|{it['url'].strip()}"
    return f"{p}|{it.get('title','')}"


def esc(s):
    return str(s if s is not None else "").replace("|", "\\|").replace("\n", " ").strip()


def load_task(config_path, task_name):
    if not config_path or not task_name:
        return {}
    try:
        with open(config_path, "r", encoding="utf-8-sig") as f:
            cfg = json.load(f)
    except Exception as e:
        sys.exit(f"读取 config 失败：{e}")
    for t in cfg.get("hot_radar", {}).get("industry_tasks", []):
        if t.get("name") == task_name:
            return t
    sys.exit(f"config.json 中未找到行业任务：{task_name}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="候选结果 JSON 文件")
    ap.add_argument("--config", default="", help="config.json 路径")
    ap.add_argument("--task", default="", help="config 中 hot_radar.industry_tasks 的任务名")
    ap.add_argument("--min-likes", type=int, default=None, help="点赞阈值（含）")
    ap.add_argument("--days", type=int, default=None, help="时间窗（近 N 天）")
    ap.add_argument("--platforms", default="", help="只保留平台，逗号分隔")
    ap.add_argument("--keywords", default="", help="行业关键词，逗号分隔（标题命中其一即保留）")
    ap.add_argument("--metric", default="likes", choices=["likes", "heat"],
                    help="阈值比较口径：likes=点赞（默认）；heat=抖音快手按点赞、百度按播放")
    ap.add_argument("--existing", default="", help="历史清单 JSON，已存在键只更新不重复入选")
    ap.add_argument("--json", dest="json_out", default="", help="结构化结果 JSON 输出")
    ap.add_argument("-o", "--output", default="", help="Markdown 清单输出")
    args = ap.parse_args()

    task = load_task(args.config, args.task)
    min_likes = args.min_likes if args.min_likes is not None else int(task.get("min_likes", 0))
    days = args.days if args.days is not None else int(task.get("time_window_days", 0) or 0)
    plats = [p.strip() for p in (
        args.platforms or ",".join(task.get("platforms", [])) or "").split(",") if p.strip()]
    kws = [k.strip() for k in (
        args.keywords or ",".join(task.get("keywords", []))).split(",") if k.strip()]

    with open(args.input, "r", encoding="utf-8-sig") as f:
        data = json.load(f)
    if not isinstance(data, list):
        sys.exit("输入 JSON 必须是数组")

    existing = set()
    if args.existing:
        try:
            with open(args.existing, "r", encoding="utf-8-sig") as f:
                prev = json.load(f)
            existing = {item_key(x) for x in (prev if isinstance(prev, list) else [])}
        except FileNotFoundError:
            existing = set()

    total_in = len(data)
    cutoff = date.today() - timedelta(days=days) if days and days > 0 else None

    # 1) 去重（同键保留热度更高者）
    dedup = {}
    for it in data:
        k = item_key(it)
        if k not in dedup or parse_num(it.get("likes")) > parse_num(dedup[k].get("likes")):
            dedup[k] = it
    after_dedup = len(dedup)

    accepted, unknown_date, excluded = [], [], []
    for k, it in dedup.items():
        p = it.get("platform", "other")
        if plats and p not in plats:
            excluded.append((k, "平台不在范围", it)); continue
        if kws and not any(kw in str(it.get("title", "")) for kw in kws):
            excluded.append((k, "标题未命中行业关键词", it)); continue
        d = parse_date(it.get("publish_time"))
        if cutoff:
            if d is None:
                unknown_date.append(it); continue
            if d < cutoff:
                excluded.append((k, f"超出近{days}天时间窗", it)); continue
        likes = parse_num(it.get("likes"))
        plays = parse_num(it.get("plays"))
        metric_val = plays if (args.metric == "heat" and p == "baidu") else likes
        if min_likes and metric_val < min_likes:
            excluded.append((k, f"未达点赞阈值{min_likes}（当前{metric_val}）", it)); continue
        it["_new"] = k not in existing
        accepted.append(it)

    accepted.sort(key=lambda x: parse_num(x.get("likes")), reverse=True)

    summary = {
        "task": args.task or "",
        "input": total_in, "after_dedup": after_dedup,
        "accepted": len(accepted), "new": sum(1 for x in accepted if x["_new"]),
        "unknown_date": len(unknown_date), "excluded": len(excluded),
        "min_likes": min_likes, "days": days, "platforms": plats or "全部",
        "keywords": kws,
    }

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(accepted, f, ensure_ascii=False, indent=2)

    # Markdown
    L = []
    title = f"行业爆款清单：{args.task}" if args.task else "行业爆款清单"
    L.append(f"# {title}（{date.today()}）")
    L.append("")
    L.append(f"> 口径：近{days or '不限'}天、点赞≥{min_likes or '不限'}、"
             f"平台 {summary['platforms'] if isinstance(summary['platforms'], str) else '/'.join(summary['platforms'])}；"
             f"采集时点近似值，有米有数数据为第三方估算。")
    L.append("")
    L.append(f"**筛选统计**：输入 {total_in} → 去重后 {after_dedup} → 入选 {len(accepted)}"
             f"（其中新增 {summary['new']}）；日期待核实 {len(unknown_date)}，剔除 {len(excluded)}。")
    L.append("")
    groups = {}
    for it in accepted:
        groups.setdefault(it.get("platform", "other"), []).append(it)
    for p in PLATFORM_ORDER + [x for x in groups if x not in PLATFORM_ORDER]:
        arr = groups.get(p)
        if not arr:
            continue
        L.append(f"## {PLATFORM_LABEL.get(p, p)}（{len(arr)}）")
        L.append("| 排名 | 新增 | 作者 | 标题 | 点赞 | 评论 | 转发 | 投放天数 | 发布 | 商品/广告主 | 链接 |")
        L.append("|---|---|---|---|---|---|---|---|---|---|---|")
        for i, it in enumerate(arr, 1):
            L.append(
                f"| {i} | {'🆕' if it.get('_new') else '—'} | {esc(it.get('author'))} | {esc(it.get('title'))} "
                f"| {parse_num(it.get('likes')) or '-'} | {parse_num(it.get('comments')) or '-'} "
                f"| {parse_num(it.get('shares')) or '-'} | {parse_num(it.get('ad_days')) or '-'} "
                f"| {esc(it.get('publish_time'))} | {esc(it.get('product'))} | {esc(it.get('url'))} |")
        L.append("")
    if unknown_date:
        L.append(f"## 日期待核实（{len(unknown_date)}，未计入达标）")
        for it in unknown_date:
            L.append(f"- {PLATFORM_LABEL.get(it.get('platform'), it.get('platform'))}｜"
                     f"{esc(it.get('author'))}｜{esc(it.get('title'))}｜{esc(it.get('url'))}")
        L.append("")

    out = "\n".join(L)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(out)
    print(json.dumps(summary, ensure_ascii=False))
    if args.output:
        print(f"已写入 {args.output}")
    elif not args.json_out:
        print(out)


if __name__ == "__main__":
    main()
