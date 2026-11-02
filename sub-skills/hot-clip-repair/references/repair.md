# 画质修复与叠加擦除

调用前先加载 `byted-mediakit-video` 技能，读 `../byted-mediakit-shared/SKILL.md`，
并 Read 对应工具的 reference；参数以实时 `--schema` 为准。

## 一、AI 画质增强（enhance-video）

命令：`mediakit-cli video enhance-video`，异步，返回 `task_id` 后 `query-task` 轮询。

短视频带货素材的推荐口径：

| 目标 | 参数 |
|---|---|
| 默认 1080p（够用） | `--tool-version standard --scene ugc --resolution 1080p --bitrate-level high` |
| 2K 高清 | `--tool-version standard --scene ugc --resolution 2k --bitrate-level high` |
| 极致修复 | `--tool-version professional --resolution 2k --bitrate-level high`（不用 scene，professional 不支持 scene） |

- `--video-url` 直接传本地文件路径（CLI 自动上传）。
- `--scene ugc` 是 UGC/短视频场景预设，仅 standard 生效。
- 不指定 `--fps`，保持原帧率；不指定 `--bit-depth`（默认 8bit/H.264，网页兼容性最好）。
- 输入限制：分辨率最高 2K，长边 360–2560、短边 360–1440；竖屏 720×1280 可直接超到 1080×1920。
- `standard` 一般每段几分钟；`professional` / 2K / 4K 常超过单次 9 分钟轮询上限，
  `query-task` 返回 running 且 exit 0 是预期，用同一 task_id 继续 `--poll-complete`。
- 终态 `result.video_url` 是 24 小时有效的临时链接，拿到立即下载到本地。
- 下载后必须保留原音频：若云端结果音轨异常，用 ffmpeg 把原音频合回（见第四节命令）。

## 二、文字类叠加擦除（erase-video-subtitle-pro）

命令：`mediakit-cli video erase-video-subtitle-pro`，异步。

- 底部字幕用 `--mode Subtitle`（默认只处理下半画面，且用文字高度/居中过滤，避免误擦大标题）。
- 底部免责声明、右侧竖排提示、人名地名等非字幕文字用 `--mode Text`，
  并**显式传 `--erase-ratio-location` 框选**（归一化坐标，左上角(0,0)、右下角(1,1)，最多 20 框）。
- 推荐 `--model-version v5`（优化带阴影字幕、误擦与闪烁）。
- 每处文字一个框，框稍微比文字大一圈，宁可多框不框到产品标签。
- Windows PowerShell 传 JSON 必须用 `--%` 停止解析，内部双引号写 `\"`，例如：
  ```powershell
  mediakit-cli video erase-video-subtitle-pro --video-url .\in.mp4 --mode Text --model-version v5 --% --erase-ratio-location "[{\"top_left_x\":0.0,\"top_left_y\":0.9,\"bottom_right_x\":1.0,\"bottom_right_y\":0.99}]"
  ```
- 只擦某时间段可用 `--time-segment-filter`（selected/skip + 起止秒）。
- 输出分辨率最高 1080P：若要 2K，先擦文字再增强（顺序：擦文字 → enhance-video 超分）。
- 云端逐帧目检：重点看文字区域背景是否自然、产品瓶身文字是否被误擦。

## 三、图形类贴纸（纯色块 / 爆款热销角标 / 卡通印章 / 手绘标记）

这类不是文字，云端 OCR 不擦，需要本地逐帧修复，用 `scripts/inpaint_box.py`：

```bash
# 依赖（首次）：python -m pip install opencv-python-headless numpy imageio-ffmpeg
# 框格式：归一化 x,y,w,h（左上角x,y + 宽高，均为 0-1），可重复 --box
python scripts/inpaint_box.py input.mp4 output.mp4 \
  --box 0.55,0.93,0.30,0.06 \
  --box 0.82,0.16,0.16,0.42 \
  --radius 5
```

- 脚本逐帧对框内做修复（邻域纹理传播 + 羽化合成），自动用 ffmpeg 合回原音频，
  输出 H.264、保持原帧率/分辨率。
- 修复策略：纯色/渐变背景用 `--method patch`（复制邻近条带），复杂背景用 `--method inpaint`（默认 TELEA）。
- 处理顺序建议：先本地擦图形贴纸 → 再云端擦文字（或反之）→ 最后 enhance-video 统一超分，
  这样最终只有一次超分，画面最干净。
- 必须逐帧抽检结果（开头/中段/结尾各若干帧），确认没有硬涂抹、闪烁、残影。

## 四、成片校验清单（交付前逐项过）

1. 抽帧目检：文字/贴纸已消失，背景自然，产品标签、人物、食物细节无变形。
2. `probe-video-metadata` 或 ffprobe：分辨率=目标档位（1080×1920 / 2K）、帧率与原片一致、
   时长与原片一致（误差 < 0.2s）。
3. 音频：有音轨、内容与原片一致、口型/节奏对齐；若云端掉音轨，用 ffmpeg 合回：
   ```bash
   ffmpeg -y -i repaired_noaudio.mp4 -i original.mp4 -map 0:v -map 1:a -c:v copy -c:a aac -shortest out.mp4
   ```
4. 编码：H.264（网页/飞书可直接播放）；不要输出 H.265 除非用户明确要。
5. 做了擦除时保留未擦除母版，便于回溯。
