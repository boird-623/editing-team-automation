#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
合并四广告后台（巨量/腾讯/磁力/百度营销）导出的素材维度 xlsx：
统一字段与单位、按素材名归属剪辑师、写统一明细、做平台合计校验、输出汇总。

扫描目录下命名为  {平台}_{账户ID}.xlsx 的文件，平台代码 douyin/tencent/kuaishou/baidu。

用法:
  python parse_cost.py <导出目录> --date 2026-10-13 \
      [--editors 剪辑师名单.xlsx] [--register 素材登记表.xlsx] \
      [--backend-totals totals.json] -o 明细_2026-10-13.xlsx

--backend-totals: 后台账户总消耗 JSON，形如
  {"douyin": {"ACC1": 12345.6}, "kuaishou": {...}, ...}，用于合计校验。

输出 xlsx 含 4 个 sheet：明细 / 平台合计 / 剪辑师汇总 / 未归属；stdout 打印汇总 JSON。
"""
import argparse
import json
import re
import sys
from pathlib import Path

import pandas as pd

PLATFORM = {"douyin": "抖音", "tencent": "视频号", "kuaishou": "快手", "baidu": "百度"}

# 统一字段 -> 列名别名（规范化后"包含"匹配）
COLUMN_MAP = {
    "material_id": ["素材ID", "素材编号", "创意ID", "创意编号"],
    "material_name": ["素材名称", "素材名", "创意名称", "素材"],
    "cost": ["消耗金额", "总消耗", "花费", "消耗", "费用"],
    "impressions": ["展示量", "展现量", "曝光量", "展示", "展现", "曝光"],
    "clicks": ["点击量", "点击数", "点击"],
    "conversions": ["转化数", "转化量", "目标转化", "成交", "转化"],
    "play_3s_rate": ["3秒播放率", "3s播放率", "3秒播放比例"],
}

NAME_RE = re.compile(
    r"^(\d{6})_([A-Z]{2,4})_(.+?)_(KB|JQ|HJ|SP|AI)_(S\d+)_(V\d+)"
)


def norm_col(s):
    return re.sub(r"\s+", "", str(s)).replace("\n", "").replace("\r", "")


def num(v):
    """清洗为数值（消耗/展示/点击/转化），空值返回 0。"""
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", "").replace("，", "").replace("¥", "") \
        .replace("￥", "").replace("元", "").replace(" ", "")
    if s in ("", "-", "--", "—", "nan", "None"):
        return 0.0
    m = re.search(r"(-?\d+(?:\.\d+)?)\s*([万亿])?", s)
    if not m:
        return 0.0
    n = float(m.group(1))
    if m.group(2) == "万":
        n *= 1e4
    elif m.group(2) == "亿":
        n *= 1e8
    return n


def rate(v):
    """清洗为小数（率）；63.2%->0.632，纯数字按百分数/100。"""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip()
    if s in ("", "-", "--", "—", "nan"):
        return None
    has_pct = "%" in s
    m = re.search(r"(\d+(?:\.\d+)?)", s.replace(",", ""))
    if not m:
        return None
    n = float(m.group(1))
    if has_pct or n > 1:
        return round(n / 100, 4)
    return round(n, 4)


def find_header(raw):
    """在前 12 行找同时含 素材/创意ID 与 消耗/花费 的表头行。"""
    for i in range(min(12, len(raw))):
        cells = [norm_col(x) for x in raw.iloc[i].tolist()]
        joined = "|".join(cells)
        has_id = any(any(a in c for a in COLUMN_MAP["material_id"]) for c in cells)
        has_cost = any(any(a in c for a in COLUMN_MAP["cost"]) for c in cells)
        if has_id and has_cost:
            return i
    return None


def map_columns(headers):
    """返回 统一字段 -> 实际列索引。"""
    result = {}
    for field, aliases in COLUMN_MAP.items():
        for idx, h in enumerate(headers):
            if idx in result.values():  # 该列已被其他字段占用，跳过
                continue
            if any(a in h for a in aliases):
                result[field] = idx
                break
    return result


SUMMARY_WORDS = ("合计", "小计", "总计", "汇总", "本页")


def cstr(v):
    """单元格转干净字符串，NaN/None -> 空串。"""
    if v is None:
        return ""
    if isinstance(v, float) and pd.isna(v):
        return ""
    s = str(v).strip()
    return "" if s in ("nan", "None", "NaN") else s


def read_one(path):
    raw = pd.read_excel(path, header=None, dtype=object)
    hr = find_header(raw)
    if hr is None:
        return [], f"未识别表头（需含素材ID与消耗列）: {path.name}"
    headers = [norm_col(x) for x in raw.iloc[hr].tolist()]
    cmap = map_columns(headers)
    rows = []
    for _, r in raw.iloc[hr + 1:].iterrows():
        vals = r.tolist()

        def cell(field):
            idx = cmap.get(field)
            return vals[idx] if idx is not None and idx < len(vals) else None
        mid = cstr(cell("material_id"))
        mname = cstr(cell("material_name"))
        if not mname:
            continue
        # 跳过合计/小计/汇总行
        if any(w in mid for w in SUMMARY_WORDS) or any(w in mname for w in SUMMARY_WORDS):
            continue
        rows.append({
            "material_id": mid,
            "material_name": mname,
            "cost": round(num(cell("cost")), 2),
            "impressions": int(num(cell("impressions"))),
            "clicks": int(num(cell("clicks"))),
            "conversions": int(num(cell("conversions"))),
            "play_3s_rate": rate(cell("play_3s_rate")),
        })
    return rows, None


def load_editors(path):
    if not path or not Path(path).exists():
        return {}
    df = pd.read_excel(path, dtype=object)
    cols = [str(c) for c in df.columns]
    code_col = next((c for c in cols if "代号" in c or "code" in c.lower()), None)
    name_col = next((c for c in cols
                     if c != code_col and "代号" not in c
                     and ("姓名" in c or "名字" in c or "剪辑师" in c or "name" in c.lower())), None)
    if not code_col or not name_col:
        return {}
    return {cstr(r[code_col]): cstr(r[name_col]) for _, r in df.iterrows() if cstr(r[code_col])}


def load_register(path):
    if not path or not Path(path).exists():
        return {}
    df = pd.read_excel(path, dtype=object)
    cols = [str(c) for c in df.columns]
    id_col = next((c for c in cols if "素材" in c and ("ID" in c.upper() or "编号" in c)), None)
    ed_col = next((c for c in cols
                   if "代号" not in c and ("剪辑师" in c or "归属" in c or "姓名" in c or "名字" in c)), None)
    if not id_col or not ed_col:
        return {}
    return {cstr(r[id_col]): cstr(r[ed_col]) for _, r in df.iterrows() if cstr(r[id_col])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir", help="导出目录，含 {平台}_{账户}.xlsx")
    ap.add_argument("--date", required=True, help="数据日期 YYYY-MM-DD")
    ap.add_argument("--editors", default="")
    ap.add_argument("--register", default="")
    ap.add_argument("--backend-totals", default="")
    ap.add_argument("-o", "--output", default="")
    args = ap.parse_args()

    d = Path(args.dir).expanduser()
    if not d.is_dir():
        sys.exit(f"目录不存在: {d}")
    editors = load_editors(args.editors)
    register = load_register(args.register)
    totals = {}
    if args.backend_totals and Path(args.backend_totals).exists():
        totals = json.loads(Path(args.backend_totals).read_text(encoding="utf-8"))

    details, warnings, seen = [], [], {}
    for f in sorted(d.glob("*.xlsx")):
        stem = f.stem
        if "_" not in stem:
            continue
        platform, account = stem.split("_", 1)
        if platform not in PLATFORM:
            continue
        rows, err = read_one(f)
        if err:
            warnings.append(err)
            continue
        for row in rows:
            m = NAME_RE.match(row["material_name"])
            code = m.group(2) if m else ""
            name = editors.get(code, "")
            if not name:
                name = register.get(row["material_id"], "")
            if not name:
                name = "未归属"
            rec = {"date": args.date, "platform": PLATFORM[platform],
                   "platform_code": platform, "account_id": account,
                   "editor_code": code, "editor_name": name, **row}
            key = (args.date, platform, account, row["material_id"])
            seen[key] = rec  # 同键覆盖，应对回刷
    details = list(seen.values())

    # 平台合计校验
    psum, warn_rows = [], []
    for code, label in PLATFORM.items():
        sub = [x for x in details if x["platform_code"] == code]
        if not sub:
            continue
        for account in sorted({x["account_id"] for x in sub}):
            ds = sum(x["cost"] for x in sub if x["account_id"] == account)
            bt = (totals.get(code, {}) or {}).get(account)
            diff = round(abs(ds - bt) / bt, 4) if bt else None
            warn = bool(bt and diff is not None and diff > 0.01)
            if warn:
                warn_rows.append(f"{label}/{account} 差异率 {diff:.2%}（明细 {ds:.2f} / 后台 {bt:.2f}）")
            psum.append({"平台": label, "账户": account, "明细消耗": round(ds, 2),
                         "后台总消耗": bt if bt is not None else "未提供",
                         "差异率": f"{diff:.2%}" if diff is not None else "-",
                         "告警": "是" if warn else ""})

    # 剪辑师汇总
    ed = {}
    for x in details:
        e = ed.setdefault(x["editor_name"], {"消耗": 0.0, "素材": set()})
        e["消耗"] += x["cost"]
        e["素材"].add(x["material_id"] or x["material_name"])
    ed_rows = [{"剪辑师": k, "消耗": round(v["消耗"], 2), "素材数": len(v["素材"])}
               for k, v in ed.items()]
    ed_rows.sort(key=lambda r: -r["消耗"])

    unowned = [{"素材ID": x["material_id"], "素材名": x["material_name"],
                "平台": x["platform"], "消耗": x["cost"]}
               for x in details if x["editor_name"] == "未归属"]

    if args.output:
        out = Path(args.output).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        with pd.ExcelWriter(out, engine="openpyxl") as w:
            pd.DataFrame(details).to_excel(w, sheet_name="明细", index=False)
            pd.DataFrame(psum).to_excel(w, sheet_name="平台合计", index=False)
            pd.DataFrame(ed_rows).to_excel(w, sheet_name="剪辑师汇总", index=False)
            pd.DataFrame(unowned).to_excel(w, sheet_name="未归属", index=False)

    total_cost = round(sum(x["cost"] for x in details), 2)
    summary = {
        "date": args.date, "rows": len(details), "total_cost": total_cost,
        "platform_cost": {p: round(sum(x["cost"] for x in details if x["platform_code"] == c), 2)
                          for c, p in PLATFORM.items()
                          if any(x["platform_code"] == c for x in details)},
        "editor_ranking": ed_rows,
        "unowned_count": len(unowned), "unowned_cost": round(sum(u["消耗"] for u in unowned), 2),
        "total_warnings": warn_rows + warnings,
        "output": str(args.output) if args.output else "",
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if warn_rows:
        sys.exit(0)  # 告警已在汇总与表内，不阻断


if __name__ == "__main__":
    main()
