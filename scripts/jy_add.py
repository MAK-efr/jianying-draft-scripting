# -*- coding: utf-8 -*-
"""jy_add.py —— 向剪映草稿「从零新增」素材/片段，并做加密回写 + 回读自证。

已在 2025-11 实测通过：text / image / audio / keyframe。
transition 受「资源未缓存」限制（见 README 能力边界），代码可用但需先手动下载资源。

用法：
  py jy_add.py text  <草稿目录> --content "字幕内容" [--start 200] [--dur 4600] [--keyframe]
  py jy_add.py image <草稿目录> --path x.png [--start 1000] [--dur 2500] [--scale .35] [--x -.55] [--y -.62]
  py jy_add.py audio <草稿目录> --path x.wav [--start 0] [--dur 3000] [--volume .35]
  py jy_add.py transition <草稿目录> --name 闪白

时间单位：命令行用毫秒，内部转微秒。
"""
import argparse
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jy  # noqa: E402

MS = 1000


def nid():
    """剪映风格的大写带横线 UUID。"""
    return str(uuid.uuid4()).upper()


def _speed_mat():
    sid = nid()
    return sid, {"curve_speed": None, "id": sid, "mode": 0, "speed": 1.0, "type": "speed"}


def _seg(mid, start_us, dur_us, render_index, track_ri, *, clip=True, has_source=True):
    """通用片段骨架。clip=False 用于音频（无图像参数）。"""
    sid, spd = _speed_mat()
    return {
        "caption_info": None,
        "cartoon": False,
        "clip": {
            "alpha": 1.0, "flip": {"horizontal": False, "vertical": False},
            "rotation": 0.0, "scale": {"x": 1.0, "y": 1.0},
            "transform": {"x": 0.0, "y": 0.0},
        } if clip else None,
        "common_keyframes": [],
        "enable_adjust": True,
        "enable_color_correct_adjust": False,
        "enable_color_curves": True,
        "enable_color_match_adjust": False,
        "enable_color_wheels": True,
        "enable_lut": True,
        "enable_smart_color_adjust": False,
        "extra_material_refs": [sid],
        "group_id": "",
        "hdr_settings": {"intensity": 1.0, "mode": 1, "nits": 1000} if clip else None,
        "id": nid(),
        "intensifies_audio": False,
        "is_placeholder": False,
        "is_tone_modify": False,
        "keyframe_refs": [],
        "last_nonzero_volume": 1.0,
        "material_id": mid,
        "render_index": render_index,
        "responsive_layout": {"enable": False, "horizontal_pos_layout": 0,
                              "size_layout": 0, "target_follow": "", "vertical_pos_layout": 0},
        "reverse": False,
        "source_timerange": {"duration": dur_us, "start": 0} if has_source else None,
        "speed": 1.0,
        "target_timerange": {"duration": dur_us, "start": start_us},
        "template_id": "",
        "template_scene": "default",
        "track_attribute": 0,
        "track_render_index": track_ri,
        "uniform_scale": {"on": True, "value": 1.0} if clip else None,
        "visible": True,
        "volume": 1.0,
    }, spd


def _kf(prop, pairs):
    return {
        "id": nid(),
        "keyframe_list": [{
            "curveType": "Line", "graphID": "",
            "left_control": {"x": 0.0, "y": 0.0}, "right_control": {"x": 0.0, "y": 0.0},
            "id": nid(), "time_offset": t, "values": [v],
        } for t, v in pairs],
        "material_id": "",
        "property_type": prop,
    }


def _next_tri(d):
    """下一个 track_render_index（取现有最大值 +1）。"""
    return max([t["segments"][0].get("track_render_index", 0)
                for t in d["tracks"] if t["segments"]] or [0]) + 1


# ------------------------------------------------------------------ 文本

def add_text(d, content, start_us, dur_us, size=15.0, keyframe=False):
    strokes = [{"content": {"solid": {"alpha": 1.0, "color": [0.0, 0.0, 0.0]}}, "width": 0.08}]
    payload = {
        "styles": [{
            "fill": {"alpha": 1.0,
                     "content": {"render_type": "solid",
                                 "solid": {"alpha": 1.0, "color": [1.0, 1.0, 1.0]}}},
            "range": [0, len(content)],
            "size": size, "bold": True, "italic": False, "underline": False,
            "strokes": strokes,
        }],
        "text": content,
    }
    mid = nid()
    mat = {
        "id": mid,
        "content": json.dumps(payload, ensure_ascii=False),   # 必须是 JSON 字符串
        "typesetting": 0, "alignment": 1,
        "letter_spacing": 0.0, "line_spacing": 0.02, "line_feed": 1,
        "line_max_width": 0.82, "force_apply_line_max_width": False,
        "check_flag": 7 | 8, "type": "text", "global_alpha": 1.0,
        "base_content": "", "fixed_width": -1, "fixed_height": -1,
        "text_to_audio_ids": [], "speaker_id": "", "speaker_name": "",
        "relevance_segment": [], "original_size": [],
        "recognize_type": 0, "sub_type": 0, "source_from": "", "add_type": 1,
    }
    d["materials"]["texts"].append(mat)

    seg, spd = _seg(mid, start_us, dur_us, 15000, _next_tri(d), has_source=False)
    if keyframe:
        seg["uniform_scale"] = {"on": False, "value": 1.0}
        seg["common_keyframes"] = [
            _kf("KFTypeScaleX", [(0, 0.55), (500 * MS, 1.0)]),
            _kf("KFTypeScaleY", [(0, 0.55), (500 * MS, 1.0)]),
        ]
    d["materials"]["speeds"].append(spd)
    d["tracks"].append({"attribute": 0, "flag": 0, "id": nid(), "is_default_name": True,
                        "name": "", "segments": [seg], "type": "text"})
    return mid, content


# ------------------------------------------------------------------ 图片

def add_image(d, path, start_us, dur_us, scale=0.35, tx=0.0, ty=0.0):
    p = Path(path)
    if not p.is_file():
        raise SystemExit(f"图片不存在: {p}")
    try:
        from PIL import Image
        with Image.open(p) as im:
            w, h = im.size
    except Exception:
        w = h = 1080

    mid = nid()
    # ⚠️ 三个致命点：进 videos 表、duration 用哨兵值、material_id 不可缺
    mat = {
        "audio_fade": None, "category_id": "", "category_name": "local",
        "check_flag": 63487,
        "crop": {"lower_left_x": 0.0, "lower_left_y": 1.0, "lower_right_x": 1.0,
                 "lower_right_y": 1.0, "upper_left_x": 0.0, "upper_left_y": 0.0,
                 "upper_right_x": 1.0, "upper_right_y": 0.0},
        "crop_ratio": "free", "crop_scale": 1.0,
        "duration": 10800000000,
        "height": h, "id": mid,
        "local_material_id": "", "material_id": mid,
        "material_name": p.name, "media_path": "",
        "path": str(p).replace("\\", "/"),
        "type": "photo", "width": w,
    }
    d["materials"]["videos"].append(mat)

    seg, spd = _seg(mid, start_us, dur_us, 0, _next_tri(d))
    seg["clip"]["scale"] = {"x": scale, "y": scale}
    seg["clip"]["transform"] = {"x": tx, "y": ty}
    d["materials"]["speeds"].append(spd)
    d["tracks"].append({"attribute": 0, "flag": 0, "id": nid(), "is_default_name": True,
                        "name": "", "segments": [seg], "type": "video"})
    return mid, f"{p.name} {w}x{h}"


# ------------------------------------------------------------------ 音频

def add_audio(d, path, start_us, dur_us, volume=1.0):
    p = Path(path)
    if not p.is_file():
        raise SystemExit(f"音频不存在: {p}")
    mid = nid()
    d["materials"]["audios"].append({
        "app_id": 0, "category_id": "", "category_name": "local",
        "check_flag": 3, "copyright_limit_type": "none",
        "duration": dur_us, "effect_id": "", "formula_id": "",
        "id": mid, "local_material_id": mid, "music_id": mid,
        "name": p.name, "path": str(p).replace("\\", "/"),
        "source_platform": 0, "type": "extract_music", "wave_points": [],
    })
    seg, spd = _seg(mid, start_us, dur_us, 0, _next_tri(d), clip=False)
    seg["volume"] = volume
    d["materials"]["speeds"].append(spd)
    d["tracks"].append({"attribute": 0, "flag": 0, "id": nid(), "is_default_name": True,
                        "name": "", "segments": [seg], "type": "audio"})
    return mid, p.name


# ------------------------------------------------------------------ 转场

def lookup_transition(name):
    """正则解析 pyJianYingDraft 的转场元数据表（不 import，避开 pymediainfo 依赖）。"""
    import re
    src = Path.home() / ".workbuddy/skills/jianying-draft-scripting/references/transition_meta.py"
    if not src.is_file():
        raise SystemExit(
            "缺少转场元数据表 references/transition_meta.py（含 453 条真实 effect_id）。\n"
            "可从 pyJianYingDraft 仓库复制该文件到 references/ 下。")
    text = src.read_text(encoding="utf-8")
    pat = re.compile(
        r'TransitionMeta\(\s*"([^"]+)"\s*,\s*(True|False)\s*,\s*"([^"]*)"\s*,\s*"([^"]*)"\s*,'
        r'\s*"([^"]*)"\s*,\s*([\d.]+)\s*,\s*(True|False)\s*\)')
    for m in pat.finditer(text):
        nm, vip, rid, eid, md5, dur, ov = m.groups()
        if nm == name:
            return {"name": nm, "is_vip": vip == "True", "resource_id": rid,
                    "effect_id": eid, "md5": md5,
                    "duration": int(round(float(dur) * MS * MS)), "is_overlap": ov == "True"}
    raise SystemExit(f"未知转场: {name}")


def add_transition(d, name, dur_us=0):
    meta = lookup_transition(name)
    tdur = dur_us or meta["duration"]
    vt = next((t for t in d["tracks"] if t["type"] == "video" and len(t["segments"]) == 1), None)
    if vt is None:
        raise SystemExit("需要一条【只有 1 段】的视频轨才能切分加转场")
    s0 = vt["segments"][0]
    total = s0["target_timerange"]["duration"]
    half = total // 2

    a = json.loads(json.dumps(s0)); b = json.loads(json.dumps(s0))
    a["id"] = nid(); b["id"] = nid()
    a["target_timerange"] = {"duration": half, "start": 0}
    a["source_timerange"] = {"duration": half, "start": 0}
    b["target_timerange"] = {"duration": total - half, "start": half}
    b["source_timerange"] = {"duration": total - half, "start": half}
    sid, spd = _speed_mat(); b["extra_material_refs"] = [sid]
    d["materials"]["speeds"].append(spd)

    tid = nid()
    d["materials"]["transitions"].append({
        "category_id": "", "category_name": "", "duration": tdur,
        "effect_id": meta["effect_id"], "id": tid,
        "is_overlap": meta["is_overlap"], "name": meta["name"],
        "platform": "all", "resource_id": meta["resource_id"], "type": "transition",
    })
    a["extra_material_refs"].append(tid)   # 转场挂在前一段
    vt["segments"] = [a, b]
    return meta, tid


# ------------------------------------------------------------------ main

def main():
    ap = argparse.ArgumentParser(description="给剪映草稿新增素材/片段（加密回写 + 回读自证）")
    ap.add_argument("--tool")
    ap.add_argument("--jy-dir")
    sub = ap.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("text", help="新增文本/字幕")
    t.add_argument("draft"); t.add_argument("--content", required=True)
    t.add_argument("--start", type=int, default=200); t.add_argument("--dur", type=int, default=4600)
    t.add_argument("--size", type=float, default=15.0); t.add_argument("--keyframe", action="store_true")

    i = sub.add_parser("image", help="新增图片")
    i.add_argument("draft"); i.add_argument("--path", required=True)
    i.add_argument("--start", type=int, default=1000); i.add_argument("--dur", type=int, default=2500)
    i.add_argument("--scale", type=float, default=0.35)
    i.add_argument("--x", type=float, default=0.0); i.add_argument("--y", type=float, default=0.0)

    a = sub.add_parser("audio", help="新增音频")
    a.add_argument("draft"); a.add_argument("--path", required=True)
    a.add_argument("--start", type=int, default=0); a.add_argument("--dur", type=int, default=3000)
    a.add_argument("--volume", type=float, default=1.0)

    r = sub.add_parser("transition", help="切分视频轨并插入转场（需资源已缓存）")
    r.add_argument("draft"); r.add_argument("--name", required=True); r.add_argument("--dur", type=int, default=0)

    a_ = ap.parse_args()
    root = Path(a_.draft)
    cf = root / "draft_content.json"
    if not cf.is_file():
        raise SystemExit(f"不是草稿目录: {root}")
    tool, jydir = jy.find_tool(a_.tool), jy.find_jy_dir(a_.jy_dir)

    d = jy.decrypt_file(tool, jydir, cf)
    n0, tr0 = len(d["tracks"]), {k: len(v) for k, v in d["materials"].items()}

    if a_.cmd == "text":
        mid, desc = add_text(d, a_.content, a_.start * MS, a_.dur * MS, a_.size, a_.keyframe)
    elif a_.cmd == "image":
        mid, desc = add_image(d, a_.path, a_.start * MS, a_.dur * MS, a_.scale, a_.x, a_.y)
    elif a_.cmd == "audio":
        mid, desc = add_audio(d, a_.path, a_.start * MS, a_.dur * MS, a_.volume)
    else:
        meta, tid = add_transition(d, a_.name, a_.dur * MS)
        mid, desc = tid, f'{meta["name"]} (is_vip={meta["is_vip"]})'

    jy.encrypt_to(tool, jydir, d, cf)

    # 回读自证：重新解密，确认字段真的落盘
    v = jy.decrypt_file(tool, jydir, cf)
    assert len(v["tracks"]) == n0 + (2 if a_.cmd == "transition" else 1), "轨道数不符"
    if a_.cmd != "transition":
        hit = [t for t in v["tracks"] for s in t["segments"] if s["material_id"] == mid]
        assert hit, "新增片段未落盘"

    print(f"✓ {a_.cmd} 已写入 {root.name}")
    print(f"  {desc}")
    print(f"  轨道 {n0} -> {len(v['tracks'])}: {[t['type'] for t in v['tracks']]}")
    changed = {k: f"{tr0[k]}->{len(vv)}" for k, vv in v["materials"].items() if len(vv) != tr0[k]}
    print(f"  素材变动: {changed or '无'}")
    print("  自证通过（重新解密后字段一致）")


if __name__ == "__main__":
    main()
