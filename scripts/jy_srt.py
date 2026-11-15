# -*- coding: utf-8 -*-
"""jy_srt.py —— 把 SRT 字幕批量灌进剪映草稿（一条字幕一个文本片段，可整轨样式统一）。

这是"真人做视频"最常用的入口：先把字幕时间轴在别处（剪辑/ASR/手工）做好，再一次性生成字幕轨。

用法:
  py jy_srt.py <字幕.srt> <草稿目录> [--size 6] [--y -0.78] [--track-name 字幕]

支持明文与加密草稿（自动判别）；写完回读自证。
"""
import argparse
import json
import sys
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import jy  # noqa: E402

US = 1000 * 1000          # 微秒/秒


def nid():
    return str(uuid.uuid4()).upper()


def parse_srt(path):
    """解析 SRT，返回 [(start_us, dur_us, text), ...]。容忍 BOM、CRLF、缺序号。"""
    raw = Path(path).read_text(encoding='utf-8-sig', errors='replace')
    lines = [ln.rstrip('\r') for ln in raw.split('\n')]
    cues, i, n = [], 0, len(lines)
    while i < n:
        ln = lines[i].strip()
        if not ln:
            i += 1
            continue
        if ln.isdigit():                     # 序号行
            i += 1
            if i >= n:
                break
            ln = lines[i].strip()
        if '-->' not in ln:
            i += 1
            continue
        a, b = [x.strip() for x in ln.split('-->')[:2]]
        start = _ts(a)
        end = _ts(b)
        i += 1
        body = []
        while i < n and lines[i].strip():
            body.append(lines[i].strip())
            i += 1
        if body:
            cues.append((start, max(end - start, 100 * 1000), '\n'.join(body)))
    return cues


def _ts(s):
    """00:00:01,500 或 00:00:01.500 → 微秒"""
    s = s.replace('.', ',')
    hms, _, ms = s.partition(',')
    parts = [int(x) for x in hms.split(':')]
    while len(parts) < 3:
        parts.insert(0, 0)
    h, m, sec = parts[-3:]
    return (h * 3600 + m * 60 + sec) * US + int((ms or '0').ljust(3, '0')[:3]) * 1000


def text_material(content, size, color=(1.0, 1.0, 1.0), stroke=True):
    payload = {
        'styles': [{
            'fill': {'alpha': 1.0,
                     'content': {'render_type': 'solid',
                                 'solid': {'alpha': 1.0, 'color': list(color)}}},
            'range': [0, len(content)],
            'size': size, 'bold': True, 'italic': False, 'underline': False,
            'strokes': ([{'content': {'solid': {'alpha': 1.0, 'color': [0.0, 0.0, 0.0]}},
                          'width': 0.08}] if stroke else []),
        }],
        'text': content,
    }
    return {
        'id': nid(), 'content': json.dumps(payload, ensure_ascii=False),
        'typesetting': 0, 'alignment': 1, 'letter_spacing': 0.0, 'line_spacing': 0.02,
        'line_feed': 1, 'line_max_width': 0.82, 'force_apply_line_max_width': False,
        'check_flag': 7 | (8 if stroke else 0),
        # 自动换行：多行字幕必须用 subtitle，否则单行渲染会被裁
        'type': 'subtitle' if '\n' in content else 'text',
        'global_alpha': 1.0,
        'base_content': '', 'fixed_width': -1, 'fixed_height': -1,
        'text_to_audio_ids': [], 'speaker_id': '', 'speaker_name': '',
        'relevance_segment': [], 'original_size': [],
        'recognize_type': 0, 'sub_type': 0, 'source_from': '', 'add_type': 1,
    }


def seg(mid, start, dur, tri, y):
    sid = nid()
    return {
        'caption_info': None, 'cartoon': False,
        'clip': {'alpha': 1.0, 'flip': {'horizontal': False, 'vertical': False},
                 'rotation': 0.0, 'scale': {'x': 1.0, 'y': 1.0},
                 'transform': {'x': 0.0, 'y': y}},
        'common_keyframes': [], 'enable_adjust': True,
        'enable_color_correct_adjust': False, 'enable_color_curves': True,
        'enable_color_match_adjust': False, 'enable_color_wheels': True,
        'enable_lut': True, 'enable_smart_color_adjust': False,
        'extra_material_refs': [sid], 'group_id': '', 'hdr_settings': None,
        'id': nid(), 'intensifies_audio': False, 'is_placeholder': False,
        'is_tone_modify': False, 'keyframe_refs': [], 'last_nonzero_volume': 1.0,
        'material_id': mid, 'render_index': 15000,
        'responsive_layout': {'enable': False, 'horizontal_pos_layout': 0, 'size_layout': 0,
                              'target_follow': '', 'vertical_pos_layout': 0},
        'reverse': False, 'source_timerange': None, 'speed': 1.0,
        'target_timerange': {'duration': dur, 'start': start},
        'template_id': '', 'template_scene': 'default', 'track_attribute': 0,
        'track_render_index': tri, 'uniform_scale': {'on': True, 'value': 1.0},
        'visible': True, 'volume': 1.0,
    }, {'curve_speed': None, 'id': sid, 'mode': 0, 'speed': 1.0, 'type': 'speed'}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('srt')
    ap.add_argument('draft')
    ap.add_argument('--size', type=float, default=6.0)
    ap.add_argument('--y', type=float, default=-0.78, help='垂直位置，负数偏下')
    ap.add_argument('--track-name', default='字幕')
    a = ap.parse_args()

    cues = parse_srt(a.srt)
    if not cues:
        raise SystemExit('SRT 没解析出任何字幕，检查格式')

    root = Path(a.draft)
    cf = root / 'draft_content.json'
    if not cf.is_file():
        raise SystemExit(f'不是草稿目录: {root}')

    if jy.is_encrypted(cf):
        tool, jydir = jy.find_tool(), jy.find_jy_dir()
        d = jy.decrypt_file(tool, jydir, cf)
    else:
        tool = jydir = None
        d = json.loads(cf.read_text(encoding='utf-8'))

    mats = d['materials']
    tri = max([t['segments'][0].get('track_render_index', 0)
               for t in d['tracks'] if t['segments']] or [0]) + 1

    segs = []
    for start, dur, content in cues:
        m = text_material(content, a.size)
        mats['texts'].append(m)
        s, spd = seg(m['id'], start, dur, tri, a.y)
        mats['speeds'].append(spd)
        segs.append(s)

    d['tracks'].append({'attribute': 0, 'flag': 0, 'id': nid(), 'is_default_name': True,
                        'name': a.track_name, 'segments': segs, 'type': 'text'})

    out = json.dumps(d, ensure_ascii=False, separators=(',', ':'))
    if jydir:
        jy.encrypt_to(tool, jydir, d, cf)
    else:
        cf.write_text(out, encoding='utf-8')

    # 回读自证
    v = (jy.decrypt_file(tool, jydir, cf) if jydir
         else json.loads(cf.read_text(encoding='utf-8')))
    tt = [t for t in v['tracks'] if t['type'] == 'text' and t['name'] == a.track_name]
    assert tt and len(tt[0]['segments']) == len(cues), '字幕段数不符'

    print(f'✓ SRT 已灌入 {root.name}')
    print(f'  字幕 {len(cues)} 条 → 轨道「{a.track_name}」 render_index=15000 y={a.y}')
    for start, dur, content in cues[:4]:
        print(f'    {start/1e6:6.2f}s +{dur/1e6:.2f}s  {content.splitlines()[0][:28]}')
    if len(cues) > 4:
        print(f'    … 另 {len(cues)-4} 条')
    print('自证通过')


if __name__ == '__main__':
    main()
