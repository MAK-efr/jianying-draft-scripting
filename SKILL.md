---
name: jianying-draft-scripting
description: 用脚本（Python）程序化生成/批量生产剪映专业版（JianyingPro / CapCut 国内版）草稿，绕过"草稿文件被加密、无开放 API、无 CLI"的限制。当用户说"用剪映批量剪辑""脚本生成剪映草稿""剪映能自动化吗""用代码做个剪映项目""能不能直接调用剪映的 API/命令行"时使用。也适用于判断任意加密工程文件的国产桌面软件（剪映/必剪等）能否被第三方工具链驱动。
agent_created: true
---

# 剪映草稿脚本化生成（JianyingPro 6.x – 8.x）

## 核心结论（先记住这条）

**剪映的 `draft_content.json` 是加密的，但剪映"读得进明文"；而加密侧也已打通——回读/回写用 `jy-draftc` 借剪映自己的 DLL 加解密。两侧都能走。**

**已实测两个版本：6.0.1.11779（旧）与 8.9.0.13361（当前本机）—— 加解密均可用。**

| 方向 | 是否可行 |
|---|---|
| 脚本生成**明文**草稿 → 剪映打开 | ✅ 成立 |
| 剪映保存时自动加密落盘 | ✅ 成立（无需自己加密） |
| 读回剪映保存后的**加密**草稿 | ✅ **可做到** —— 用 `jy-draftc` 借剪映自己的 DLL 解密（见下节） |
| **改完明文再加密回去 → 剪映读得出改动** | ✅ **已实测闭环（两个版本）**：6.0.1 改画布 9:16→16:9 → 剪映 UI 显示 16:9；**8.9.0 改 1920×1014→1080×1920 → 剪映「草稿参数」显示 9:16，且 `.load.bak` 的 md5 与我写入文件逐字节相同** |
| 无头导出 MP4（不走界面） | ✅ **可做到**，但**必须用与工具同版本的引擎**。8.9.0 必崩；用 11.6.0.14552 引擎实测导出成功 1080×1920 / 30fps / 5.02s / 2.66 MB / 11.6 秒（特效与贴纸轨均已渲染）。详见下方「导出」节 |
| 走 GUI 自动化 / CLI / 官方 API | ❌ 剪映没有 |

**标准流程**：
- **从零生成**：脚本生成明文草稿 → 用户在剪映里精修 → 剪映自动加密。
- **接着改**：`jy.py info` 看清现状 → `jy.py set` 改字段 → 自动回加密 + 反向自证。

## ⛔ 能力边界（别过度宣称"剪映已完全可接入"）

被问"是不是没有接入不了的了"时，答案是**否**。按证据强度分三档：

| 档位 | 能力 | 证据 |
|---|---|---|
| ✅ **已实测** | 读草稿全部结构（画布/轨道/素材/时长） | 解密 14KB→10.7KB JSON，28 顶层键全解析 |
| ✅ **已实测** | 改**全局属性**：画布宽高/比例、素材绝对路径 | 改 1920×1014→1080×1920，剪映 UI 显示 9:16，`.load.bak` md5 一致 |
| ✅ **已实测** | 改**片段级属性**：`clip.scale`（缩放） | 1.0→1.5 后导出，画面明显放大（横带高 310px→440px），贴纸轨不受影响 |
| ✅ **已实测** | 克隆草稿（换 `draft_id`/`draft_name`/`fold_path`） | 剪映草稿列表正常识别、可打开 |
| ✅ **已实测** | **无头导出 MP4**（需 11.6.0 引擎，见下） | 1080×1920 / 30fps / 5.02s / 特效+贴纸轨均渲染 |
| ✅ **已实测** | **新增文本/字幕**（`materials.texts` + `type:"text"` 轨道） | 导出 5.02s，t=1.0s 帧内可见白字黑描边中文，**中文渲染正常** |
| ✅ **已实测** | **新增图片**（photo 素材 + `type:"video"` 轨道） | 导出后蓝块 bbox 372px ≈ 1080×0.35，与设定 scale 吻合 |
| ✅ **已实测** | **新增音频**（`materials.audios` + `type:"audio"` 轨道） | `volumedetect` mean −35.5 dB，同稿无音频时 −91.0 dB |
| ✅ **已实测** | **关键帧**（`common_keyframes` → `KFTypeScaleX/Y`） | scale 1.0→1.25，t=0.02s vs t=2.5s 帧差 53.72，目视放大 |
| ✅ **已实测** | **VIP 素材导出干净成片** | 「金粉飘落」`is_vip=True` 照常渲染，四角无水印，1250 行日志 `vip/watermark/license` 命中 0 |
| ✅ **已实测** | **从零建稿**（不克隆任何现有草稿） | `references/draft_skeleton.json` 空骨架 → 写 `draft_content.json` → 直接导出成功，剪映从未读过这条草稿 |
| ✅ **已实测** | **多素材拼接** | 3 段不同素材顺序接在一条视频轨，成片 A→B→C 顺序正确（靠素材内嵌帧号判定） |
| ✅ **已实测** | **变速 `speed`** | 第 3 段 `speed=2.0`，成片帧号 t=4.1/4.5/4.9 分别 `f006/f030/f054` ⇒ 每 0.4s 走 24 帧 = **60fps = 2×** |
| ✅ **已实测** | **导出参数**：分辨率 / 帧率 / 编码 / 码率 | `--size 720x1280 --fps 24 --codec hevc --bitrate 4000K` → 成片 `720x1280 / 24fps / hvc1` |
| ✅ **已实测** | **SRT 批量字幕** | `jy_srt.py demo.srt <草稿>` 灌 3 条 → 导出后 t=1.0/3.0/4.5s 分别显示「第一句 A 段 / 第二句 B 段 / 第三句 C 段」，准点切换且与顶部标题不冲突 |
| ✅ **已实测（推荐）** | **视频段自带原声的淡化**（`KFTypeVolume` 音量关键帧） | 关键帧时间基是**素材源时间**：`源时间 = 输出时间 × 速度 + trim 起点`。三例交叉验证：trim=2 写 7.1 → 实测 5.35 起淡；trim=4 写 8.0 → 4.30；trim=0 写 7.1 → 7.35（三者都含约 +0.25s 的检测偏置，扣除后严格等于 `设定 − trim`）。按公式换算后：trim[2,10] 写 9.1/10.0 → 实测 **7.1s 起淡**、7.9s −43.2 dB；trim[2,10] + `speed 2.0` 写 8.2/10.0 → 实测 **3.1s 起淡**。⇒ 不需要拆音轨，一处换算即可 |
| ❌ **实测不通** | **把 `audio_fades` 挂到视频段上** | 四种编码全试遍：①`audio_fades` 表 + 视频段引用 ②`videos[].audio_fade=600000`(µs) ③`=0.6`(秒) ④两者都写 —— 导出后**音频流 MD5 与无淡化版逐字节相同**（`fb369d6c…`），delta 恒 0.00。⇒ 这张表只服务独立音频轨 |
| ✅ **备用配方** | **原声淡化第二解法 = 视频段 `volume:0` + 同文件进音频轨带 `trim` + `audio_fades`** | 真实素材（Sintel，`trim=[2,10]`，淡出 0.9s）：前 7s 与源片差值 ≤0.1 dB，7.50s −1.0、7.80s −6.4、7.98s **−15.1 dB**，音频完整到 8.01s。音频段时间基从 0 起，不继承 `trim_start`，所以**不需要换算**。代价是多一条音轨、同文件引用两次；能用上一行时不必用它 |
| ✅ **已实测** | **叠化转场**（两条视频轨 + `KFTypeAlpha`） | 底层 clipA（红）2s×2，上层 clipB（绿）1.5s 起 2s、α 0→1 跨 0.5s。抽帧反推上层不透明度：1.667s 帧 **0.333**、1.80s **0.600**、2.10s **1.000**，与线性设定逐点吻合；1.80s 那帧可肉眼看到 A/B 字形重叠。恒定 α=0.5 版实测 0.497 ⇒ 静态与关键帧都有效 |
| ✅ **已实测** | **画中画**（叠加轨 + `clip.scale` / `clip.transform`） | `scale=0.5, x=0.3, y=-0.3` → 绿色块 bbox `x 288–647 / y 512–1151`（恰 360×640，即半幅），中心偏移 `(+108, +192)`。单位是「半个画布」：`x` 正为右、**`y` 负为下**，与 `images` / `texts` 的 y 语义一致 |
| ✅ **已实测** | **真转场特效包**（`materials.transitions` + 段 `extra_material_refs`） | 「推近」1.0s 挂第 0 段末尾 → 1.85s MAD 18.96、1.95s **65.29**；「水墨」0.5s → 1.80s 45.89、1.90s **85.45**，与无转场对照逐帧比对确认真的生效（数字两次独立导出完全一致）。**三个必要条件**：① 素材写进 `materials.transitions`；② **必须带 `path`** 指向本地缓存（照 pyJianYingDraft 只写 category/duration/effect_id/is_overlap/name/platform/resource_id/type，引擎静默丢弃）；③ **挂在接缝前的那一段**（挂后一段无效，实测 MAD 恒 0）。资源在 `%LOCALAPPDATA%/JianyingPro/User Data/Cache/effect/<resource_id>/<md5>/`，当前 453 条转场里已缓存 2 条（推近、水墨） |
| ⚠️ **受本地资源限制** | **转场包总量** | 元数据有 453 条，本地只缓存了 2 条；其余在剪映里先点用一次即可缓存，之后同样可用。`jy_build.py` 会先查缓存目录，缺资源直接报错并给出路径 |
| ✅ **已实测** | **滤镜（调色）**（`materials.effects` + `type:"filter"` + 一条 `filter` 轨） | 「电影增质」作用 4s：同一帧平均 RGB 从 (92.0, 91.6, 103.0) 变为 (99.7, 98.3, 126.8)，MAD **14.65**。素材字段照真实草稿抄（含 `path`、`value`、`apply_target_type`、`color_match_info`），轨段带 `enable_color_curves/enable_color_wheels` 等开关。资源在 `Cache/artistEffect/<effect_id>/<hash>` |
| ❌ **实测不通（仅指关键帧写法）** | **用 `common_keyframes` 调色** | `KFTypeBrightness=0.5`、`KFTypeSaturation=1.5`、`KFTypeContrast=1.5` 三条各测一遍，成片与基准帧 **MAD 全为 0.00**（平均 RGB 91.98/91.59/103.04 一字未变）。几何与不透明度、音量类关键帧同时期全部正常 ⇒ 这套属性在本引擎不驱动画面。**调色请走上一行的 `filter` 轨** |
| ❌ **实测不通** | **蒙版**（`materials.masks` 与 `materials.common_mask` 两种容器都试过） | 圆形蒙版挂到片段 `extra_material_refs`，成片四角仍是完整底色（应被遮黑）。`common_mask` 按 pyJianYingDraft 的 `export_common_json()` 全字段照抄（含 `category/category_id/text_config/expansion`）后**仍然无效** ⇒ 蒙版可能同样需要云端资源，或 11.6 换了别的容器 |
| ✅ **已实测** | **音频淡入淡出**（`materials.audio_fades` + 音频段 `extra_material_refs`） | 5s 恒定正弦 + 1.5s 淡入/淡出：t=0.1s 比对照低 **14.6 dB**，0.5s −4.8，0.9s −1.4，中段 0，4.5s −4.8，4.85s −11.9；对照 11 个采样点恒为 −26.9/−27.1。曲线非线性（近似正弦缓动），不是直线增益 |
| ✅ **已实测** | **静音视频段原声**（`segment.volume = 0`） | 同素材恒为 −27.1 dB，置 0 后全程 **−91.0 dB**。注意 `materials.videos[].has_audio=false` **不能静音**（该字段只是描述性元数据，实测仍 −27.0 dB） |
| ⚠️ **未验证** | 气泡/花字、滤镜、入场/出场动画 | 未做端到端验证；滤镜与动画大概率同转场一样需要云端资源 |
| ⛔ **做不到** | 操作**运行中**的剪映（改内存、点界面） | 无 UIA 控件树（CEF 渲染）；只能改磁盘文件再重载 |
| ⛔ **做不到** | 云端能力：AI 绘画/数字人/图文成片/智能字幕识别/模板广场 | 服务端 + 账号 + SVIP 积分，与本地文件无关 |
| ⛔ **做不到** | 命令行直接打开**指定**草稿 | 无 URL 协议；只能靠"刷成最近修改 + 启动剪映自动打开" |

> **一句话**：草稿文件层已基本全通（读、改、写、**从零建稿 + 拼接 + 变速 + 加素材 + 淡入淡出 + 叠化 + 真转场包 + 滤镜调色 + SRT 字幕**、导出、导出参数）；**转场与滤镜的唯一硬前提是资源已在本地 `Cache` 里**；**蒙版这条写法仍不通**；**云端 AI 功能与运行时状态完全不可及**。

> **纠正一条曾经的错误结论**：早前写的「未授权 VIP 素材导不干净成片」**是错的**。无头导出通道（`jy-draftc` + 11.6.0 DLL）不读登录态、不连素材鉴权，EffectSDK 的 `license` 全程为空串仍照常渲染。真实约束只有一条：**资源文件必须在本地 `Cache` 里**。VIP 与"能不能导出"无关；"资源下没下过"才决定一切。

### 🔑 新增素材与关键帧的十二个坑（别重犯）

1. **photo 素材进 `materials.videos`，不进 `materials.images`** —— 放错时引擎**零报错、零日志**，纯静默跳过。
2. **photo 的 `duration` 必须是哨兵值 `10800000000`**（3h），真实长度交给片段 `target_timerange`。
3. **`material_id` / `local_material_id` 不能省** —— 删掉它们图片就再也不出现。
4. **剪映没有 `image` 轨道类型** —— 图片挂 `type:"video"` 轨道；层序看片段 `render_index`（不是 `track_render_index`）。
5. **长文本不会自动换行** —— `materials.texts[].type` 设 `"text"` 时按单行渲染，超出画布**直接被裁**。需要自动换行就设 `type: "subtitle"`，或调小 `styles[].size` / 手动插入 `\n`。
6. **音频片段必须有 `source_timerange`** —— 音频的 `clip` 是 `null`（没有图像参数），但 `source_timerange` **不能一起置空**。置空后导出**全程数字静音**（`volumedetect` 测得 −91.0 dB，与"没有音轨"无法区分），且日志零告警。
7. **音量关键帧的时间基是「素材源时间」，不是片段内时间** —— 换算：`keyframe 时刻 = 输出时刻 × 速度 + trim 起点`。少扣 `trim` 起点就提前淡完（trim=[2,10] 直接把 7.1 写进去，实测 5.2s 起掉电平、6.25s 静音，画面照放）；带变速时还要乘速度。按公式换算后 trim/变速都成立，**不需要拆音轨**。
   ⚠️ 这条坑的**检测盲区**：`trim_start=0` 时偏移量为 0，缺陷完全隐身——用从头截取的合成素材永远测不出来，必须用「带 trim 的真实素材」做回归。
8. **叠加轨放图片必须走 photo 通道** —— `overlays` 里给 jpg，`ffmpeg -i` 只会报 `Duration 00:00:00.04`，素材 `duration` 变 40000µs、`type` 变 `video`，成片里**完全看不到**。图片要 `duration=10800000000` + `type:"photo"`（`jy_build.py` 已按后缀自动识别）。
9. **静音只认 `segment.volume`** —— `materials.videos[].has_audio` 是描述性字段，写 `false` 照旧出声（实测 −27.0 dB）。
10. **`common_keyframes` 的有效性按属性分类，别一概而论** —— 生效：`KFTypeScaleX/Y`、`KFTypeAlpha`、`KFTypeVolume`、位置类；不生效：`KFTypeBrightness/Contrast/Saturation`（三项实测 MAD 均为 0.00）。判断"关键帧机制坏没坏"要拿几何属性做对照，别用调色属性下结论。
11. **转场缺 `path` 会被静默丢弃** —— 只写 `resource_id`/`effect_id`/`is_overlap` 等字段（pyJianYingDraft 的写法）引擎一句话不说就跳过；补上 `path` 指向 `Cache/effect/<resource_id>/<md5>/` 才生效。另外**挂载点是接缝前那一段**，挂后一段同样静默无效。
12. **判断"资源有没有"要看用户数据目录，不是安装目录** —— 资源在 `%LOCALAPPDATA%/JianyingPro/User Data/Cache/{effect,artistEffect}/`（本机 286 个），安装目录里的 `Resources/CloudMaterial` 只有占位图标。看错目录会得出"本地无资源"的错结论，进而误判整类能力不可用。

> 已封装工具：
> - `scripts/jy.py` —— `doctor/info/set/clone/fixpath/verify/export`
> - `scripts/jy_add.py` —— 往**已有**草稿追加 `text` / `image` / `audio` / `transition`
> - `scripts/jy_build.py` —— 用**一份 JSON 清单从零建稿**（拼接 + 变速 + 图片 + 文本 + 音频（支持 `trim` 截取）+ 淡入淡出（自动换算时间基）+ 静音 + **叠加轨 `overlays`（画中画 / 叠化 / 海报，图片自动走 photo 通道）** + **`transitions`（真转场包，按名称查元数据）+ `filters`（滤镜调色）**），自带骨架 `references/draft_skeleton.json`
> - `scripts/jy_srt.py` —— 把 **SRT 字幕批量灌成字幕轨**（多行自动切 `type:"subtitle"`，样式整轨统一）
> - `references/transition_meta.py` —— 453 条真实转场 ID（含 VIP 标记）
>
> 典型流水线（三条命令）：
> ```
> py jy_build.py manifest.json  <草稿目录>          # 拼素材 / 变速 / 加图
> py jy_srt.py   sub.srt        <草稿目录>          # 灌字幕
> py jy.py export --jy-dir <11.6.0目录> --out out.mp4 <草稿目录>
> ```

**标准流程**：
- **从零生成**：脚本生成明文草稿 → 用户在剪映里精修 → 剪映自动加密。
- **接着改**：`jy.py info` 看清现状 → `jy.py set` 改字段 → 自动回加密 + 反向自证。

## ⭐ 现成工具：`scripts/jy.py`（推荐入口，别手搓）

```bash
SK=~/.workbuddy/skills/jianying-draft-scripting/scripts

python "$SK/jy.py" doctor                 # 自检：工具/DLL/草稿数
python "$SK/jy.py" info   "<草稿目录>"     # 解密后打印画布/轨数/素材失效项
python "$SK/jy.py" set    "<草稿目录>" --canvas 1080x1920 --ratio 9:16
python "$SK/jy.py" clone  "<源草稿>" "新草稿名" --canvas 1080x1920 --ratio 9:16
python "$SK/jy.py" fixpath "<草稿目录>" --to "<存在的素材路径>"
python "$SK/jy.py" verify "<草稿目录>"
```

它做了四件手工容易漏的事：**① 备份**（`.ai-bak`）**② 加密后反向自证**（重新解密比对期望值）**③ clone 时换 `draft_id`/`draft_name`/`draft_fold_path`**（不换会导致身份重复）**④ 去掉 `.locked`**（那是"正被打开"标记，拷过去会让剪映误判）。

`jy-draftc.exe` 已随技能放在 `scripts/bin/`（v11.6.0.14552，SHA256 已核对官方发布）。`--tool` / `--jy-dir` 一般不需要指定，会自动探测 `%LOCALAPPDATA%\JianyingPro\Apps\<版本>\videoeditor.dll`。

> **实测记录（两台版本）**
> - **6.0.1.11779（绿色解压版，Win11）**：明文草稿被正常加载（`.backup/*.load.bak` md5 与源文件一致、封面图比例匹配设定字段）；`jy-draftc` v0.1.1 跑通 `roundtrip_ok=true`。
> - **8.9.0.13361（装机版，2026-11 复测）**：`jy-draftc` **v11.6.0.14552** 可用。真实加密草稿 14396 B → 明文 10743 B；改画布 `1920×1014/original` → `1080×1920/9:16` 回加密 14388 B；**再解密与原明文 sha256 完全相同**（字节级无损）。`-c` 自检 crypto 段 `roundtrip OK, 229 -> 376 bytes, decrypt matches plaintext`。
>   ⚠️ 同一份 `-c` 自检的 **export 段会崩**（`0xC0000005 @ LoadLibrary`），因 11.6.0 的导出 profile 需要 `startup`/`pumpOnce`/`openTimelineEditor`/`draftTransaction`/`ProjectClient::init` 这 5 个 8.9.0 不存在的入口。**⇒ 用 8.9.0 的 DLL 只能读改草稿；要无头导出，把 `--jy-dir` 换成一个与工具同版本的引擎（见下方「已验证的完整无头导出流程」）。**
>   ✅ 界面侧已验收：剪映打开后「草稿参数 → 比例」显示 `9:16`，播放器为竖条（横版素材放进竖屏画布的正常表现）；`.backup/20261114193550_1b2bfd59…load.bak` 的 md5 与我写入的 `draft_content.json` **逐字节相同**。

## ⭐ 解密/回加密：jy-draftc（攻破"单向通道"的关键）

**仓库**：`wenshui330/jy-draftc`（MIT）。**原理**：不逆向算法、不猜密钥，而是**加载剪映自己的 `videoeditor.dll`，用 `GetProcAddress` 取 `EncryptUtils::decrypt` / `enable` / `encrypt`**，复用其原生加解密逻辑。

### 版本适配怎么判断（关键方法，比看 README 更可靠）

**不要相信"README 说支持哪个版本"**，要看 **ABI 是否一致**。两步，都在本机做：

1. 在剪映安装目录的 `videoeditor.dll` 里搜字符串 `jianying_draft_encrypt_v2` —— 有 = 用的是该加密方案（8.9.0 中存在）。
2. **比对导出表里的修饰名**：已验证入口是
   `?decrypt@EncryptUtils@lvve@@QEAA?AV?$basic_string@DU?$char_traits@D@std@@V?$allocator@D@2@@std@@AEBV34@0AEA_N@Z`
   用 PE 导出表解析（`struct` 读 DataDirectory[0]）确认本机 DLL 里**存在一字不差的同一修饰名**。
   → 签名一致 ⇒ ABI 一致 ⇒ 可直接用。

8.9.0 的实测结果：`EncryptUtils` 共 **14 个导出**，上述 decrypt（3 参，带 `AEA_N` 输出标志）、`?enable@EncryptUtils@lvve@@QEAAX_N@Z`、`?encrypt@...AEBV34@@Z` 均**逐字符命中**。另有 2 参重载 `?decrypt@...AEBV34@0@Z`（不带 ok 标志）—— **调用方必须用 3 参那个**，选错重载会读错栈。

**两个已实测的版本事实（重要，决定能用哪条路）**

| 事实 | 含义 |
|---|---|
| 8.9.0 远低于 v11 工具绑定的 11.6.0，但 **crypto 段照样通过** | 加解密是**按 ABI 兼容**，不是按版本号放行 |
| v11 二进制把 DLL 的**字节数 + sha256 硬编码**（期望 72547608 B / `8CFCBB61…`） | 只打印 `! fingerprint mismatch` **警告，不阻断** crypto；但 export 段会崩 |
| export profile 依赖 5 个新入口 | `-ex` 只能在**与工具同版本**的剪映上用；跨版本必崩 |

⇒ **拿新版老工具别慌**：先跑 `-c`，只看 `[1/3] crypto` 是否 `roundtrip OK`。过了就能读写草稿。

### 为什么「导出崩」不是补几个入口就能修好（重要，省下白做的功夫）

自检报 `missing: startup, pumpOnce, openTimelineEditor, draftTransaction, ProjectClient::init`，看起来像"改名了，替换一下就行"。**逐个在 8.9.0 的 25,034 个导出里查过，不是：**

| 缺失入口 | 8.9.0 实况 |
|---|---|
| `ProjectClient::init` | ⛔ **0 个** —— 整个 `ProjectClient` 类不存在 |
| `pumpOnce` | ⛔ **0 个** |
| `openTimelineEditor` | ⛔ 0 个（只有 `VeWrapper` 的 timeline 监听函数） |
| `draftTransaction` | ⚠️ 有，但签名不同（`?draftTransaction@Server@lyra@@…J…` / `@Session@lyra`） |
| `startup` | ⚠️ 有 `?startup@Server@lyra@@QEAAXPEBUVEGlobalConfig@lvve@@@Z`，签名与 11.6.0 要的不一致 |

`ProjectClient`、`pumpOnce` 是**类/函数被整体删除**，说明 11.6.0 的导出流水线换了**一代引擎 API**（`Lyra Server → Session → ProjectClient → draftInit → restoreDraft → ExportService`）。硬改等于重写整条链路，属逆向工程量级的大项目，且无成功保证。

> 也确认过**没有绕过 DLL 的通道**：`Apps\<ver>\JianyingPro.exe` 只有 433 KB（壳），全文件仅 `--process-type` / `--type` 两个开关，`-export`/`--export`/`headless` 命中数全为 0；`HKCR` 下无 `jianying://` 类 URL 协议。

**✅ 可行解：让版本配对。** 工具严格按剪映版本发布，配对上导出即可用。
- `winget show --id ByteDance.JianyingPro --exact --version <ver>` 能拿到官方 CDN 直链 + SHA256。实测速度：`winget download` 单线程 ≈0.25 MB/s；直连 curl ≈0.5 MB/s；**8 线程分段 ≈1.6–2 MB/s**（881 MB 约 10 分钟）。分段并行可用任意多线程下载器完成（实测 8 线程最快）。
- 剪映多版本**共存**于 `%LOCALAPPDATA%\JianyingPro\Apps\<版本号>\`；`--jy-dir` 指哪个就用哪个引擎，**不动用户当前版本**（前提：只解包，不改 `Configure.ini`）。
- `jy.py export` 会先比对 `-v` 打印的 `expected: N bytes` 与目标 DLL 实际大小，不一致就中止（`-f` 才继续）—— 因为这个不一致**必然**导致 export 段崩。

### ✅ 已验证的完整无头导出流程（8.9.0 改稿 → 11.6.0 引擎出片）

本机实测（2026-11-14）走通的完整链条，可照抄：

```bash
# 1) 取配对版本的官方安装包（只下载不安装）
winget show --id ByteDance.JianyingPro --exact --version 11.6.0.14552   # 拿 CDN 直链 + SHA256
python pdl.py "<直链>" "<保存路径>.exe" 8                                # 8 线程分段，881MB 约 7 分钟

# 2) 安装包是「PE 外壳 + 内嵌 7z」，7z 可直接解包，不必安装、不动现有版本
7z l  Jianying_11_6_0_14552.exe | grep videoeditor.dll
7z x  Jianying_11_6_0_14552.exe -o"D:\jy116" -y

# 3) 校验：必须同时满足字节数与 sha256，两条都对才算真配对
#    videoeditor.dll = 72,547,608 B / 8CFCBB61…  ← 与 jy-draftc -v 打印的 expected 一致

# 4) 自检（关键门槛）
jy-draftc.exe -c --jy-dir "D:\jy116\JYPacket\11.6.0.14552"
#   期望：exports 16/16 entries resolvable + "=> export path matches this dll" + all passed

# 5) 导出
python jy.py export "<草稿目录>" --jy-dir "D:\jy116\JYPacket\11.6.0.14552" --out "<out>.mp4"
```

**实测结果**：草稿 `1080×1920 / 30fps / 5s` → MP4 `1080×1920 / h264 Main / 30fps / 5.02s / 2,659,827 B`，耗时 **11.6 秒**（软件渲染，日志有 `Cannot load nvcuda.dll` 属正常——本机 Iris Xe 无 N 卡，自动回落）。抽帧检查：**特效轨（金色飘落粒子）与贴纸轨（花朵）都渲染进去了**，不是只拼视频流。

**几个实测细节**
- 解包后整体 **3.11 GB / 5169 个文件**；磁盘要留够。
- 内嵌包路径固定为 `JYPacket\<版本号>\`，`videoeditor.dll` 直接位于该层。
- 导出日志极长（EffectSDK/AE_EFFECT 刷屏），`jy.py export` 只回显末尾 3000 字符。
- 草稿结构版本 `112.0.0` **无需先升级**就能被 11.6.0 引擎导出（引擎内部自行处理）。
- 导出用的是草稿副本即可，不必放进剪映草稿目录；**素材是绝对路径，所以副本也能正常取到素材**。
- 日志里出现 `Cannot load nvcuda.dll` 不影响结果。

### 用法（v11 版命令行；v0.1.1 的 `-d`/`-e` 已改名）

```powershell
.\jy-draftc.exe -c   --jy-dir "<含 videoeditor.dll 的版本目录>"   # 自检：exports/abi/crypto/draft io
.\jy-draftc.exe -dc  <草稿目录或文件> -o <输出> --jy-dir <dir> -f   # 解密（dir -> dir-plain）
.\jy-draftc.exe -ec  <plain.json>    -o <输出> --jy-dir <dir> -f   # 回加密
.\jy-draftc.exe -v                                                  # 打印它绑定的剪映版本+期望 sha256
```

- **`-f` 必须加**：输出已存在时工具返回 rc=11（`output exists, use -f`），很容易被误读成"加解密失败"。
- `--jy-dir` 可省（配 `.env` 的 `JY_INSTALL_DIR`，或命令行优先）；**`.env` 必须用文件写入工具写**，别用 `echo/printf`（反斜杠会被 shell 吃掉）。
- 退出码：0 成功 / 8 DLL / 9 入口 / 10 解析 / 11 加密 / 14 目录或版本 / 64 用法。
- 输入可以是**任意被加密的文件**（不限于 `draft_content.json`）：`draft_meta_info.json` 同样是加密的，`-dc` 一样能解。
- 加密含随机 IV ⇒ **回加密产物与原始文件长度接近但哈希必然不同**，别拿哈希判成败，用"再解密是否等价"判。

### 改已有加密草稿的标准流程（最常用）

1. **完全退出剪映**（`tasklist | grep -ci jianying` 必须为 0），否则写入会被覆写。
2. **备份**目标的 `draft_content.json`（另存为 `*.剪映加密原版`），可随时回退。
3. **解密**：`jy.py info` 或 `-dc draft_content.json -o plain.json -f`
4. **改明文**：只改目标字段，其余保持剪映原样（**单变量**，否则误判责任在自己）。
5. **回加密**：`-ec plain.json -o re_enc.json -f`
6. **写入**：把 `re_enc.json` 覆盖 `draft_content.json`；**同时把 `draft_content.json.bak` 与 `template-2.tmp` 也覆盖成同一份**（实测原草稿这两个文件与 `draft_content.json` 的 md5 完全一致，是同步副本；不同步则剪映崩溃恢复/另存模板时可能回退旧值）。
7. **反向自证（必做，几秒钟）**：对**已落盘的**那份文件再跑一次 `-dc`，确认解出来**正是你要写入的改动值**。`jy.py` 的 `set`/`clone` 已内置这步。

⚠️ **验证值必须落在用户能感知的维度上**：曾有版本把画布从 `1080×1920` 改成 `720×1280`，两值**同为 9:16，界面上完全看不出差别** —— 即使剪映读成功，用户也无法确认，实验等于白做。**选跨越可感知边界的值**（竖屏→横屏、有→无、1 条→3 条、短→长）。

### 8.9.0 解密出的结构（比 6.0.1 复杂，28 个顶层键）

- 顶层 **28 键**：在 6.0.1 的 14 键基础上多出 `cover / create_time / extra_info / fps / free_render_index_mode_on / group_container / keyframe_graph_list / mutable_config / name / relationships / render_index_track_mode_on / retouch_cover / source / static_cover_image_path / time_marks / update_time`。
- **`fps` 这次在顶层了（实测 30.0）**；`version: 360000`、`new_version: 112.0.0`。
- `materials` 有 **44 个键**（`videos/images/texts/audios/effects/stickers/canvases/masks/transitions/…`）。
- **画布的权威源只有 `draft_content.json` 的 `canvas_config`**（`{width,height,ratio,background}`）——`draft_meta_info.json` 里**没有**宽高字段，不存在双源不一致问题。实测值 `1920×1014 / ratio:"original"`。
- ⚠️ **`draft_content.json` 的 `id` ≠ `draft_meta_info.json` 的 `draft_id`**（前者如 `B2BC483F-…`，后者如 `44E493D5-…`）。**克隆草稿只需换 `draft_id` + `draft_name` + `draft_fold_path`**，不要动 `content.id`。
- ⚠️ **`draft_meta_info.json` 也是加密的**（直接 `json.load` 会报 `Extra data: line 1 column 3`）。`-dc` 能解任意加密文件，不限于 `draft_content.json`。
- 素材引用是**绝对路径**（如 `E:/Jianying_Pro/6.0.1.11779/Resources/oobe/example.mp4`），**换机/卸载旧版后必然死链**。`jy.py info` 会列出失效素材，`jy.py fixpath --to <现有文件>` 批量修正。

### ⚠️ 必踩的坑

1. **`.env` 用 shell 写会被吃掉反斜杠**：`printf 'JY_INSTALL_DIR=D:\\jianying\\...'` 里 `\6` 会被 shell 转义吃掉，变成 `...Jianying_Pro.0.1.11779`，程序报 `JY_INSTALL_DIR does not exist`。**用文件写入工具直接写 .env，别用 echo/printf。**
2. **`-f` 不加就被当成"加密失败"**：输出已存在时 rc=11，日志 `output exists, use -f to overwrite`。
3. **`.locked` 是"正被打开"标记**：克隆草稿时务必删掉，否则剪映可能判定该草稿正在被占用。
4. **克隆必须换 `draft_id`**：只拷目录会得到两个同 id 草稿，剪映的封面缓存/云同步会串。
5. **PowerShell 工具可能不回传 stdout**（本机实测恒为空）：把 exe 输出重定向到文件再读，或用 Bash。
6. **管道 `| head` 会 SIGPIPE 杀掉 Python 脚本**：脚本末尾的 `json.dump` 等收尾动作可能来不及执行，表现为"文件莫名没生成"。要么写文件，要么别截断输出。
7. **剪映自带的 `ffmpeg.exe` 没有 libx264**：`-c:v libx264` 直接报 `Unknown encoder`。可用的是 `h264_qsv`（Intel 核显）/ `h264_mf`（MediaFoundation）/ `h264_nvenc`（NVIDIA）；本机实测 `h264_qsv` 正常。造测试素材时按此降级链试。
8. **`jy.py export` 报的时长不准**：它打印的 "%s s"（如 `4.3 s`）与成片真实时长无关，**一律用 `ffmpeg -i` 的 `Duration` 为准**（同一文件实测打印 4.3 s / 实际 5.02 s）。

### 其他同类项目（按实用性排序）

| 项目 | 说明 | 评价 |
|---|---|---|
| `wenshui330/jy-draftc` | 借 DLL 解密/回加密、结构升降级、无头导出。发布线：`v0.1.0`/`v0.1.1`（旧，`-d/-e`）→ `v11.5.0`/`v11.6.0`（新，`-dc/-ec/-ex/-ug/-dg/-c`，版本号跟剪映走） | ⭐ **首选**，两个版本线均已实测 |
| `aoguai/pyJianYingDraft` | fork，内置加密 codec（同样走 videoeditor.dll），含模板读写 | 需 Windows 64 位 Python，声称验证 10.3.0–10.6.5 |
| `wzk2025/capcut-cli` | 零依赖 CLI，**只检测不解密**，写入护栏拒绝改 6.0+ 草稿 | 适合做"版本体检" |
| `HTWMedia/JyDraft` | 云端 HTTP 解密 + 云端渲染成片（需 API Key） | 便利但**草稿要上传第三方**，注意隐私 |
| `xjn9854262/JyDraft` | 本地 HTTP 代理，抓剪映上传草稿时的明文 | 需登录并触发上传 |

### 解密出的 6.0.1 结构特征（写代码要按这个来）

- 顶层只有 **14 个键**：`canvas_config / config / duration / id / is_minimal_draft / keyframes / last_modified_platform / materials / new_version / path / platform / tracks / uneven_animation_template_info / version`。
- `new_version: 142.0.0`、`version: 360000`、`is_minimal_draft: true`；`fps` **不在顶层**（由别处决定）。
- ⚠️ **`target_timerange` 可能只有 `duration` 而缺 `start`** —— 剪映对"从 0 开始"的片段会省略 `start`。**5.x 的 pyJianYingDraft 解析器要求 `start` 必须存在，缺了会静默跳过整条轨道**（表现为 `ScriptFile._load_template()` 加载成功但 `tracks` 长度为 0）。自己解析时要写 `.get('start', 0)` 容错。


## 环境前置（每次都先做这三步）

1. **定位程序与草稿目录**（两者可能不在同一个盘）：
   - 程序：绿色解压版根目录只有引导器（≈1.9 MB exe + `JianyingProPacket.xml` + `Configure.ini`），**真程序在 `<版本号>\` 子目录**。
   - 草稿：恒在 `%LOCALAPPDATA%\JianyingPro\User Data\Projects\com.lveditor.draft\`，与程序放哪个盘无关。
2. **必须完全退出剪映**：草稿目录有 `.locked` 标记，运行中剪映会把内存状态覆写回磁盘，你的写入会被冲掉。用 `tasklist | grep -ci jianying` 确认 0 进程。
3. **先备份**：`cp -r` 整个草稿目录 + 单独另存加密原版为 `*.加密原版`。校验文件数与大小一致再动手。

### 想免点击打开草稿来验证？利用"自动打开最近修改的草稿"

- 剪映启动会**自动打开最近修改的那个草稿**（实测 8.9.0）。⇒ 要给某个草稿做验收，**先让它成为最新修改的**（我们回加密落盘时天然就是），再启动剪映即可，不必在列表里点。
- **没有 URL 协议**：`HKEY_CLASSES_ROOT` 下查不到 `jianying://` / `lveditor://` / `capcut://`，`draft_meta_info.json` 里的 `draft_deeplink_url` 字段是给云端分享用的，**不能当命令行入口**。所以"命令行直接打开指定草稿"做不到。
- **启动路径（踩过，务必按这个来）**：可执行文件**不在** `%LOCALAPPDATA%\JianyingPro\` 根目录（那里只有 `Apps\` 和 `User Data\` 两个子目录，写 `JianyingPro.exe` 会 `WinError 2`）。真实位置二选一：
  - 引导器：`%LOCALAPPDATA%\JianyingPro\Apps\JianyingPro.exe`（读同目录 `Configure.ini` 决定启哪个版本）
  - 指定版本：`%LOCALAPPDATA%\JianyingPro\Apps\<ver>\JianyingPro.exe`
- **不要用 `cmd /c start`**：实测它只弹一个控制台、剪映没起来。用 Python 起更稳：
  ```python
  subprocess.Popen([exe], cwd=os.path.dirname(exe),
                   creationflags=0x00000008 | 0x00000200,  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
                   close_fds=True)
  ```
- **已知失败模式（本机复现）**：即使这样拉起、窗口出现 `剪映专业版`（`Qt622QWindowIcon`），进程也会在 30 秒左右自行退出，既不出 `.load.bak` 也不回存草稿。此时**不要把它当成"草稿有问题"**——是启动环境问题。要做 UI 侧验收，让用户手动双击启动最可靠。
- 窗口类是 **Qt**（`Qt622QWindowIcon` / 标题 `剪映专业版`），不是纯 CEF。截图/取窗口矩形可用 `EnumWindows`+`GetWindowRect`；内容区仍是 CEF 渲染，**不要指望 UI Automation 拿到控件树**。

## 安装新草稿（风险最低的操作）

**只拷文件夹，不需要改 `root_meta_info.json`** —— 剪映是自行扫描草稿目录来登记新草稿的（已实测验证：拷入后 `root_meta_info.json` 自动出现新条目）。

```
cp -r <暂存草稿目录> "%LOCALAPPDATA%/JianyingPro/User Data/Projects/com.lveditor.draft/"
```

**原则：先写到暂存区，确认无误再拷入。** 不要在草稿目录里直接生成。

## 生成草稿：用 pyJianYingDraft

```
git clone --depth 1 https://github.com/GuanYixuan/pyJianYingDraft.git
```
（**该库未上 PyPI**，`pip install pyJianYingDraft` 必然失败，只能源码装。）

关键接口：`DraftFolder(草稿根目录)` → `.create_draft(名字, 宽, 高, fps=)` → `script.add_track()` / `add_segment()` → `script.save()`。参考库内 `demo.py`。

### 打了两个补丁（本机已改，换机需重打）

1. **`__init__.py`**：把需要 `uiautomation` 的 `jianying_controller`（自动导出用）改为 `try/except ImportError` 可选导入，否则 import 就挂。
2. **依赖 shim**：见下节。

### schema 对齐（关键，否则可能被当"高版本草稿"处理）

用**目标版本剪映自己产生的空草稿模板**（草稿目录里的 `template.tmp` 是明文空模板）逐字段比对，只改差异项。实测 6.0.1：

| 字段 | 6.0.1 期望值 |
|---|---|
| `version` | 360000（与库天然一致） |
| `new_version` | `75.0.0`（库默认 110.0.0，需改写） |
| `color_space` | `-1`（库默认 0，需改写） |
| `canvas_config.ratio` | 显式写字面比例（如 `9:16`），不要留 `original` |

模板独有而库里没有的键，**不要臆测补**。

## 本机依赖困境的三条解法

沙箱/受限环境常见 **pip 无网络**（连 `six` 都报 `No matching distribution` 就是无源可用，别怀疑包名）。

1. **`git clone` GitHub 源码**（git 常通，pip 不通时优先试它）。
2. **给缺失模块写最小 shim**：先 `grep` 出第三方库到底读哪几个属性，只实现那几个。
3. **改第三方代码的可选导入**（`try/except ImportError`），别为不用的功能硬凑依赖。

### `pymediainfo` 等价探针（复用价值高）

`pyJianYingDraft` 用 `pymediainfo` 感知素材时长/分辨率。可**用剪映自带的 `ffmpeg.exe`** 写等价 shim：

- 命令：`ffmpeg -hide_banner -i <file>`，信息打到 **stderr 后报错退出**（解析 stderr，不要用返回码判断失败）。
- 正则取 `Duration: HH:MM:SS.ss`，**必须换算成毫秒**（库要毫秒）。
- 取 `(\d+)x(\d+)` 作宽高；⚠️ **别把顺序写反**（曾踩此坑，靠断言抓到）。
- **图片（png/jpg）要按扩展名分流进 `image_tracks`**，`video_tracks` 留空；否则库里判断素材类型会错。
- `MediaInfo.can_parse()` 返回 True，`FFMPEG` 指向剪映自带的 ffmpeg。

## 顺手记：剪映自带一份可用的 ffmpeg

**问"本机有没有 ffmpeg"不能只 `where ffmpeg`** —— 剪映程序目录里就有一份（实测 `6.0.1.11779\ffmpeg.exe`，187 编码器/490 解码器）。

- 判定可用性必须**实跑一条真编码 + 解码回读校验帧数**（`-version` 跑通 ≠ 能编码）。
- 典型缺口：❌ 无 `libx264`（软编）、❌ 无 `ffprobe`、❌ **无 `drawtext`/`subtitles`/`ass`（不能烧字幕/叠文字）**、❌ 无 `libmp3lame`、❌ 无 `eq`。
- 常用滤镜在：`scale/overlay/concat/xfade/fade/rotate/crop/trim/setpts/atempo/volume/amix/drawbox`。
- 编码器选型：N卡 `h264_nvenc` / Intel 核显 `h264_qsv` / AMD `h264_amf` / 无独显 `h264_mf`。
- ⚠️ `--enable-shared` 构建 → **依赖同目录 5 个 `av*.dll`**，单拷 exe 起不来。

## 验证"剪映到底读没读我写的草稿"（最硬的取证手法）

**不要采信用户口述"正常"，直接读磁盘。** 剪映的 `.backup\` 目录是金矿：

| 文件名模式 | 含义 |
|---|---|
| `<时间戳>_<md5>.load.bak` | **加载**草稿时的快照，内容 = 当时读到的文件 |
| `<时间戳>_<md5>.save.bak` | **保存**时的快照 |
| `draft_content.json.bak` | 关闭/保存前的备份 |

**判据**：`.load.bak` 的 **md5 与我写入的文件 md5 完全相同** ⇒ 铁证，剪映加载的正是我写的明文。
（注意：文件名里的 md5 段就是该备份内容的 md5，可直接当校验值用。）

再加一条独立证据做强交叉：`draft_cover.jpg` 的像素比例应等于设定画布比例（如 405×720 = 1080×1920 的 3/8 缩略 = 9:16）。

**单变量设计**：验证兼容性时，内容用剪映自己的空模板，**只改 1–2 个字段**，否则"是我 JSON 写错"会造成误判。

## 常见陷阱清单

- `template.tmp` 是**明文但为空模板**（tracks=0）——只看它会误判"草稿没加密"。判定加密要拿待查文件与 `template-2.tmp` 比字节。
- 草稿目录里的素材引用是**绝对路径**。素材放在临时目录（如工作区）里，日后清理会断链 → 应固化到稳定位置。
- 用户「拖了几下时间轴」这类操作会触发保存 → 文件变加密、大小变化，属正常，不代表被回滚。
- 剪映界面是 Chromium(CEF) 渲染，但**未开远程调试端口**，不能靠 DevTools 协议驱动。
- 267 个 DLL 不是 API：无文档、无稳定 ABI、无 COM 注册 → 属逆向范畴。判断某目录有无可用接口，正确做法是**找 exe 并实测接不接命令行参数**，而不是数 DLL 个数。
- **改草稿后，草稿列表的缩略图可能仍显示旧画面**（剪映有封面缓存）；判据要看**打开草稿后的预览区**，而不是列表缩略图。
- **设计验证实验前先自问"用户能看出差别吗"**：同比例、同数量的改动等于没改（本会话踩过：竖屏 1080×1920 → 720×1280 看不出差别）。选跨越可感知边界的值。
- ⚠️ **用户说"画面是竖屏/横屏"时，他说的很可能是"素材"而不是"画布"**：竖屏素材放进横屏画布后按"适应"缩放 → 左右留黑边、中间一条竖带，看起来仍"像竖屏"。**比例/分辨率/数量这类可精确读出的属性，必须读 UI 参数面板（剪映右侧「草稿参数 → 比例」）或磁盘 JSON/封面图，不能凭"看起来像"下结论。**

## ⭐ 关键帧镜头动效（"让照片动起来"，剪映内全自动）

**先认清边界**：剪映（6.0.1 已实测）**没有任何动作迁移 / 照片跳舞模型**——`Resources/models/` 清单里只有 `avatar3d`/`avatar_drive`（数字人）、`skeleton_model`、`humanparsing`、`matting`、`mangamodel` 等。数字人是**云端付费 VAS**（`Resources/digital_human_purchase/template.js` 内嵌购买页 UI：`info__price--value`/`pay_code`/`locked-mask`，需 SVIP + 积分），且它是"**文本/音频驱动口播**"，**不是照搬参考视频的动作**。
⇒ 剪映内能做的"照片动起来"只有**镜头运动**（肯·伯恩斯式推拉/平移）。**这与真·动作迁移是两件事，交付前必须向用户讲清。**

### API（pyJianYingDraft）

`VisualSegment.add_keyframe(KeyframeProperty, time_offset_us, value)`（`segment.py:253`）

可用属性：`position_x/y`（**单位 = 半个画布宽/高**）、`rotation`（角度）、`scale_x/scale_y/uniform_scale`（1.0 为不缩放）、`alpha`、`saturation`、`contrast`、`brightness`、`volume`。

⚠️ **坑**：`uniform_scale` 会被内部**改写成 `scale_x`**（`segment.py:269`）。要等比例缩放，**必须同时加 `scale_x` 与 `scale_y` 两条关键帧**，否则只有 X 轴缩放。

### 最小可用配方

```python
from pyJianYingDraft import KeyframeProperty
d_us = 3_500_000                              # 片段时长(微秒)
seg = draft.VideoSegment(PHOTO, trange_seconds(0, duration=3.5))
for prop, v0, v1 in ((KeyframeProperty.scale_x, 1.00, 1.22),
                     (KeyframeProperty.scale_y, 1.00, 1.22)):
    seg.add_keyframe(prop, 0, v0)
    seg.add_keyframe(prop, d_us, v1)
seg.add_background_filling("blur")             # 竖屏留白用模糊背景填充
seg.add_transition(draft.TransitionType.叠化)
```

已验证的三段镜头语言：推近 `1.00→1.22` + 上移 → 拉远 `1.22→1.02` + 左移 → 推近 `1.02→1.18` + 右移；叠化转场 0.6s；BGM 音量 55%。参考脚本 `_tools\gen_photo_motion.py`。

### 同效果的 ffmpeg 预览（不必先装草稿，让用户先判方向）

剪映自带 ffmpeg 的 **`zoompan` 滤镜可用**：

```bash
# 先放大输入再 zoompan，否则放大后糊
ffmpeg -loop 1 -i photo.jpg -vf "scale=2160:-2,zoompan=z='1+0.22*on/104':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=105:s=1080x1920:fps=30" -frames:v 105 ...
# 多段用 xfade 串接：offset = 前段时长 − 转场时长
```

⚠️ **坑**：`-shortest` 会被较短的音轨截断整段视频（8s BGM 把 9.3s 视频截成 8.17s）→ 音频侧加 **`apad`** 补静音。参考脚本 `_tools\render_photomotion.sh`。
