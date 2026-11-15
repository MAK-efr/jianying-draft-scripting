# 剪映草稿脚本化（jianying-draft-scripting）

用 Python 直接生成 / 修改 / 导出剪映专业版（JianyingPro / CapCut 国内版）草稿，**不开界面、不碰鼠标**。

剪映把工程存在 `draft_content.json` 里，且文件是加密的、没有任何开放 API 或 CLI。这个项目把三层都打通了：

| 层 | 做法 | 状态 |
|---|---|---|
| 读 | 借剪映自己的 `videoeditor.dll` 解密（`jy-draftc`） | ✅ 已实测（6.0.1 / 8.9.0） |
| 写 | 生成明文草稿，剪映打开时自己加密落盘；或改完再加密回去 | ✅ 已实测（`.load.bak` md5 与写入逐字节一致） |
| 出片 | 无头导出（**必须用与工具同版本的引擎**） | ✅ 已实测（11.6.0.14552 引擎） |

---

## 能做什么（全部有实测证据）

| 能力 | 说明 | 关键实测数据 |
|---|---|---|
| 从零建稿 | 一份 JSON 清单 → 草稿，不克隆任何现有工程 | 14.6s 成片，5 条轨，时间轴与清单逐项对齐 |
| 拼接 / 裁剪 | `clips[]` 顺序拼接，`trim=[起,止]` | — |
| 变速 | `speed` | 1.4× 成片与源片对齐 MAD 6.24（未变速则 21.43） |
| 画中画 | `overlays[]`：`scale` / `x` / `y` / 不透明度包络 | 海报框内 MAD 63.6 vs 框外 5.2 |
| 叠化转场 | 两条视频轨 + `KFTypeAlpha` 不透明度关键帧（自建，不依赖特效包） | 反解上层 α：0.333 / 0.600 / 1.000 与设定逐点吻合 |
| **真转场包** | `transitions[]`，按名称查元数据 | 推近 1.95s MAD 65.29；水墨 1.90s 85.45（挂错位置恒 0） |
| **滤镜（调色）** | `filters[]`，`materials.effects` + `filter` 轨 | 平均 RGB (92,92,103)→(100,98,127)，MAD 14.65 |
| 音频淡入淡出 | 独立音频段 `audio_fades` | 尾部 −15.1 dB，音频完整到结尾 |
| 原声淡化 | 视频段 `KFTypeVolume` 音量关键帧 | 关键帧时刻 = 输出时刻 × 速度 + trim 起点 |
| 静音 | `segment.volume = 0` | 全程 −91.0 dB |
| SRT 字幕 | `jy_srt.py` 批量灌入 | 底部近白像素 5947/6295/**0**（空档）/7896 |
| 导出参数 | 分辨率 / 帧率 / 编码 / 码率 | 720×1280 / 24fps / hvc1 全部生效 |

---

## 三个必须知道的前提

1. **资源必须在本地**。转场、滤镜、贴图都是从 `%LOCALAPPDATA%\JianyingPro\User Data\Cache\{effect,artistEffect}\` 读的。没下载过的资源，写再对也不渲染——本机 453 条转场里只缓存了 2 条。先在剪映里点用一次即可缓存。
2. **转场要带 `path`**，且挂在**接缝前**那一段。照 `pyJianYingDraft` 的写法（不导出 `path`）会被引擎静默丢弃。
3. **出片要用匹配版本的引擎**。工具与引擎版本不一致时导出会崩（8.9.0 引擎崩、11.6.0.14552 引擎成功）。

---

## 安装

```
git clone https://github.com/<you>/jianying-draft-scripting.git
```

放到 WorkBuddy / Claude 的技能目录即可被当作 Skill 加载：

```
~/.workbuddy/skills/jianying-draft-scripting/
```

依赖：Python 3.9+（只用标准库），Windows（剪映本身只有 Windows / macOS 版，本项目实测于 Windows）。

`scripts/bin/jy-draftc.exe` 是第三方工具（见文末），已随仓库提供；也可用环境变量指向别处：

```
set JY_DRAFTC=D:\tools\jy-draftc.exe
set JY_DIR=C:\Users\<you>\AppData\Local\JianyingPro\Apps\11.6.0.14552
```

`JY_DIR` 一般不用设——脚本会自动在 `Apps\` 下找含 `videoeditor.dll` 的最新版本目录。

---

## 快速开始

```bash
# 0) 体检：加密回环、ABI、导出是否可用
python scripts/jy.py doctor

# 1) 从清单建稿
python scripts/jy_build.py examples/manifest_basic.json "%LOCALAPPDATA%\JianyingPro\User Data\Projects\com.lveditor.draft\我的片子"

# 2) 无头导出
python scripts/jy.py export --jy-dir <11.6 引擎目录> --out out.mp4 "<草稿目录>"

# 3) 读回 / 改 / 校
python scripts/jy.py info "<草稿目录>"
python scripts/jy.py verify "<草稿目录>"

# 4) 往已有草稿灌字幕
python scripts/jy_srt.py subs.srt "<草稿目录>" --size 5.0 --y -0.80
```

清单长这样（时间单位：秒）：

```json
{
  "canvas": "1280x720",
  "fps": 30,
  "clips": [
    {"path": "a.mp4", "trim": [2.0, 10.0], "fade_out": 0.9},
    {"path": "b.mp4", "trim": [0.8, 10.0], "speed": 1.4}
  ],
  "transitions": [{"name": "推近", "at": 0, "dur": 1.0}],
  "filters": [{"name": "电影增质", "effect_id": "7430733313419005238", "value": 1.0}],
  "overlays": [
    {"path": "b.mp4", "start": 7.2, "dur": 0.8, "trim": [0.0, 0.8], "alpha_in": 0.8},
    {"path": "poster.jpg", "start": 2.0, "dur": 3.0, "scale": 0.3, "x": 0.45, "y": 0.55}
  ],
  "texts": [{"content": "标题", "start": 0.3, "dur": 3.2, "size": 5.2, "y": 0.82}],
  "audio": [{"path": "a.mp4", "trim": [2.0, 10.0], "start": 0, "dur": 8.0, "fade_out": 0.9}]
}
```

---

## 目录

```
SKILL.md                 技能正文：能力矩阵、12 条实测坑、导出与排障
scripts/jy.py            草稿读写 / 加解密 / 导出 / doctor
scripts/jy_build.py      清单 → 草稿（核心）
scripts/jy_add.py        往已有草稿追加 text / image / audio / transition
scripts/jy_srt.py        SRT → 字幕轨
scripts/bin/             jy-draftc.exe（第三方，见 NOTICE）
references/              空草稿骨架、453 条转场元数据
examples/                可直接跑的清单示例
```

---

## 不做什么

- 不调用剪映的云端 AI 功能（文稿匹配、智能字幕、AI 调色等），这些依赖登录态与网络；
- 不解锁 VIP 素材的**下载**（能不能导出与 VIP 无关，与"资源在不在本地"有关）；
- 不做界面自动化。GUI 点击成本高、易假成功，本项目只走文件层。

---

## 第三方

`scripts/bin/jy-draftc.exe` 为第三方开源工具，MIT License © 2026 wenshui330，随附其原始说明文档。本项目仅调用其命令行，未修改二进制。

`references/transition_meta.py` 的转场元数据整理自 [pyJianYingDraft](https://github.com/GuanYixuan/pyJianYingDraft)（MIT）。

`references/draft_skeleton.json` 是从剪映实际工程中提取的空骨架结构，仅含字段结构、不含任何素材内容。

---

## 许可

本项目代码 MIT。详见 `LICENSE` 与 `NOTICE.md`。

## 免责

仅用于处理你自己有权访问和修改的本地草稿文件。请遵守剪映的用户协议与所在地法律。因使用本工具产生的任何后果由使用者自负。
