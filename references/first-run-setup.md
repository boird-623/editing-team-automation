# 首次运行向导（First-Run Setup）

> 设计原则：**首次使用的人自己决定一切**——用哪些能力、要不要扫码登录、要不要定时、几点跑、推到哪、登录失效怎么办。
> 向导**不预设**任何时间/推送地/失效策略；**定时默认关闭，登录默认按需扫码**；未经用户当面确认，**不得创建任何定时任务、不得写入任何线上飞书资源**。

## 触发条件（满足其一即进入向导）
- 本机没有 `D:\豆包工作区\config.json`，或其中 `setup.completed != true`；
- 用户说"初始化 / 安装 / 第一次用 / 配置 / 部署 / 开始用"。
- 之后用户说"重新配置 / 改下定时 / 改下登录"，也走对应小节，不必重跑全部。

## 向导步骤（分步进行，每步可核验；需要选择时用 `interaction.ask`，一次最多 4 问）

### 第 1 步：工作区与依赖
1. 建 `D:\豆包工作区\`（用户要换路径就用用户路径）及子目录：
   `00_规则库 01_竞品下载 02_待修复 03_修复完成 04_待预审 05_预审报告 06_报表导出 tools`。
2. 把 `scripts/extract.py`、`scripts/upscale.bat` 与 `ad-cost-daily/scripts/parse_cost.py` 复制到 `tools\`；
   把 `hot-radar/scripts/filter_hotlist.py` 复制到 `tools\`。
3. 运行 `python scripts/check_env.py`（**只检测不安装**）。必需：ffmpeg、ffprobe、Python；缺什么明确告诉用户去装，**不要替用户下载安装**。
4. 生成 `config.json`：交付默认会话直出、`feishu.enabled=false`、`schedule.enabled=false`、各平台登录态 false（模板见文末）。

### 第 2 步：能力选择（多选，决定后续登录与定时只问相关项）
用 `interaction.ask` 让用户勾选要用的能力：
- `hot_radar` 爆款抓取/分析/开头（每日爆款、行业素材、对标账号、深度分析、开头制作）
- `hot_clip_repair` 素材修复/溯源/找原创
- `pre_review` 素材预审（违禁词/过审）
- `ad_cost` 四平台消耗日报/周报
默认全选；用户只选部分时，后续步骤和定时任务**只围绕已选能力**展开，不推销、不补装其它能力。

### 第 3 步：交付方式（单选或多选）
- 豆包会话直接给（默认，零配置）
- 飞书多维表：需要用户**当场提供表链接并明确授权写入**，写进 `feishu.base_url`、`feishu.enabled=true`；没给链接就保持关闭，不写死任何链接。
- 飞书群 / 邮件 / 本地 Excel：用户明确要才配，记录到 `delivery`。
- 说明：会话直出与本地存档始终保留；飞书只是额外出口。

### 第 4 步：登录向导（只对"已选能力"用到的平台，逐个扫码；用户可跳过）
规则：**逐个打开、逐页确认、一次只交接一个平台**；登录/扫码/验证码一律 `interaction.request_action(type="browserControl")`，**不绕过、不代填密码、不碰验证码**；用户扫完回到页面，重新 snapshot 确认登录成功后，把结果（true/false + 时间）写进 config 的 `schedule.login`，再开下一个平台。

| 平台 | 何时需要 | 地址 | config 键 |
|---|---|---|---|
| 有米有数 youmi | 选了 hot_radar（爆款/行业/对标主通道） | 以用户给的有米有数域名为准 | `login.youmi` |
| 抖音·巨量引擎 oceanengine | 选了 ad_cost（也用于爆款补充） | https://ad.oceanengine.com | `login.oceanengine` |
| 视频号·腾讯广告 tencent | 选了 ad_cost | 腾讯广告投放管理后台 | `login.tencent` |
| 快手·磁力引擎 kuaishou | 选了 ad_cost（也用于爆款补充） | https://ad.e.kuaishou.com | `login.kuaishou` |
| 百度营销 baidu | 选了 ad_cost（也用于好看视频补充） | https://e.baidu.com | `login.baidu` |

每个平台问一句"现在扫码登录吗？（可跳过，以后随时补）"；跳过的平台对应能力在需要时会再提醒。记录登录有效期（页面或会员到期提示，写运维说明），作为后续巡检依据。

### 第 5 步：定时任务（默认不开，由用户决定）
先问**总开关**："要现在配置每天自动跑吗？"
- 选"**先不开，需要时再说**"（默认）：`schedule.enabled=false`，向导结束，以后随时说"配定时"再进本步。
- 选"配置"：继续逐项确认，**每项任务都要单独确认开不开、几点跑**（不强制全开）：
  - 每日爆款（`daily_hot`）：哪些平台、按产品/行业、只新增（默认 true）、推送格式。
  - 行业素材（`industry_*`）：选已配置的行业任务、时间窗。
  - 消耗日报（`cost_daily`）：拉"昨天"、时间（平台数据上午才稳定，建议 09:00 后）、推送地、失败处理。
  - 周报（`weekly_report`）：周几几点。
- 必问的运行前提（影响可行性，如实告知）：
  1. 电脑是否**工作日开机、豆包常驻、不锁屏**（锁屏/休眠/关机时浏览器自动化可能失败）；
  2. 某次任务遇到登录失效/验证码时：**跳过并告警**（推荐）/ 暂停等扫码 / 改手动导出；
  3. 告警与结果推送到哪里（复用第 3 步交付方式）。
- 只有用户**明确确认任务清单与时间后**，才 Read `doubao-cron-scheduler` 的 SKILL.md 并逐条创建（先 Read 再建，建完回报任务清单与下次触发时间）。文案/cron 见 `scheduled-tasks.md`。

### 第 6 步：业务配置（可留空，以后补）
- 剪辑师代号映射（`cost.editor_code_map`）：先给"代号:姓名"，可后补。
- 行业关键词 / 点赞阈值 / 时间窗（`hot_radar.industry_tasks`）：已内置食品饮料、个护保养默认值，可让用户校正。
- 对标账号清单（`hot_radar.benchmark_accounts`）：用户给链接/ID，没有先留空。

### 第 7 步：完成
- 把 `setup.completed` 置 `true`、写 `setup.wizard_version`、`setup.finished_at`。
- 向用户汇总：工作区路径、依赖结果、已选能力、各平台登录状态、交付方式、定时是否启用（启用则列任务表）、哪些项待补。
- 明确告知：**这是"开机常驻+偶尔扫码"的半自动，不是扫一次永久无人值守**；登录失效会按其选择跳过并告警。

## 落盘 config 模板（首跑前的中性状态，未决项留空/null）
```json
{
  "setup": { "completed": false, "wizard_version": "1.0", "finished_at": "" },
  "delivery": { "mode": "direct_to_chat", "extra": [] },
  "feishu": { "enabled": false, "base_url": "", "enabled_modules": [] },
  "modules": {
    "hot_radar": true, "hot_clip_repair": false, "pre_review": false, "ad_cost": false
  },
  "schedule": {
    "enabled": false,
    "machine_always_on": null,
    "on_expiry": "",
    "push_dest": [],
    "login": { "youmi": false, "oceanengine": false, "tencent": false, "kuaishou": false, "baidu": false },
    "login_checked_at": { },
    "tasks": {
      "daily_hot": { "enabled": false, "time": "", "platforms": [], "new_only": true },
      "cost_daily": { "enabled": false, "time": "", "target": "yesterday" },
      "weekly_report": { "enabled": false, "weekday": "", "time": "" }
    }
  }
}
```
> 模块默认值：以用户第 2 步实际选择覆盖；上面仅示例。`hot_radar` 是主能力，其余按用户勾选。

## 硬约束
- 不创建任何 cron，除非用户在第 5 步明确确认；不因"反正以后要用"而预建。
- 不向飞书建表/写表/发群，除非用户当场给链接并授权（第 3 步）。
- 登录扫码只交接、不代操作；不保存密码、不读 Cookie 内容。
- 缺依赖只提示安装，不自动下载。
- 任何步骤的选项若用户没定，保持空值并在完成汇总里标"待补"，不替用户做决定。
