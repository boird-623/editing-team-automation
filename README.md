# editing-team-automation · 剪辑团队自动化套件

> 信息流广告剪辑团队的四个高频环节做成可编排的自动化流水线：**爆款雷达 → 素材修复/溯源 → 素材预审 → 消耗日报**，外加一个交互式首次初始化向导与可选定时任务。
>
> Ad-creative team automation suite: hot-radar, clip repair & origin tracing, material pre-review, and ad-cost daily reporting, orchestrated by one entry skill.

这是一个在豆包（Doubao）工作环境中运行的 monorepo：1 个总控技能 + 4 个可独立使用的子技能。每个子技能既是独立技能，也被总控按意图路由与串联。

## 组成

| 技能 | 干什么 | 关键产物 |
|---|---|---|
| `editing-team-automation`（总控） | 首次初始化向导、环境检查、交付方式与定时配置、按意图路由 | 工作区目录 + config.json |
| `hot-radar` 爆款雷达 | 有米有数+三平台网页抓取竞品/行业/对标账号爆款，逐条拆解，出前 3 秒开头分镜 | 爆款清单 + 拆解报告 + 开头脚本 |
| `hot-clip-repair` 素材修复 | 画质增强（云端/本地兜底）、文字/贴纸擦除、原创溯源、下载原片、授权草稿 | 修复成片 + 溯源报告 |
| `material-pre-review` 预审官 | 违禁词词库扫描 + 语义复核 + 技术规格与制作瑕疵检查 | 素材预审报告 |
| `ad-cost-daily` 消耗日报 | 四个广告后台拉数、字段归一、按剪辑师归属、合计校验、日报/周报 | 合并明细 Excel + 日报 |

## 仓库结构

```
SKILL.md                        # 总控：路由表、初始化向导入口、跨环节数据流、全局约束
references/
  first-run-setup.md            # 首次运行向导（能力/交付/登录/定时全部用户决定）
  feishu-base-schema.md         # 可选飞书数据中台 7 张表结构 + 本地 config 字段
  scheduled-tasks.md            # T0-T3 定时任务清单（默认关闭，时间仅参考）
scripts/
  check_env.py                  # 依赖检测（只报不装）
  extract.py                    # 视频抽帧 + 音频提取（模型读不了视频时的降级通道）
  upscale.bat                   # 本地 Real-ESRGAN 超分兜底（无云端增强时）
sub-skills/
  hot-radar/                    # SKILL.md + references×2 + scripts×2
  hot-clip-repair/              # SKILL.md + references×2 + scripts×1
  material-pre-review/          # SKILL.md + wordlib.json + rules.md + scan_words.py
  ad-cost-daily/                # SKILL.md + backends.md + parse_cost.py
```

## 设计要点

- **首跑向导全部交互式决定**：用哪些能力、要不要扫码、要不要定时、几点跑，一律用户当面确认，不预设；定时默认关闭。
- **会话直出为默认交付**：下载的视频、Excel、报告直接发用户；飞书多维表是可选出口，用户给链接并授权才写。
- **确定性脚本承担可计算部分**：行业筛选阈值/时间窗/去重（`filter_hotlist.py`）、违禁词扫描（`scan_words.py`）、四后台字段归一与剪辑师归属（`parse_cost.py`）。
- **命名规范即主键**：素材名 `YYMMDD_剪辑师代号_产品_类型_脚本号_版本` 贯穿全链路，消耗自动归属到人，归属不了进「未归属」清单不强猜。
- **诚实降级**：没有的工具能力明说并降级（本地超分兜底、词库缺失时语义审查并标注局限）；拿不到的数据写「未获取」，不编造、不用估算凑数。
- **全程只读广告后台**；登录/验证码一律交接用户扫码，不绕风控。

## 独立使用脚本

```bash
# 依赖检查
python scripts/check_env.py

# 行业/对标/增量筛选（配合 config.json 的行业任务）
python sub-skills/hot-radar/scripts/filter_hotlist.py candidates.json --min-likes 100 --days 1

# 违禁词扫描（词库在同目录 assets/）
python sub-skills/material-pre-review/scripts/scan_words.py 口播.txt --lib sub-skills/material-pre-review/assets/wordlib.json

# 四后台导出合并（扫描目录下 douyin_账户.xlsx 等）
python sub-skills/ad-cost-daily/scripts/parse_cost.py 06_报表导出/2026-10-13 --date 2026-10-13 -o 明细.xlsx
```

依赖：Python 3.8+；`parse_cost.py` 需 pandas/openpyxl；视频相关需 ffmpeg（`check_env.py` 会检测）。

## 合规声明
- 广告后台只读，不改计划/预算/出价/素材状态；不绕过任何平台风控与验证码。
- 竞品视频仅入参考目录用于分析，不进投放素材目录；不去水印、不改 MD5、不做镜像规避原创检测。
- 预审结论是投放前自查参考，最终以平台官方审核为准；溯源结论一律标注「待人工确认」。
