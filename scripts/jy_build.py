# -*- coding: utf-8 -*-
"""jy_build.py —— 用一份 JSON 清单「从零」生成剪映草稿，再交给 jy.py export 出片。

不克隆任何现有草稿：骨架来自 references/draft_skeleton.json（28 个顶层键 / 45 个素材表，空表）。

清单格式（时间单位：秒）：
{
  "canvas": "1080x1920",
  "fps": 30,
  "clips": [                                  # 顺序拼接成主视频轨
    {"path": "a.mp4"},
    {"path": "b.mp4", "speed": 2.0},           # 2 倍速：2s 素材压成 1s
    {"path": "c.mp4", "speed": 0.5, "trim": [0.5, 1.5],
     "fade_in": 0.5, "fade_out": 0.5}          # 淡化自带原声（音量关键帧，时间基=源时间，trim/变速都自动换算）
  ],
  "transitions": [{"name": "推近", "at": 0, "dur": 1.0}],
                                               # 真转场包：name 取自 references/transition_meta.py，
                                               # at = 挂在哪一段末尾（该段与下一段的接缝），资源须已缓存
  "filters": [{"name": "电影增质", "effect_id": "7430733313419005238", "value": 1.0}],
                                               # 滤镜（调色）：走 materials.effects + filter 轨，资源须已缓存
  "images": [{"path": "x.png", "start": 1.0, "dur": 2.0, "scale": 0.4, "x": 0, "y": 0}],
  "overlays": [{"path": "b.mp4", "start": 1.5, "dur": 2.0,     # 叠加视频轨（画中画 / 叠化）
                "alpha_in": 0.5, "alpha_out": 0.5,             # 不透明度包络（秒）
                "scale": 0.5, "x": 0.3, "y": -0.3}],           # 画中画：缩小 + 偏移（x 正为右，y 负为下）
  "texts":  [{"content": "标题", "start": 0.3, "dur": 4.0, "size": 10, "y": -0.3}],
  "audio":  [{"path": "x.wav", "start": 0.0, "dur": 3.0, "volume": 0.5,
              "fade_in": 1.0, "fade_out": 1.0}]   # 淡入/淡出秒数，可省略
}

用法:
  py jy_build.py <清单.json> <目标草稿目录>
然后:
  py jy.py export --jy-dir <与工具同版本的剪映目录> --out out.mp4 <目标草稿目录>
"""
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import jy  # noqa: E402

SKELETON = HERE.parent / 'references' / 'draft_skeleton.json'
MS = 1000

TEXT_RI, IMG_RI, AUD_RI = 15000, 0, 0

CACHE_EFFECT = Path(os.environ.get('LOCALAPPDATA', '')) / 'JianyingPro/User Data/Cache/effect'
CACHE_FILTER = Path(os.environ.get('LOCALAPPDATA', '')) / 'JianyingPro/User Data/Cache/artistEffect'


def transition_meta(name):
    """从 references/transition_meta.py 取一条转场的真值：effect_id / resource_id / md5 / 默认时长 / 是否重叠。"""
    src = (HERE.parent / 'references' / 'transition_meta.py').read_text(encoding='utf-8')
    pat = (r'TransitionMeta\("' + re.escape(name) + r'",\s*(?:True|False),\s*'
           r'"(\d+)",\s*"(\d+)",\s*"([0-9a-f]+)",\s*([\d.]+),\s*(True|False)\)')
    m = re.search(pat, src)
    if not m:
        raise SystemExit(f'转场名「{name}」不在 transition_meta 里（共 453 条，需与剪映面板名称一致）')
    eid, rid, md5, dur, ov = m.groups()
    return eid, rid, md5, float(dur), ov == 'True'


def effect_cache_dir(resource_id, md5):
    return CACHE_EFFECT / resource_id / md5



def nid():
    return str(uuid.uuid4()).upper()


def kf_mat(prop, pairs):
    """构造一条关键帧列表。pairs 为 [(相对片段起点的微秒, 值)]。"""
    return {
        'id': nid(),
        'keyframe_list': [{
            'curveType': 'Line', 'graphID': '',
            'left_control': {'x': 0.0, 'y': 0.0}, 'right_control': {'x': 0.0, 'y': 0.0},
            'id': nid(), 'time_offset': int(t), 'values': [float(v)],
        } for t, v in pairs],
        'material_id': '',
        'property_type': prop,
    }


def probe_duration(path):
    """用 ffmpeg 读时长（剪映自带 ffmpeg 没有 ffprobe，但 -i 的 stderr 里有 Duration）。"""
    import re
    import subprocess
    ff = None
    for cand in [HERE / 'bin' / 'ffmpeg.exe']:
        if cand.is_file():
            ff = str(cand)
    if ff is None:
        ff = jy.find_jy_dir() and str(Path(jy.find_jy_dir()) / 'ffmpeg.exe')
    if not ff or not Path(ff).is_file():
        raise SystemExit('找不到 ffmpeg.exe，无法读取素材时长')
    r = subprocess.run([ff, '-hide_banner', '-i', str(path)],
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    m = re.search(r'Duration:\s*(\d+):(\d+):(\d+\.\d+)', r.stderr or '')
    if not m:
        raise SystemExit(f'读不到时长: {path}')
    h, mi, s = m.groups()
    return int(round((int(h) * 3600 + int(mi) * 60 + float(s)) * MS * MS))


def probe_size(path):
    import re
    import subprocess
    ff = str(Path(jy.find_jy_dir()) / 'ffmpeg.exe')
    r = subprocess.run([ff, '-hide_banner', '-i', str(path)],
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    m = re.search(r'Video:.*?(\d{2,5})x(\d{2,5})', r.stderr or '')
    return (int(m.group(1)), int(m.group(2))) if m else (1080, 1920)


def probe_has_audio(path):
    """素材自带音轨则为 True。剪映官方草稿在 videos[] 里会写 has_audio 字段。"""
    import subprocess
    ff = str(Path(jy.find_jy_dir()) / 'ffmpeg.exe')
    r = subprocess.run([ff, '-hide_banner', '-i', str(path)],
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    return bool(__import__('re').search(r'Stream #\S+.*?:\s*Audio:', r.stderr or ''))


def speed_mat(v=1.0):
    sid = nid()
    return sid, {'curve_speed': None, 'id': sid, 'mode': 0, 'speed': v, 'type': 'speed'}


def base_seg(mid, start, dur, render_index, track_ri, *, clip=True, source=None, has_source=None):
    """has_source: 是否写 source_timerange。音频虽然 clip=False，但**必须有** source_timerange，
    否则引擎当它没有素材区间 → 整条音频静音（实测 −91 dB）。"""
    if has_source is None:
        has_source = clip
    sid, spd = speed_mat()
    return {
        'caption_info': None, 'cartoon': False,
        'clip': {'alpha': 1.0, 'flip': {'horizontal': False, 'vertical': False},
                 'rotation': 0.0, 'scale': {'x': 1.0, 'y': 1.0},
                 'transform': {'x': 0.0, 'y': 0.0}} if clip else None,
        'common_keyframes': [], 'enable_adjust': True,
        'enable_color_correct_adjust': False, 'enable_color_curves': True,
        'enable_color_match_adjust': False, 'enable_color_wheels': True,
        'enable_lut': True, 'enable_smart_color_adjust': False,
        'extra_material_refs': [sid], 'group_id': '',
        'hdr_settings': {'intensity': 1.0, 'mode': 1, 'nits': 1000} if clip else None,
        'id': nid(), 'intensifies_audio': False, 'is_placeholder': False,
        'is_tone_modify': False, 'keyframe_refs': [], 'last_nonzero_volume': 1.0,
        'material_id': mid, 'render_index': render_index,
        'responsive_layout': {'enable': False, 'horizontal_pos_layout': 0,
                              'size_layout': 0, 'target_follow': '', 'vertical_pos_layout': 0},
        'reverse': False,
        'source_timerange': {'duration': source or dur, 'start': 0} if has_source else None,
        'speed': 1.0,
        'target_timerange': {'duration': dur, 'start': start},
        'template_id': '', 'template_scene': 'default', 'track_attribute': 0,
        'track_render_index': track_ri,
        'uniform_scale': {'on': True, 'value': 1.0} if clip else None,
        'visible': True, 'volume': 1.0,
    }, spd


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    man = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    dst = Path(sys.argv[2])
    if dst.exists() and any(dst.iterdir()):
        raise SystemExit(f'目标非空，拒绝覆盖: {dst}')

    base = json.loads(SKELETON.read_text(encoding='utf-8'))
    d = base
    w, h = [int(x) for x in str(man.get('canvas', '1080x1920')).lower().split('x')]
    fps = float(man.get('fps', 30))
    mats = d['materials']

    canvas_id = nid()
    mats['canvases'].append({'album_image': '', 'blur': 0.0, 'color': '', 'id': canvas_id,
                             'image': '', 'image_id': '', 'image_name': '',
                             'source_platform': 0, 'team_id': '', 'type': 'canvas_color'})
    scm_id = nid()
    mats['sound_channel_mappings'].append({'audio_channel_mapping': 0, 'id': scm_id,
                                           'is_config_open': False, 'type': 'none'})

    # ---------------- 主视频轨：顺序拼接 ----------------
    segs, cursor, log = [], 0, []
    for c in man.get('clips', []):
        p = c['path']
        src_dur = probe_duration(p)
        if c.get('trim'):
            t0, t1 = c['trim']
            src_dur = int((t1 - t0) * MS * MS)
            trim_start = int(t0 * MS * MS)
        else:
            trim_start = 0
        speed = float(c.get('speed', 1.0))
        target = int(src_dur / speed)
        mw, mh = probe_size(p)
        vid = nid()
        mats['videos'].append({
            'audio_fade': None, 'category_id': '', 'category_name': 'local',
            'check_flag': 63487,
            'crop': {'lower_left_x': 0.0, 'lower_left_y': 1.0, 'lower_right_x': 1.0,
                     'lower_right_y': 1.0, 'upper_left_x': 0.0, 'upper_left_y': 0.0,
                     'upper_right_x': 1.0, 'upper_right_y': 0.0},
            'crop_ratio': 'free', 'crop_scale': 1.0,
            'duration': src_dur, 'height': mh, 'id': vid,
            'has_audio': bool(c.get('has_audio', probe_has_audio(p))),
            'local_material_id': nid(), 'material_id': vid,
            'material_name': Path(p).name, 'media_path': '',
            'path': str(Path(p)).replace('\\', '/'),
            'source': 0, 'source_platform': 0, 'team_id': '', 'type': 'video', 'width': mw,
        })
        seg, spd = base_seg(vid, cursor, target, 0, 0, source=src_dur)
        seg['speed'] = speed
        seg['volume'] = float(c.get('volume', 1.0))
        seg['source_timerange'] = {'duration': src_dur, 'start': trim_start}
        seg['extra_material_refs'] = [spd['id'] if isinstance(spd, dict) else spd, canvas_id, scm_id]
        spd['speed'] = speed
        # 视频段自带原声的淡入淡出 → KFTypeVolume 音量关键帧。
        # ⚠ 关键帧的时间基是「素材源时间」，不是片段内时间：
        #    源时间 = 输出时间 × 速度 + trim 起点
        # 少扣 trim 起点就会提前淡完（实测 trim=[2,10]+淡出 0.9s：设定 7.1s 起淡，
        # 实际 5.2s 起掉电平、6.25s 静音）。变速同理要乘速度，否则同样错位。
        cfi = float(c.get('fade_in', 0) or 0)
        cfo = float(c.get('fade_out', 0) or 0)
        if cfi > 0 or cfo > 0:
            dur_s = target / MS / MS

            def _k(t_out):
                return int(t_out * speed * MS * MS) + trim_start

            pairs = []
            if cfi > 0:
                pairs += [(_k(0.0), 0.0), (_k(cfi), 1.0)]
            if cfo > 0:
                pairs += [(_k(max(0.0, dur_s - cfo)), 1.0), (_k(dur_s), 0.0)]
            pairs.sort()
            seg.setdefault('common_keyframes', []).append(kf_mat('KFTypeVolume', pairs))
        mats['speeds'].append(spd)
        segs.append(seg)
        log.append(f'{Path(p).name}  start={cursor/1e6:.2f}s dur={target/1e6:.2f}s speed={speed}')
        cursor += target

    total = cursor
    if not segs:
        raise SystemExit('清单里没有 clips，无法成片')

    d['tracks'].append({'attribute': 0, 'flag': 0, 'id': nid(), 'is_default_name': True,
                        'name': '', 'segments': segs, 'type': 'video'})

    # ---------------- 转场（真特效包；叠化替代法只是备用）----------------
    # 三条实测约束：① 素材表是 materials.transitions；② 必须带 path 指向本地缓存资源
    # （只写 pyJianYingDraft 那套字段，引擎会静默丢弃）；③ 挂在前一段（接缝前那段的 extra_material_refs）。
    for tr in man.get('transitions', []):
        name = tr['name']
        eid, rid, md5, ddur, ov = transition_meta(name)
        cdir = effect_cache_dir(rid, md5)
        if not cdir.is_dir():
            raise SystemExit(f'转场「{name}」的资源未下载：{cdir}\n'
                             f'  → 在剪映里对该转场用一次即可缓存，或换用已缓存的名称')
        tid = nid()
        dur_s = float(tr.get('dur', ddur))
        mats['transitions'].append({
            'category_id': '', 'category_name': '',
            'duration': int(dur_s * MS * MS), 'effect_id': eid, 'id': tid,
            'is_overlap': ov, 'name': name, 'path': str(cdir).replace('\\', '/'),
            'platform': 'all', 'request_id': '', 'resource_id': rid, 'type': 'transition',
        })
        idx = int(tr.get('at', len(segs) - 2))
        if not (0 <= idx < len(segs) - 1):
            raise SystemExit(f'转场「{name}」的 at={idx} 越界（需 0 ~ {len(segs) - 2}）')
        segs[idx].setdefault('extra_material_refs', []).append(tid)
        log.append(f'[转场] {name}  {dur_s:.2f}s  挂在第 {idx} 段末尾')

    # ---------------- 滤镜（调色）----------------
    # 素材表是 materials.effects 且 type="filter"，资源在 Cache/artistEffect/<effect_id>/<hash>；
    # 承载它的是一条 type="filter" 的轨。注意：调色不走 common_keyframes（KFTypeBrightness 实测无效）。
    for ft in man.get('filters', []):
        eid = str(ft['effect_id'])
        base = CACHE_FILTER / eid
        subs = [q for q in base.iterdir() if q.is_dir()] if base.is_dir() else []
        if not subs:
            raise SystemExit(f'滤镜 {eid} 的资源未下载：{base}\n'
                             f'  → 在剪映里用一次该滤镜即可缓存')
        fpath = Path(ft['path']) if ft.get('path') else subs[0]
        mid = nid()
        mats['effects'].append({
            'adjust_params': [], 'algorithm_artifact_path': '', 'apply_target_type': 0,
            'bloom_params': None, 'category_id': '', 'category_name': '',
            'color_match_info': {'source_feature_path': '', 'target_feature_path': '',
                                 'target_image_path': ''},
            'effect_id': eid, 'enable_skin_tone_correction': False, 'exclusion_group': [],
            'face_adjust_params': [], 'formula_id': '', 'id': mid, 'intensity_key': '',
            'multi_language_current': '', 'name': ft.get('name', ''), 'panel_id': '',
            'path': str(fpath).replace('\\', '/'), 'platform': 'all', 'request_id': '',
            'resource_id': eid, 'source_platform': 1, 'sub_type': 'none', 'time_range': None,
            'type': 'filter', 'value': float(ft.get('value', 1.0)), 'version': '',
        })
        st = int(float(ft.get('start', 0)) * MS * MS)
        du = int(float(ft.get('dur', total / 1e6)) * MS * MS)
        d['tracks'].append({
            'attribute': 0, 'flag': 0, 'id': nid(), 'is_default_name': True,
            'name': '滤镜', 'type': 'filter',
            'segments': [{
                'caption_info': None, 'cartoon': False, 'clip': None, 'common_keyframes': [],
                'enable_adjust': False, 'enable_color_correct_adjust': False,
                'enable_color_curves': True, 'enable_color_match_adjust': False,
                'enable_color_wheels': True, 'enable_lut': False,
                'enable_smart_color_adjust': False, 'extra_material_refs': [], 'group_id': '',
                'hdr_settings': None, 'id': nid(), 'intensifies_audio': False,
                'is_placeholder': False, 'is_tone_modify': False, 'keyframe_refs': [],
                'last_nonzero_volume': 1.0, 'material_id': mid, 'render_index': 10000,
                'responsive_layout': {'enable': False, 'horizontal_pos_layout': 0,
                                      'size_layout': 0, 'target_follow': '',
                                      'vertical_pos_layout': 0},
                'reverse': False, 'source_timerange': None, 'speed': 1.0,
                'target_timerange': {'duration': du, 'start': st}, 'template_id': '',
                'template_scene': 'default', 'track_attribute': 0, 'track_render_index': 2,
                'uniform_scale': None, 'visible': True, 'volume': 1.0,
            }],
        })
        log.append(f'[滤镜] {ft.get("name", eid)}  {du/1e6:.2f}s  强度 {ft.get("value", 1.0)}')


    # ---------------- 叠加视频轨（画中画 / 叠化转场）----------------
    # 每条 overlay 单独一条视频轨，层级由 track_render_index 决定（越大越靠上）。
    # alpha_in / alpha_out 用 KFTypeAlpha 做不透明度包络 —— 这是转场拿不到云端资源时的替代方案。
    tri = 1
    for ov in man.get('overlays', []):
        p = Path(ov['path'])
        if not p.is_file():
            raise SystemExit(f'叠加素材不存在: {p}')
        # 图片走 photo 通道：必须用哨兵 duration 10800000000，否则 jpg 会被取成 40ms 而渲染不出来
        is_img = p.suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp', '.bmp'}
        if is_img:
            try:
                from PIL import Image
                with Image.open(p) as f:
                    mw, mh = f.size
            except Exception:
                mw, mh = w, h
            speed = 1.0
            target = int(ov['dur'] * MS * MS) if ov.get('dur') else total
            src_dur = target                    # 片段区间时长
            trim_start = 0
            mat_dur = 10800000000               # 素材 duration 哨兵值
        else:
            full = probe_duration(p)            # 素材文件总长
            if ov.get('trim'):
                t0, t1 = ov['trim']
                src_len = int((t1 - t0) * MS * MS)
                trim_start = int(t0 * MS * MS)
            else:
                src_len = full
                trim_start = 0
            speed = float(ov.get('speed', 1.0))
            target = int(ov['dur'] * MS * MS) if ov.get('dur') else int(src_len / speed)
            src_dur = src_len                   # 片段消耗的源区间
            mat_dur = full                      # 素材自身时长
            mw, mh = probe_size(p)
        mid = nid()
        mats['videos'].append({
            'audio_fade': None, 'category_id': '', 'category_name': 'local',
            'check_flag': 63487,
            'crop': {'lower_left_x': 0.0, 'lower_left_y': 1.0, 'lower_right_x': 1.0,
                     'lower_right_y': 1.0, 'upper_left_x': 0.0, 'upper_left_y': 0.0,
                     'upper_right_x': 1.0, 'upper_right_y': 0.0},
            'crop_ratio': 'free', 'crop_scale': 1.0,
            'duration': mat_dur, 'height': mh, 'id': mid,
            'has_audio': False,
            'local_material_id': nid(), 'material_id': mid,
            'material_name': p.name, 'media_path': '',
            'path': str(p).replace('\\', '/'),
            'source': 0, 'source_platform': 0, 'team_id': '',
            'type': 'photo' if is_img else 'video', 'width': mw,
        })
        st = int(ov.get('start', 0) * MS * MS)
        seg, spd = base_seg(mid, st, target, 0, tri, source=src_dur)
        seg['speed'] = speed
        seg['source_timerange'] = {'duration': src_dur, 'start': trim_start}
        seg['extra_material_refs'] = [spd['id'], canvas_id, scm_id]
        spd['speed'] = speed
        seg['volume'] = float(ov.get('volume', 0.0))      # 叠加轨默认不出声
        sc = float(ov.get('scale', 1.0))
        seg['clip']['scale'] = {'x': sc, 'y': sc}
        seg['clip']['transform'] = {'x': float(ov.get('x', 0)), 'y': float(ov.get('y', 0))}
        if ov.get('alpha') is not None:
            seg['clip']['alpha'] = float(ov['alpha'])
        ai = float(ov.get('alpha_in', 0) or 0)
        ao = float(ov.get('alpha_out', 0) or 0)
        pairs = []
        if ai > 0:
            pairs += [(0, 0.0), (int(ai * MS * MS), 1.0)]
        if ao > 0:
            pairs += [(target - int(ao * MS * MS), 1.0), (target, 0.0)]
        if pairs:
            pairs.sort()
            seg['common_keyframes'] = [kf_mat('KFTypeAlpha', pairs)]
        mats['speeds'].append(spd)
        d['tracks'].append({'attribute': 0, 'flag': 0, 'id': nid(), 'is_default_name': True,
                            'name': '', 'segments': [seg], 'type': 'video'})
        log.append(f'[叠加{tri}] {p.name}  start={st/1e6:.2f}s dur={target/1e6:.2f}s '
                   f'alpha={ov.get("alpha")} in={ai} out={ao}')
        tri += 1

    # ---------------- 图片 ----------------
    for im in man.get('images', []):
        p = Path(im['path'])
        if not p.is_file():
            raise SystemExit(f'图片不存在: {p}')
        try:
            from PIL import Image
            with Image.open(p) as f:
                mw, mh = f.size
        except Exception:
            mw, mh = w, h
        mid = nid()
        mats['videos'].append({   # ⚠️ photo 必须进 videos
            'audio_fade': None, 'category_id': '', 'category_name': 'local', 'check_flag': 63487,
            'crop': {'lower_left_x': 0.0, 'lower_left_y': 1.0, 'lower_right_x': 1.0,
                     'lower_right_y': 1.0, 'upper_left_x': 0.0, 'upper_left_y': 0.0,
                     'upper_right_x': 1.0, 'upper_right_y': 0.0},
            'crop_ratio': 'free', 'crop_scale': 1.0, 'duration': 10800000000,
            'height': mh, 'id': mid, 'local_material_id': '', 'material_id': mid,
            'material_name': p.name, 'media_path': '',
            'path': str(p).replace('\\', '/'), 'type': 'photo', 'width': mw,
        })
        st = int(im.get('start', 0) * MS * MS)
        du = int(im.get('dur', total / 1e6) * MS * MS)
        seg, spd = base_seg(mid, st, du, IMG_RI, tri)
        sc = float(im.get('scale', 1.0))
        seg['clip']['scale'] = {'x': sc, 'y': sc}
        seg['clip']['transform'] = {'x': float(im.get('x', 0)), 'y': float(im.get('y', 0))}
        mats['speeds'].append(spd)
        d['tracks'].append({'attribute': 0, 'flag': 0, 'id': nid(), 'is_default_name': True,
                            'name': '', 'segments': [seg], 'type': 'video'})
        tri += 1

    # ---------------- 文本 ----------------
    for tx in man.get('texts', []):
        s = tx['content']
        payload = {'styles': [{
            'fill': {'alpha': 1.0, 'content': {'render_type': 'solid',
                                               'solid': {'alpha': 1.0, 'color': [1.0, 1.0, 1.0]}}},
            'range': [0, len(s)], 'size': float(tx.get('size', 10.0)), 'bold': True,
            'italic': False, 'underline': False,
            'strokes': [{'content': {'solid': {'alpha': 1.0, 'color': [0.0, 0.0, 0.0]}},
                         'width': 0.08}],
        }], 'text': s}
        mid = nid()
        mats['texts'].append({
            'id': mid, 'content': json.dumps(payload, ensure_ascii=False),
            'typesetting': 0, 'alignment': 1, 'letter_spacing': 0.0, 'line_spacing': 0.02,
            'line_feed': 1, 'line_max_width': 0.82, 'force_apply_line_max_width': False,
            'check_flag': 7 | 8, 'type': 'text', 'global_alpha': 1.0,
            'base_content': '', 'fixed_width': -1, 'fixed_height': -1,
            'text_to_audio_ids': [], 'speaker_id': '', 'speaker_name': '',
            'relevance_segment': [], 'original_size': [],
            'recognize_type': 0, 'sub_type': 0, 'source_from': '', 'add_type': 1,
        })
        st = int(tx.get('start', 0) * MS * MS)
        du = int(tx.get('dur', total / 1e6) * MS * MS)
        seg, spd = base_seg(mid, st, du, TEXT_RI, tri, clip=True, source=None)
        seg['source_timerange'] = None
        seg['clip']['transform'] = {'x': float(tx.get('x', 0)), 'y': float(tx.get('y', 0))}
        mats['speeds'].append(spd)
        d['tracks'].append({'attribute': 0, 'flag': 0, 'id': nid(), 'is_default_name': True,
                            'name': '', 'segments': [seg], 'type': 'text'})
        tri += 1

    # ---------------- 音频 ----------------
    for au in man.get('audio', []):
        p = Path(au['path'])
        if not p.is_file():
            raise SystemExit(f'音频不存在: {p}')
        mid = nid()
        du = int(au.get('dur', total / 1e6) * MS * MS)
        mats['audios'].append({
            'app_id': 0, 'category_id': '', 'category_name': 'local', 'check_flag': 3,
            'copyright_limit_type': 'none', 'duration': probe_duration(p), 'effect_id': '',
            'formula_id': '', 'id': mid, 'local_material_id': mid, 'music_id': mid,
            'name': p.name, 'path': str(p).replace('\\', '/'),
            'source_platform': 0, 'type': 'extract_music', 'wave_points': [],
        })
        seg, spd = base_seg(mid, int(au.get('start', 0) * MS * MS), du, AUD_RI, tri,
                            clip=False, has_source=True)
        # trim=[t0, t1] 秒：从源文件中间截取，不加则从头开始
        if au.get('trim'):
            t0, t1 = au['trim']
            dummy = int((float(t1) - float(t0)) * MS * MS)
            seg['target_timerange']['duration'] = dummy
            seg['source_timerange'] = {'duration': dummy, 'start': int(float(t0) * MS * MS)}
            du = dummy
        seg['volume'] = float(au.get('volume', 1.0))
        # 淡入淡出：纯增益包络，不依赖云端特效资源
        fi = float(au.get('fade_in', 0) or 0)
        fo = float(au.get('fade_out', 0) or 0)
        if fi > 0 or fo > 0:
            fid = nid()
            mats['audio_fades'].append({
                'id': fid,
                'fade_in_duration': int(fi * MS * MS),
                'fade_out_duration': int(fo * MS * MS),
                'fade_type': 0, 'type': 'audio_fade',
            })
            seg['extra_material_refs'].append(fid)
        mats['speeds'].append(spd)
        d['tracks'].append({'attribute': 0, 'flag': 0, 'id': nid(), 'is_default_name': True,
                            'name': '', 'segments': [seg], 'type': 'audio'})
        tri += 1

    # ---------------- 收尾 ----------------
    now = int(time.time())
    d['duration'] = total
    d['fps'] = fps
    d['canvas_config'] = {'background': None, 'height': h, 'ratio': man.get('ratio', '9:16'), 'width': w}
    d['id'] = nid()
    d['create_time'] = now
    d['update_time'] = now

    dst.mkdir(parents=True, exist_ok=True)
    cf = dst / 'draft_content.json'
    cf.write_text(json.dumps(d, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    (dst / 'draft_meta_info.json').write_text(json.dumps({
        'draft_id': nid(),
        'draft_name': dst.name,
        'draft_fold_path': str(dst).replace('\\', '/'),
        'draft_root_path': str(dst.parent).replace('\\', '/'),
        'draft_create_time': now,
        'draft_removable_storage_device': '',
        'draft_timeline_materials_size_': sum(Path(c['path']).stat().st_size
                                              for c in man.get('clips', []) if Path(c['path']).is_file()),
    }, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')

    # 自证：重新解析，核对段数与总时长
    v = json.loads(cf.read_text(encoding='utf-8'))
    assert v['duration'] == total
    assert len(v['tracks'][0]['segments']) == len(segs)

    print(f'✓ 从零建稿 {dst}')
    print(f'  画布 {w}x{h} @ {fps}fps  总时长 {total/1e6:.2f}s  轨道 {len(v["tracks"])} 条')
    for line in log:
        print('    ' + line)
    print('  自证通过')
    print(f'  出片: python jy.py export --jy-dir <同版本剪映目录> --out out.mp4 "{dst}"')


if __name__ == '__main__':
    main()
