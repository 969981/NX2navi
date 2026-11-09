"""Find the offsets runtime/gfx_tweaks.c and the gfx_hook patch set need in a build of the game's main.

    python tools/find_gfx_offsets.py <exefs>/main [--expect]

<exefs>/main is a game folder's exefs/main (make_game.py stores the modules unpacked) or the dump's own, packed one
(then recomp/nso.py unpacks it, with lz4 or zbic installed). The script prints the #define block of gfx_tweaks.c and the
gfx_hook site line of recomp/patches-v<ver>.txt for that build, each value with how it was found, and marks what it
could not find. --expect compares the result with the 1.1.1 values (a self-check of the search rules on 1.1.1).

How each value is found (docs/game-graphics.md explains why these anchors hold):
  hook site         the graphics system's per-frame update: ldrb w8, [x0, #imm]; tbz w8, #1; pacibsp; then within
                    its first instructions fmov s0, #1.0; movi d1, #0; tst w1, #1 (score; the best match wins)
  named vtables     the game's reflection: slot 12 of a parameter class's vtable is a function returning its type name
                    ("game__gfx__ModelLodParam"); the foliage component's slot 27 returns its editor icon path
  VT_GFX            the vtable whose first slots point at the functions around the hook (its methods sit together)
  VT_SCENE_SHADOW   its constructor builds the floats 1.5, 15 and 120, 120 and stores the 120 pair at +0xb0: the
                    distance is the second of the pair
  G_FOLIAGE         a singleton: the vtable of its disposer sits right before the foliage component's vtable, and that
                    disposer's destructor clears the global (str xzr)
  G_CONSOLE         the constructor that calls nn::oe::GetOperationMode, GetPerformanceMode, GetCurrentFocusState and
                    GetCurrentGraphicsScale and stores itself in a global; the field is where the first result goes
The field offsets inside the objects are printed as 1.1.1's and checked where the code shows them (the hook reads the
graphics system's +0xb30 and +0xd50, and +0x150 of the holder); the rest are checked in play: the log lines
"gfx tweaks: ...: the game's value" must show the values docs/game-graphics.md lists.
"""
import argparse
import re
import struct
import sys
from pathlib import Path

EXPECT_111 = {
    'HOOK_SITE': 0x31d3200, 'G_FOLIAGE': 0x4e22540, 'G_CONSOLE': 0x4e97dd8, 'VT_GFX': 0x4b8bc00,
    'VT_FOLIAGE': 0x4b24800, 'VT_FOLIAGE_SCENE': 0x4b23228, 'VT_FOLIAGE_LOD': 0x4b235d0, 'VT_MODEL_LOD': 0x4b87a88,
    'VT_CHAR_SHADOW': 0x4b86828, 'VT_SCENE_SHADOW': 0x4b8a0a8, 'SCENE_SHADOW_DIST': 0xb4,
    'CONSOLE_OPERATION_MODE': 0x20,
}

# type name returned by slot <slot> of the vtable
NAMED = {
    'VT_FOLIAGE_SCENE': ('game__foliage__ResFoliageScene', 12),
    'VT_FOLIAGE_LOD': ('game__foliage__ResLodSetting', 12),
    'VT_MODEL_LOD': ('game__gfx__ModelLodParam', 12),
    'VT_CHAR_SHADOW': ('game__gfx__LocalDepthShadowParam', 12),
    'VT_FOLIAGE': ('Icon=%PROJECT_TOOL%\\Internal\\ORIcon\\foliage.png', 27),
}

DT_STRTAB, DT_SYMTAB, DT_JMPREL, DT_PLTRELSZ = 5, 6, 23, 2
RET, PACIBSP = 0xd65f03c0, 0xd503237f


class Image:
    """main's memory image (segments at their offsets) and its .text end."""

    def __init__(self, path):
        raw = Path(path).read_bytes()
        if raw[:4] != b'NSO0':
            sys.exit(f'{path}: not an NSO module')
        flags = struct.unpack_from('<I', raw, 0xC)[0]
        if flags & 7:   # packed: recomp/nso.py unpacks it (lz4, or zbic for Switch 2 modules)
            sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'recomp'))
            from nso import Nso
            n = Nso(path)
            self.img, self.text_end = bytes(n.image), n.text[0] + n.text[1]
        else:
            segs = [struct.unpack_from('<III', raw, 0x10 + i * 0x10) for i in range(3)]
            bss = struct.unpack_from('<I', raw, 0x3C)[0]
            img = bytearray((segs[2][1] + segs[2][2] + bss + 0xFFF) & ~0xFFF)
            for fo, mo, size in segs:
                img[mo:mo + size] = raw[fo:fo + size]
            self.img, self.text_end = bytes(img), segs[0][1] + segs[0][2]
        self.words = struct.unpack_from(f'<{self.text_end // 4}I', self.img, 0)
        self.plt = self._plt()

    def u32(self, a): return struct.unpack_from('<I', self.img, a)[0]
    def u64(self, a): return struct.unpack_from('<Q', self.img, a)[0]

    def cstr(self, a):
        e = self.img.find(b'\0', a)
        return self.img[a:e].decode('latin1')

    def _dynamic(self):
        mod0 = self.u32(4)
        dyn, out = mod0 + struct.unpack_from('<i', self.img, mod0 + 4)[0], {}
        while True:
            tag, val = struct.unpack_from('<QQ', self.img, dyn)
            dyn += 16
            if tag == 0:
                return out
            out.setdefault(tag, val)

    def _plt(self):
        """{stub address: imported symbol}, from the stubs' adrp x16 / ldr x17, [x16, #off] and the JUMP_SLOT
        relocations."""
        d = self._dynamic()
        got = {}
        for i in range(0, d[DT_PLTRELSZ], 24):
            off, info, _ = struct.unpack_from('<QQq', self.img, d[DT_JMPREL] + i)
            name = struct.unpack_from('<I', self.img, d[DT_SYMTAB] + (info >> 32) * 24)[0]
            got[off] = self.cstr(d[DT_STRTAB] + name)
        stubs = {}
        for i, w in enumerate(self.words[:-1]):
            if w & 0x9F00001F == 0x90000010 and self.words[i + 1] & 0xFFC003FF == 0xF9400211:
                a = 4 * i
                stubs[a] = got.get(adrp_page(w, a) + ((self.words[i + 1] >> 10) & 0xFFF) * 8)
        return stubs


def adrp_page(w, a):
    imm = ((w >> 29) & 3) | (((w >> 5) & 0x7FFFF) << 2)
    if imm >= 1 << 20:
        imm -= 1 << 21
    return (a & ~0xFFF) + (imm << 12)


def adrp_target(im, i):
    """The address an adrp at word i forms with the add or ldr / str that uses its register next, or None."""
    w = im.words[i]
    rd, page = w & 31, adrp_page(w, 4 * i)
    for j in range(i + 1, min(i + 8, len(im.words))):
        x = im.words[j]
        if (x >> 5) & 31 != rd:
            continue
        if x & 0xFF800000 == 0x91000000:                 # add (immediate)
            return page + (((x >> 10) & 0xFFF) << (12 if x >> 22 & 1 else 0))
        if x & 0x3B000000 == 0x39000000:                 # ldr / str (unsigned offset)
            return page + (((x >> 10) & 0xFFF) << (x >> 30))
        return None
    return None


def find_hook(im):
    """(address, score) of the best match of the per-frame update's start."""
    best = (None, 0)
    want = {0x1E2E1000, 0x2F00E401, 0x7200003F}   # fmov s0, #1.0; movi d1, #0; tst w1, #1
    for i, w in enumerate(im.words[:-32]):
        if w & 0xFFC003FF != 0x39400008 or im.words[i + 1] & 0xFFF8001F != 0x36080008 or im.words[i + 2] != PACIBSP:
            continue
        score = 3 + len(want & set(im.words[i + 3:i + 24]))
        if score > best[1]:
            best = (4 * i, score)
    return best


def string_at(im, s):
    m = re.search(b'\0' + re.escape(s.encode()) + b'\0', im.img)
    return m.start() + 1 if m else None


def named_vtable(im, name, slot):
    """The vtable whose slot returns the string name: adrp x0 / add x0 / ret, and a data word pointing at it."""
    s = string_at(im, name)
    if s is None:
        return None
    for i, w in enumerate(im.words[:-2]):
        if w & 0x9F00001F == 0x90000000 and im.words[i + 2] == RET and adrp_target(im, i) == s:
            fn = struct.pack('<Q', 4 * i)
            for m in re.finditer(re.escape(fn), im.img):
                vt = m.start() - 8 * slot
                if m.start() % 8 == 0 and vt >= im.text_end and im.u64(vt - 8) == 0 and im.u64(vt - 16) == 0:
                    return vt
    return None


def vtables(im):
    """Start (slot 0) of every vtable-looking run: two zero words, then code pointers."""
    data = im.img
    for a in range((im.text_end + 7) & ~7, len(data) - 48, 8):
        if im.u64(a) == 0 and im.u64(a + 8) == 0:
            first = [im.u64(a + 16 + 8 * k) for k in range(4)]
            if all(0x1000 <= f < im.text_end for f in first):
                yield a + 16


def find_vt_gfx(im, hook):
    best = (None, 0)
    for vt in vtables(im):
        near = sum(abs(im.u64(vt + 8 * k) - hook) < 0x3000 for k in range(6))
        if near > best[1]:
            best = (vt, near)
    return best[0] if best[1] >= 3 else None


def find_scene_shadow(im):
    """(vtable, distance offset) from the constructor's 1.5 / 15 and 120 / 120 floats."""
    w = im.words
    for i in range(len(w) - 4):
        if w[i] & 0xFFFFFFE0 != 0xD2A7F800:                       # movz xA, #0x3fc0, lsl #16 (1.5)
            continue
        ra = w[i] & 31
        if not any(w[j] == 0xF2E82E00 | ra for j in range(i + 1, i + 4)):   # movk xA, #0x4170, lsl #48 (15)
            continue
        for j in range(i - 4, i + 6):
            if w[j] & 0xFFFFFFE0 == 0xD2A85E00:                   # movz xB, #0x42f0, lsl #16 (120)
                rb = w[j] & 31
                if not any(w[k] == 0xF2E85E00 | rb for k in range(j + 1, j + 4)):
                    continue
                dist = None
                for k in range(i, i + 12):                         # stp xA, xB, [x0, #o]: the distance is o + 12
                    x = w[k]
                    if x & 0xFFC00000 == 0xA9000000 and x & 31 == ra and (x >> 10) & 31 == rb:
                        imm = (x >> 15) & 0x7F
                        dist = (imm - 128 if imm & 64 else imm) * 8 + 12
                        break
                for k in range(i - 1, i - 32, -1):                 # the vtable the constructor stores
                    if w[k] & 0x9F000000 == 0x90000000:
                        vt = adrp_target(im, k)
                        if vt and vt >= im.text_end and im.u64(vt - 8) == 0 and im.u64(vt - 16) == 0:
                            return vt, dist
    return None, None


def find_singleton_global(im, vt):
    """The singleton's global: the disposer's destructor loads it, deletes the object it points at and clears it (str
    xzr). That disposer's vtable ends right before vt's header (two words before it: the destructors)."""
    for fn in (im.u64(vt - 32), im.u64(vt - 24)):
        if not 0 < fn < im.text_end:
            continue
        loaded, cleared = set(), []
        regs = {}                                                  # register -> page of its last adrp
        for i in range(fn // 4, fn // 4 + 48):
            x = im.words[i]
            if x & 0x9F000000 == 0x90000000:
                regs[x & 31] = adrp_page(x, 4 * i)
            elif x & 0xFFC00000 == 0xF9400000 and (x >> 5) & 31 in regs:          # ldr xR, [xN, #off]
                a = regs[(x >> 5) & 31] + ((x >> 10) & 0xFFF) * 8
                nxt = im.words[i + 1]
                if nxt & 0xFFC00000 == 0xF9400000 and (nxt >> 5) & 31 == x & 31:   # then ldr xS, [xR]: an object
                    loaded.add(a)
            elif x & 0xFFC0001F == 0xF900001F and (x >> 5) & 31 in regs:          # str xzr, [xN, #off]
                cleared.append(regs[(x >> 5) & 31] + ((x >> 10) & 0xFFF) * 8)
        for a in cleared:
            if a in loaded:
                return a
    return None


def find_console(im):
    """(global, operation mode offset) from the constructor that caches the nn::oe state."""
    names = {s: a for a, s in im.plt.items() if s}
    op = names.get('_ZN2nn2oe16GetOperationModeEv')
    perf = names.get('_ZN2nn2oe18GetPerformanceModeEv')
    if op is None:
        return None, None
    w = im.words
    for i, x in enumerate(w):
        if x >> 26 != 0x25:                                         # bl
            continue
        t = 4 * i + ((((x & 0x3FFFFFF) ^ 0x2000000) - 0x2000000) << 2)
        if t != op:
            continue
        nxt = w[i + 1]
        if nxt & 0xFFC0001F != 0xB9000000:                          # str w0, [xS, #off]
            continue
        field, rs = ((nxt >> 10) & 0xFFF) * 4, (nxt >> 5) & 31
        calls = [4 * k + ((((w[k] & 0x3FFFFFF) ^ 0x2000000) - 0x2000000) << 2) for k in range(i + 1, i + 8)
                 if w[k] >> 26 == 0x25]
        if perf not in calls:
            continue
        for k in range(i + 2, i + 16):                              # str xS, [xG, #off]: the global
            y = w[k]
            if y & 0xFFC0001F == 0xF9000000 | rs:
                rg = (y >> 5) & 31
                for j in range(k - 1, i, -1):
                    if w[j] & 0x9F00001F == 0x90000000 | rg:
                        return adrp_page(w[j], 4 * j) + ((y >> 10) & 0xFFF) * 8, field
    return None, None


def hook_reads(im, hook, offsets):
    """The offsets the hook's function loads from the graphics system (x0, kept in another register)."""
    seen = set()
    for i in range(hook // 4, hook // 4 + 300):
        x = im.words[i]
        if x & 0xFFC00000 == 0xF9400000:                            # ldr xT, [xN, #off]
            seen.add(((x >> 10) & 0xFFF) * 8)
    return {o: o in seen for o in offsets}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('main', help="exefs/main of the build (a game folder's unpacked one, or the dump's)")
    ap.add_argument('--expect', action='store_true', help='compare with the 1.1.1 values')
    a = ap.parse_args()
    im = Image(a.main)
    found, how = {}, {}

    hook, score = find_hook(im)
    found['HOOK_SITE'], how['HOOK_SITE'] = hook, f'per-frame update signature, score {score} of 6'
    for key, (name, slot) in NAMED.items():
        found[key], how[key] = named_vtable(im, name, slot), f'slot {slot} returns "{name}"'
    found['VT_GFX'] = find_vt_gfx(im, hook) if hook is not None else None
    how['VT_GFX'] = 'its first slots point next to the hook'
    found['VT_SCENE_SHADOW'], found['SCENE_SHADOW_DIST'] = find_scene_shadow(im)
    how['VT_SCENE_SHADOW'] = how['SCENE_SHADOW_DIST'] = 'constructor floats 1.5, 15, 120, 120'
    found['G_FOLIAGE'] = find_singleton_global(im, found['VT_FOLIAGE']) if found['VT_FOLIAGE'] else None
    how['G_FOLIAGE'] = 'cleared by the foliage singleton disposer'
    found['G_CONSOLE'], found['CONSOLE_OPERATION_MODE'] = find_console(im)
    how['G_CONSOLE'] = how['CONSOLE_OPERATION_MODE'] = 'the nn::oe::GetOperationMode cache'

    print('// runtime/gfx_tweaks.c')
    for key in EXPECT_111:
        v = found.get(key)
        val = f'{v:#x}ull' if v is not None else 'NOT FOUND'
        print(f'#define {key} {val}   // {how[key]}')
    if hook is not None:
        print('\n// recomp/patches-v<ver>.txt')
        word = im.u32(hook)
        print(f'site gfx_hook main {hook:x} {word:08x} d409cb01 {word:08x}')
        checks = hook_reads(im, hook, (0xb30, 0xd50, 0x150))
        print('\n// graphics system offsets the hook\'s function reads: ' +
              ', '.join(f'{o:#x} {"yes" if ok else "NO"}' for o, ok in checks.items()))
    bad = [k for k in EXPECT_111 if found.get(k) is None]
    if a.expect:
        bad += [f'{k} {found.get(k)} != {v:#x}' for k, v in EXPECT_111.items()
                if found.get(k) is not None and found[k] != v]
    if bad:
        print('\nnot found or not as expected: ' + ', '.join(bad))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
