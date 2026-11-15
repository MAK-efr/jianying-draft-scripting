# -*- coding: utf-8 -*-
"""
jy.py — 剪映专业版草稿程序化读写（AI 接入层）

原理: 不逆向加密算法, 借剪映自带 videoeditor.dll 的 EncryptUtils
      (由 jy-draftc 通过 GetProcAddress 调用) 做解密/回加密。
本脚本负责: 解密 -> 改 JSON -> 回加密 -> 落盘 -> 反向自证。

用法:
  python jy.py info    "<草稿目录>"
  python jy.py set     "<草稿目录>" [--canvas 1080x1920] [--ratio 9:16]
  python jy.py clone   "<源草稿目录>" "<新草稿名>" [--canvas WxH] [--ratio R]
  python jy.py fixpath "<草稿目录>" --to "<存在的素材路径>"
  python jy.py verify  "<草稿目录>"
  python jy.py doctor

依赖: jy-draftc.exe (https://github.com/wenshui330/jy-draftc) + 本机剪映安装目录
环境变量: JY_DRAFTC=exe路径  JY_DIR=含 videoeditor.dll 的版本目录
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

DRAFT_ROOT = Path(os.environ.get('LOCALAPPDATA', '')) / 'JianyingPro' / 'User Data' / 'Projects' / 'com.lveditor.draft'


# ---------------------------------------------------------------- tool / dir

def find_tool(explicit=None):
    cands = []
    if explicit:
        cands.append(Path(explicit))
    if os.environ.get('JY_DRAFTC'):
        cands.append(Path(os.environ['JY_DRAFTC']))
    here = Path(__file__).resolve().parent
    cands += [here / 'jy-draftc.exe', here / 'bin' / 'jy-draftc.exe', Path.cwd() / 'jy-draftc.exe']
    for c in cands:
        if c.is_file():
            return c
    raise SystemExit('找不到 jy-draftc.exe, 用 JY_DRAFTC 或 --tool 指定')


def find_jy_dir(explicit=None):
    cands = []
    if explicit:
        cands.append(Path(explicit))
    if os.environ.get('JY_DIR'):
        cands.append(Path(os.environ['JY_DIR']))
    apps = Path(os.environ.get('LOCALAPPDATA', '')) / 'JianyingPro' / 'Apps'
    if apps.is_dir():
        # 版本号目录里才有 videoeditor.dll, 根目录只有引导器
        for v in sorted(apps.iterdir(), key=lambda p: p.name, reverse=True):
            if (v / 'videoeditor.dll').is_file():
                cands.append(v)
    for c in cands:
        if c and (Path(c) / 'videoeditor.dll').is_file():
            return Path(c)
    raise SystemExit('找不到含 videoeditor.dll 的剪映目录, 用 JY_DIR 或 --jy-dir 指定')


def run_crypt(tool, jydir, mode, src, dst):
    """mode: -dc 解密 / -ec 加密。返回 (ok, stdout, stderr)。"""
    # -f: 允许覆盖已存在输出; 不加会因输出已存在而 rc=11
    cmd = [str(tool), mode, str(src), '-o', str(dst), '--jy-dir', str(jydir), '-f']
    p = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    ok = p.returncode == 0 and Path(dst).is_file()
    return ok, p.returncode, (p.stdout or '') + (p.stderr or '')


def decrypt_file(tool, jydir, src):
    """解密到临时文件并返回解析后的 JSON 对象。"""
    tmp = Path(tempfile.mkdtemp(prefix='jydec_')) / (Path(src).stem + '.plain.json')
    ok, rc, log = run_crypt(tool, jydir, '-dc', src, tmp)
    if not ok:
        raise SystemExit(f'解密失败 rc={rc}\n{log[:800]}')
    d = json.loads(tmp.read_text(encoding='utf-8'))
    shutil.rmtree(tmp.parent, ignore_errors=True)
    return d


def encrypt_to(tool, jydir, obj, dst):
    """把 JSON 对象加密后写到 dst。"""
    tmp = Path(tempfile.mkdtemp(prefix='jyenc_')) / 'plain.json'
    tmp.write_text(json.dumps(obj, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    ok, rc, log = run_crypt(tool, jydir, '-ec', tmp, dst)
    shutil.rmtree(tmp.parent, ignore_errors=True)
    if not ok:
        raise SystemExit(f'加密失败 rc={rc}\n{log[:800]}')
    return log


def is_encrypted(p):
    """明文 JSON 以 { 开头; 加密后是 base64 文本。"""
    try:
        head = Path(p).read_bytes()[:1]
        return head != b'{'
    except OSError:
        return False


def backup(p):
    b = Path(str(p) + '.ai-bak')
    if p.is_file() and not b.exists():
        shutil.copy2(p, b)
    return b


# ---------------------------------------------------------------- commands

def cmd_info(a):
    root = Path(a.draft)
    cf = root / 'draft_content.json' if root.is_dir() else root
    tool, jydir = find_tool(a.tool), find_jy_dir(a.jy_dir)
    enc = is_encrypted(cf)
    d = decrypt_file(tool, jydir, cf) if enc else json.loads(cf.read_text(encoding='utf-8'))
    cc = d.get('canvas_config') or {}
    print(f'draft      : {root}')
    print(f'encrypted  : {enc}')
    print(f'version    : {d.get("version")}  new_version={d.get("new_version")}')
    print(f'canvas     : {cc.get("width")}x{cc.get("height")}  ratio={cc.get("ratio")}')
    print(f'duration   : {(d.get("duration") or 0) / 1e6:.2f}s  fps={d.get("fps")}')
    mats = d.get('materials') or {}
    print(f'materials  : videos={len(mats.get("videos") or [])} images={len(mats.get("images") or [])} '
          f'texts={len(mats.get("texts") or [])} audios={len(mats.get("audios") or [])}')
    for t in d.get('tracks') or []:
        print(f'  track {t.get("type"):10s} segments={len(t.get("segments") or [])}')
    missing = []
    for key in ('videos', 'images', 'audios'):
        for m in mats.get(key) or []:
            p = m.get('path')
            if p and not Path(p).exists():
                missing.append(p)
    if missing:
        print(f'!! 素材失效 {len(missing)} 个:')
        for m in dict.fromkeys(missing):
            print(f'   {m}')
    return 0


def _apply(d, canvas, ratio):
    cc = d.setdefault('canvas_config', {})
    changed = []
    if canvas:
        w, h = canvas.lower().split('x')
        if str(cc.get('width')) != w or str(cc.get('height')) != h:
            changed.append(f'canvas {cc.get("width")}x{cc.get("height")} -> {w}x{h}')
        cc['width'], cc['height'] = int(w), int(h)
    if ratio:
        if cc.get('ratio') != ratio:
            changed.append(f'ratio {cc.get("ratio")} -> {ratio}')
        cc['ratio'] = ratio
    return changed


def cmd_set(a):
    root = Path(a.draft)
    cf = root / 'draft_content.json' if root.is_dir() else root
    tool, jydir = find_tool(a.tool), find_jy_dir(a.jy_dir)
    enc = is_encrypted(cf)
    d = decrypt_file(tool, jydir, cf) if enc else json.loads(cf.read_text(encoding='utf-8'))
    changed = _apply(d, a.canvas, a.ratio)
    if not changed:
        print('无需改动')
        return 0
    backup(cf)
    if enc:
        encrypt_to(tool, jydir, d, cf)
    else:
        cf.write_text(json.dumps(d, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print('已修改: ' + '; '.join(changed))
    return _selfcheck(tool, jydir, cf, expect_canvas=a.canvas)


def cmd_fixpath(a):
    root = Path(a.draft)
    tool, jydir = find_tool(a.tool), find_jy_dir(a.jy_dir)
    newp = Path(a.to)
    if not newp.is_file():
        raise SystemExit(f'目标素材不存在: {newp}')
    newposix = str(newp).replace('\\', '/')
    total = 0
    for name in ('draft_content.json', 'draft_meta_info.json'):
        f = root / name
        if not f.is_file():
            continue
        d = decrypt_file(tool, jydir, f) if is_encrypted(f) else json.loads(f.read_text(encoding='utf-8'))
        n = [0]

        def walk(o):
            if isinstance(o, dict):
                for k, v in list(o.items()):
                    if k in ('path', 'file_Path') and isinstance(v, str) and v and not Path(v).exists():
                        o[k] = newposix
                        n[0] += 1
                    else:
                        walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)

        walk(d)
        if n[0]:
            backup(f)
            encrypt_to(tool, jydir, d, f)
            print(f'{name}: 修正 {n[0]} 处失效路径 -> {newposix}')
            total += n[0]
    print('合计修正', total)
    return 0


def cmd_clone(a):
    src = Path(a.src)
    name = a.name
    dst = a.dst_dir or (DRAFT_ROOT / name)
    dst = Path(dst)
    if dst.exists():
        raise SystemExit(f'目标已存在, 拒绝覆盖: {dst}')
    if not (src / 'draft_content.json').is_file():
        raise SystemExit(f'源不是草稿目录: {src}')
    tool, jydir = find_tool(a.tool), find_jy_dir(a.jy_dir)
    shutil.copytree(src, dst)
    # .locked 是"正在被打开"的标记, 拷过去会让剪映误判
    for junk in ('.locked',):
        try:
            (dst / junk).unlink()
        except OSError:
            pass
    # 1) 正文: 画布
    cf = dst / 'draft_content.json'
    d = decrypt_file(tool, jydir, cf)
    changed = _apply(d, a.canvas, a.ratio)
    encrypt_to(tool, jydir, d, cf)
    # 2) 元信息: 换身份, 否则 draft_id 重复
    mf = dst / 'draft_meta_info.json'
    if mf.is_file():
        m = decrypt_file(tool, jydir, mf)
        m['draft_id'] = str(uuid.uuid4()).upper()
        m['draft_name'] = name
        m['draft_fold_path'] = str(dst).replace('\\', '/')
        encrypt_to(tool, jydir, m, mf)
    print(f'已克隆 -> {dst}')
    print('  身份: draft_id 已换新, draft_name/fold_path 已同步')
    print('  改动: ' + ('; '.join(changed) if changed else '(未改画布)'))
    return _selfcheck(tool, jydir, cf, expect_canvas=a.canvas)


def cmd_verify(a):
    root = Path(a.draft)
    cf = root / 'draft_content.json'
    tool, jydir = find_tool(a.tool), find_jy_dir(a.jy_dir)
    return _selfcheck(tool, jydir, cf, expect_canvas=None)


def cmd_export(a):
    """无头导出 MP4。注意：导出必须用【与工具同版本】的剪映 DLL。

    8.9.0 缺 ProjectClient/pumpOnce 等入口，导出段会崩；
    需用 --jy-dir 指向与 jy-draftc 版本匹配的剪映目录（如 11.6.0.14552）。
    """
    src = Path(a.draft)
    if not src.exists():
        raise SystemExit(f'草稿不存在: {src}')
    tool = find_tool(a.tool)
    jydir = find_jy_dir(a.jy_dir)

    ver = subprocess.run([str(tool), '-v'], capture_output=True, text=True,
                         encoding='utf-8', errors='replace').stdout or ''
    print('tool   :', ver.splitlines()[0] if ver else '?')
    print('jy dir :', jydir)
    # 预检：DLL 大小是否与工具期望一致（跨版本会崩，先提示）
    import re as _re
    m = _re.search(r'expected:\s*(\d+)\s*bytes', ver)
    dll = jydir / 'videoeditor.dll'
    if m and dll.is_file():
        want, got = int(m.group(1)), dll.stat().st_size
        if want != got:
            print(f'!! 版本不匹配: 工具期望 {want} B, 实际 {got} B')
            print('   crypto 仍可用，但 export 段大概率崩。请用与工具同版本的剪映目录。')
            if not a.force:
                raise SystemExit('已中止（确要继续加 --force）')

    cmd = [str(tool), '-ex', str(src), '--jy-dir', str(jydir)]
    if a.out:
        out = Path(a.out).resolve()
        cmd += ['-o', str(out)]
    for k, v in (('--size', a.size), ('--fps', a.fps), ('--bitrate', a.bitrate)):
        if v:
            cmd += [k, str(v)]
    if a.codec:
        cmd += ['--codec', a.codec]
    if a.force:
        cmd += ['-f']
    print('run    :', ' '.join(cmd))
    p = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    log = ((p.stdout or '') + (p.stderr or '')).strip()
    print(log[-3000:] if log else '(no output)')
    print('exit   :', p.returncode)
    return 0 if p.returncode == 0 else p.returncode


def _selfcheck(tool, jydir, cf, expect_canvas=None):
    """反向自证: 把落盘文件再解一次, 确认解开的是我要的值。"""
    d = decrypt_file(tool, jydir, cf)
    cc = d.get('canvas_config') or {}
    got = f'{cc.get("width")}x{cc.get("height")}'
    print(f'自证: 重新解密 OK, canvas={got} ratio={cc.get("ratio")} tracks={len(d.get("tracks") or [])}')
    if expect_canvas and got != expect_canvas.lower():
        print(f'!! 自证失败: 期望 {expect_canvas} 实际 {got}')
        return 1
    print('自证通过')
    return 0


def cmd_doctor(a):
    print('python  :', sys.version.split()[0])
    tool = find_tool(a.tool)
    print('tool    :', tool)
    p = subprocess.run([str(tool), '-v'], capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    print((p.stdout or '') + (p.stderr or ''))
    jydir = find_jy_dir(a.jy_dir)
    dll = jydir / 'videoeditor.dll'
    print('jy dir  :', jydir)
    print('dll     :', dll.stat().st_size, 'bytes')
    print('drafts  :', DRAFT_ROOT, '->', len(list(DRAFT_ROOT.glob('*/draft_content.json'))) if DRAFT_ROOT.is_dir() else 0, '个')
    return 0


def main():
    # 让 --tool / --jy-dir 既可放在子命令前、也可放在后（argparse 默认只认前者）
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('--tool', default=argparse.SUPPRESS, help='jy-draftc.exe 路径')
    common.add_argument('--jy-dir', default=argparse.SUPPRESS, help='含 videoeditor.dll 的剪映版本目录')

    ap = argparse.ArgumentParser(description='剪映草稿程序化读写', parents=[common])
    sub = ap.add_subparsers(dest='cmd', required=True)

    def P(name, **kw):
        return sub.add_parser(name, parents=[common], **kw)

    s = P('info'); s.add_argument('draft'); s.set_defaults(func=cmd_info)
    s = P('set'); s.add_argument('draft')
    s.add_argument('--canvas'); s.add_argument('--ratio'); s.set_defaults(func=cmd_set)
    s = P('clone'); s.add_argument('src'); s.add_argument('name')
    s.add_argument('--dst-dir'); s.add_argument('--canvas'); s.add_argument('--ratio')
    s.set_defaults(func=cmd_clone)
    s = P('fixpath'); s.add_argument('draft')
    s.add_argument('--to', required=True); s.set_defaults(func=cmd_fixpath)
    s = P('verify'); s.add_argument('draft'); s.set_defaults(func=cmd_verify)
    s = P('export')
    s.add_argument('draft')
    s.add_argument('--out')
    s.add_argument('--size', help='WxH，默认用草稿画布')
    s.add_argument('--fps')
    s.add_argument('--bitrate', help='12M / 8000K / 12000000')
    s.add_argument('--codec', help='h264 / hevc')
    s.add_argument('-f', '--force', action='store_true', help='版本不匹配也继续 / 覆盖输出')
    s.set_defaults(func=cmd_export)
    s = P('doctor'); s.set_defaults(func=cmd_doctor)

    a = ap.parse_args()
    # 子命令若未带 --tool/--jy-dir，SUPPRESS 会让属性不存在，这里补齐为 None
    for k in ('tool', 'jy_dir'):
        if not hasattr(a, k):
            setattr(a, k, None)
    return a.func(a)


if __name__ == '__main__':
    sys.exit(main())
