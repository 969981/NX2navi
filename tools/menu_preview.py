"""Draw the in-game settings menu and the performance overlay without the game (tools/menu_preview.cpp).

    python tools/menu_preview.py [--out build/menu-preview] [--font FILE] [--size 1920x1080]

Builds tools/menu_preview.cpp with the menu's own row, shape, overlay and text code and Dear ImGui (host clang++, into
build/menu-preview), runs it for each scene and writes menu.png and overlay.png. No game files are read: the window
has its plain border in place of the game's ornamented frame, and the font given (default: DejaVu Sans, else the first
TrueType font found) stands in for the game's.
"""
import argparse
import os
import shutil
import struct
import subprocess
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RT = ROOT / 'runtime'
SOURCES = [ROOT / 'tools' / 'menu_preview.cpp', RT / 'ui' / 'option_rows.cpp', RT / 'ui' / 'menu_skin.cpp',
           RT / 'ui' / 'perf_panel.cpp', RT / 'ui_text.c'] + sorted((RT / 'third_party' / 'imgui').glob('imgui*.cpp'))
FONTS = ['/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 'C:/Windows/Fonts/segoeui.ttf', 'C:/Windows/Fonts/arial.ttf']


def png(path, w, h, rgba):
    """An 8-bit RGBA PNG of the raw pixels."""
    rows = b''.join(b'\0' + rgba[y * w * 4:(y + 1) * w * 4] for y in range(h))

    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    Path(path).write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0)) +
                           chunk(b'IDAT', zlib.compress(rows, 6)) + chunk(b'IEND', b''))


def build(out):
    cxx = shutil.which('clang++') or shutil.which('g++')
    if not cxx:
        sys.exit('needs clang++ or g++ on PATH')
    exe = out / ('menu_preview.exe' if os.name == 'nt' else 'menu_preview')
    objs = []
    for src in SOURCES:
        obj = out / (src.stem + '.o')
        if not obj.is_file() or obj.stat().st_mtime < max(src.stat().st_mtime, (RT / 'ui' / 'menu_skin.h').stat().st_mtime):
            lang = ['-x', 'c', '-std=gnu11'] if src.suffix == '.c' else ['-x', 'c++', '-std=gnu++17']
            cmd = [cxx, *lang, '-c', '-O2', '-w', '-I', str(RT), '-I', str(RT / 'third_party' / 'imgui'), str(src), '-o',
                   str(obj)]
            if subprocess.run(cmd).returncode:
                sys.exit(f'{src.name} did not compile')
        objs.append(str(obj))
    if subprocess.run([cxx, *objs, '-o', str(exe), '-lm']).returncode:
        sys.exit('the link failed')
    return exe


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--out', type=Path, default=ROOT / 'build' / 'menu-preview')
    ap.add_argument('--font', help='a TrueType font for the text')
    ap.add_argument('--size', default='1920x1080')
    a = ap.parse_args()
    font = a.font or next((f for f in FONTS if Path(f).is_file()), None)
    if not font:
        sys.exit('no font found: give one with --font')
    w, h = (int(x) for x in a.size.lower().split('x'))
    a.out.mkdir(parents=True, exist_ok=True)
    exe = build(a.out)
    for scene in ('menu', 'overlay'):
        raw = a.out / f'{scene}.rgba'
        if subprocess.run([str(exe), font, scene, str(w), str(h), str(raw)]).returncode:
            sys.exit(f'the {scene} scene failed')
        png(a.out / f'{scene}.png', w, h, raw.read_bytes())
        raw.unlink()
        print(a.out / f'{scene}.png')


if __name__ == '__main__':
    main()
