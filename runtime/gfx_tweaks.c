// Game graphics settings for Ocarina of Time 1.1.1, live from the menu (ui/menu.cpp row_game_gfx). Each is a percent
// of the game's own value, except the last two:
//   NX2NAVI_GFX_FOLIAGE   foliage draw distance (small trees, bushes, flowers)
//   NX2NAVI_GFX_OBJECTS   3D object detail: the distance scale of the models' level of detail (100 and up: below the
//                         game's scale objects vanish)
//   NX2NAVI_GFX_GRASS     grass density (0 = no grass; above 300 the grass breaks up)
//   NX2NAVI_GFX_SHADOWS   shadow distance, of the scenery (160 m in the game) and of the characters
//   NX2NAVI_GFX_CONTACT_SHADOWS  the game's own screen-space contact shadows: 1 on (the game's setting), 0 off. Not
//                         NX2NAVI_CONTACT_SHADOWS, the runtime's own pass (vk_contact.c)
//   NX2NAVI_GFX_BASE_QUALITY     normal, or low: the game's handheld graphics preset, for weaker GPUs
//
// docs/game-graphics.md explains where each value lives, how it was found and how to find it again in another build
// (tools/find_gfx_offsets.py does most of it).
//
// When: the graphics system's per-frame update (main+0x31d3200, called from main+0x31c00cc with the graphics system in
// x0) starts with svc #0x4e58 (patch set gfx_hook, recomp/patches-v111.txt). svc.c calls gfx_tweaks_hook there, on the
// game's own thread, before the update reads the parameters, so a write is seen by the frame being built and never
// races with the game. The SVC keeps every register: the hook only reads x0.
//
// What: from the graphics system (x0) and two of the game's globals the hook follows pointers to the parameter objects
// and writes the values the settings ask for. The game keeps a type name for some classes (their vtable's slot 12
// returns it, e.g. "game__gfx__ModelLodParam"); those names are in the comments below. The last object of every chain
// has its vtable checked exactly, and so has the graphics system; the objects in between only need a vtable inside
// main (game_object), since a wrong offset there cannot reach a leaf of the right class.
//
//   foliage  *(main+0x4e22540), the foliage component [vt 0x4b24800, its name "Foliage"]
//              +0xf0 -> +0x2a90 -> +0x150 = game::foliage::ResFoliageScene [vt 0x4b23228] = S
//            *(S+0x40) and *(S+0x48), two game::foliage::ResLodSetting [vt 0x4b235d0]: 8 distances at +0x38
//            (the game's 135 ... and 50 ...), times the setting
//   grass    S+0x68, the grass density (the game's 150), times the setting
//   objects  graphics system +0xd50 -> +0x150 = game::gfx::ModelLodParam [vt 0x4b87a88]: +0x48, +0x4c, +0x50, the
//            level-of-detail distance scales (the game's 1, 0.8, 1), times the setting
//   shadows  graphics system +0xb30 [vt 0x4b8a0a8] +0xb4: the scenery's shadow distance (160 m), times the setting;
//            graphics system +0xba8 -> +0xc18 -> +0x150 = game::gfx::LocalDepthShadowParam [vt 0x4b86828]: +0x90 and
//            +0x94, the distance the characters' shadows end at and the one they start to fade from, times the setting
//   contact  graphics system +0xc08, byte +0x318 bit 0: the screen-space contact shadows are drawn. Cleared while the
//            setting is off; set again when it is turned back on (only if the hook cleared it)
//   quality  *(main+0x4e97dd8): the game's copy of the console state, filled by nn::oe::GetOperationMode (+0x20),
//            GetPerformanceMode (+0x24), GetCurrentFocusState (+0x28) and GetCurrentGraphicsScale (+0x2c). The graphics
//            code picks its preset from +0x20 (0 handheld, 1 docked); low writes 0 there, and the game's value back
//            when it is set to normal again
//
// A scaled run of floats keeps the game's values (Scaled): the first time, and whenever the object moved or the game
// wrote its own value since (the first float differs from what the hook wrote last), the current values are taken as
// the game's. What is written is always the game's values times the setting, so a change in the menu applies at the
// next frame and 100 % gives the game's values back. Nothing is written until a setting leaves its default: an
// untouched game runs as shipped.
//
// A chain whose object is missing or of another class is skipped for the frame (the title screen, a scene without
// foliage).
//
// Another game build: the offsets belong to main 1.1.1 (build id MAIN_BUILD_ID). The patch set is optional
// (recomp/patches.py prune): a build whose instruction at the hook site differs lifts without it, so the hook never
// runs and gfx_tweaks_available hides the menu rows. Should the site still match, the build id check below keeps the
// hook from writing and the rows hidden, and the vtable checks of every chain stop it at the first object that is not
// what 1.1.1 has there.
#include <stdint.h>
#include <string.h>

#include "cfg.h"
#include "gfx_tweaks.h"
#include "host.h"
#include "layout.h"
#include "mods.h"
#include "platform/platform.h"

// main 1.1.1 (docs/game-graphics.md, "Offsets"; tools/find_gfx_offsets.py finds them in another build)
#define MAIN_BUILD_ID "e0f3ccfaf50065ae4ea01eb5aeb13b1a"   // the build id of main 1.1.1, the build the offsets are for
#define HOOK_SITE 0x31d3200ull      // the graphics system's per-frame update
#define G_FOLIAGE 0x4e22540ull      // global: the foliage component
#define G_CONSOLE 0x4e97dd8ull      // global: the game's copy of the nn::oe console state
#define VT_GFX 0x4b8bc00ull         // the graphics system (x0 at the hook)
#define VT_FOLIAGE 0x4b24800ull     // the foliage component ("Foliage")
#define VT_FOLIAGE_SCENE 0x4b23228ull   // game::foliage::ResFoliageScene
#define VT_FOLIAGE_LOD 0x4b235d0ull     // game::foliage::ResLodSetting
#define VT_MODEL_LOD 0x4b87a88ull       // game::gfx::ModelLodParam
#define VT_CHAR_SHADOW 0x4b86828ull     // game::gfx::LocalDepthShadowParam
#define VT_SCENE_SHADOW 0x4b8a0a8ull    // the scenery's shadow settings (no type name in the game)

// field offsets
#define FOLIAGE_SYSTEM 0xf0      // foliage component -> its system
#define FOLIAGE_SYS_HOLDER 0x2a90   // foliage system -> the holder of the foliage scene
#define HOLDER_PARAM 0x150       // a parameter holder -> its parameter object (also in the graphics system's chains)
#define SCENE_LOD_A 0x40         // ResFoliageScene -> its two ResLodSetting
#define SCENE_LOD_B 0x48
#define SCENE_GRASS 0x68         // ResFoliageScene: grass density (float)
#define LOD_DISTANCES 0x38       // ResLodSetting: 8 distances (floats)
#define GFX_MODEL_LOD 0xd50      // graphics system -> holder of the ModelLodParam
#define MODEL_LOD_SCALES 0x48    // ModelLodParam: 3 distance scales (floats)
#define GFX_SCENE_SHADOW 0xb30   // graphics system -> scenery shadow settings
#define SCENE_SHADOW_DIST 0xb4   // scenery shadow settings: distance in metres (float)
#define GFX_CHAR_SHADOW 0xba8    // graphics system -> character shadow renderer
#define CHAR_SHADOW_HOLDER 0xc18    // character shadow renderer -> holder of the LocalDepthShadowParam
#define CHAR_SHADOW_DIST 0x90    // LocalDepthShadowParam: end and fade-start distances in metres (2 floats)
#define GFX_CONTACT 0xc08        // graphics system -> screen-space contact shadow pass
#define CONTACT_FLAGS 0x318      // contact shadow pass: bit 0 = drawn
#define CONSOLE_OPERATION_MODE 0x20   // console state: nn::oe::GetOperationMode (int32, 0 handheld)

static int ok_at(uint64_t p, uint64_t n) {
    return p >= 0x10000 && p < (1ull << 39) && (p & 7) == 0 && plat_mem_readable(p, n);
}
static uint64_t rd64(uint64_t a) { uint64_t v; memcpy(&v, (const void *)(uintptr_t)a, 8); return v; }
// The object at p when n bytes of it can be read and its vtable is main+vt; 0 otherwise.
static uint64_t obj(uint64_t p, uint64_t vt, uint64_t n) {
    return ok_at(p, n) && rd64(p) == MOD_MAIN_BASE + vt ? p : 0;
}
// An object of the game at p: n bytes readable and a vtable inside main; 0 otherwise.
static uint64_t game_object(uint64_t p, uint64_t n) {
    if (!ok_at(p, n)) return 0;
    uint64_t vt = rd64(p);
    return vt >= MOD_MAIN_BASE && vt < MOD_MAIN_BASE + MOD_MAIN_SIZE ? p : 0;
}
// The pointer field off of p (0 when p is 0).
static uint64_t field(uint64_t p, uint64_t off) { return p ? rd64(p + off) : 0; }

// 1 when main is the build the offsets belong to (its build id, the NSO header's, from mods.c); logged once when not.
static int right_build(void) {
    static int known = -1;   // menu and game thread may both compute it: the same answer
    if (known < 0) {
        const char *bid = mods_main_build_id();
        int ok = !strncmp(bid, MAIN_BUILD_ID, sizeof MAIN_BUILD_ID - 1);
        if (!ok)
            rt_log("gfx tweaks: main's build id %s is not the one the offsets are for (%s): the game graphics settings "
                   "stay off", *bid ? bid : "(unknown)", MAIN_BUILD_ID);
        known = ok;
    }
    return known;
}

// ---- settings
typedef struct { float foliage, objects, grass, shadows; int contact_off, low; } Want;
static Want want = {1, 1, 1, 1, 0, 0};
static unsigned seen = ~0u;
static int touched;   // a setting left its default once: from then on every frame writes (100 % restores the game's)

static float pct(const char *key, int lo, int hi) {
    int v = cfg_int(key);
    return (float)(v < lo ? lo : v > hi ? hi : v) / 100.0f;
}
// Parses the settings again when the menu changed one (cfg_version), on the game thread.
static void settings(void) {
    unsigned v = cfg_version();
    if (v == seen) return;
    seen = v;
    Want w = {pct("NX2NAVI_GFX_FOLIAGE", 0, 400), pct("NX2NAVI_GFX_OBJECTS", 100, 400),
              pct("NX2NAVI_GFX_GRASS", 0, 300), pct("NX2NAVI_GFX_SHADOWS", 25, 400),
              !cfg_bool("NX2NAVI_GFX_CONTACT_SHADOWS"), !strcmp(cfg_value("NX2NAVI_GFX_BASE_QUALITY"), "low")};
    if (memcmp(&w, &want, sizeof w)) {
        rt_log("gfx tweaks: foliage %.0f %%, objects %.0f %%, grass %.0f %%, shadows %.0f %%, game contact shadows %s, "
               "base quality %s", w.foliage * 100, w.objects * 100, w.grass * 100, w.shadows * 100,
               w.contact_off ? "off" : "on", w.low ? "low" : "normal");
        touched = 1;
    }
    want = w;
}

// ---- a run of floats scaled from the game's values
typedef struct {
    uint64_t at;          // where they are; 0 none yet
    int n;
    float game[8];        // the game's values
    float wrote;          // what the hook wrote to the first
    const char *name;     // for the log, once
    int logged;
} Scaled;

static void scale(Scaled *s, uint64_t at, int n, float k) {
    float *p = (float *)(uintptr_t)at;
    if (s->at != at || s->n != n || p[0] != s->wrote) {   // new object, or the game set its own values since
        s->at = at, s->n = n;
        memcpy(s->game, p, sizeof(float) * (size_t)n);
        if (!s->logged++)
            rt_log("gfx tweaks: %s: the game's value %g (at %#llx)", s->name, s->game[0], (unsigned long long)at);
    }
    for (int i = 0; i < n; i++)
        if (p[i] != s->game[i] * k) p[i] = s->game[i] * k;   // only a change is written
    s->wrote = p[0];
}

static Scaled foliage_a = {.name = "foliage distance"}, foliage_b = {.name = "foliage distance (second set)"},
              grass = {.name = "grass density"}, model_lod = {.name = "object detail scale"},
              scene_shadow = {.name = "scenery shadow distance"}, char_shadow = {.name = "character shadow distance"};
static int contact_cleared, console_saved, console_mode;

static void foliage(void) {
    uint64_t f = obj(rd64(MOD_MAIN_BASE + G_FOLIAGE), VT_FOLIAGE, FOLIAGE_SYSTEM + 8);
    f = game_object(field(f, FOLIAGE_SYSTEM), FOLIAGE_SYS_HOLDER + 8);
    f = game_object(field(f, FOLIAGE_SYS_HOLDER), HOLDER_PARAM + 8);
    uint64_t s = obj(field(f, HOLDER_PARAM), VT_FOLIAGE_SCENE, SCENE_GRASS + 4);
    if (!s) return;
    uint64_t a = obj(rd64(s + SCENE_LOD_A), VT_FOLIAGE_LOD, LOD_DISTANCES + 32);
    uint64_t b = obj(rd64(s + SCENE_LOD_B), VT_FOLIAGE_LOD, LOD_DISTANCES + 32);
    if (a) scale(&foliage_a, a + LOD_DISTANCES, 8, want.foliage);
    if (b) scale(&foliage_b, b + LOD_DISTANCES, 8, want.foliage);
    scale(&grass, s + SCENE_GRASS, 1, want.grass);
}

static void graphics(uint64_t g) {
    uint64_t h = game_object(rd64(g + GFX_MODEL_LOD), HOLDER_PARAM + 8);
    uint64_t l = obj(field(h, HOLDER_PARAM), VT_MODEL_LOD, MODEL_LOD_SCALES + 12);
    if (l) scale(&model_lod, l + MODEL_LOD_SCALES, 3, want.objects);
    uint64_t s = obj(rd64(g + GFX_SCENE_SHADOW), VT_SCENE_SHADOW, SCENE_SHADOW_DIST + 4);
    if (s) scale(&scene_shadow, s + SCENE_SHADOW_DIST, 1, want.shadows);
    uint64_t r = game_object(rd64(g + GFX_CHAR_SHADOW), CHAR_SHADOW_HOLDER + 8);
    h = game_object(field(r, CHAR_SHADOW_HOLDER), HOLDER_PARAM + 8);
    uint64_t c = obj(field(h, HOLDER_PARAM), VT_CHAR_SHADOW, CHAR_SHADOW_DIST + 8);
    if (c) scale(&char_shadow, c + CHAR_SHADOW_DIST, 2, want.shadows);
    uint64_t cs = game_object(rd64(g + GFX_CONTACT), CONTACT_FLAGS + 8);
    if (cs) {
        volatile uint8_t *b = (volatile uint8_t *)(uintptr_t)(cs + CONTACT_FLAGS);
        if (want.contact_off && (*b & 1)) *b = (uint8_t)(*b & ~1u), contact_cleared = 1;
        else if (!want.contact_off && contact_cleared) *b = (uint8_t)(*b | 1u), contact_cleared = 0;
    }
}

static void console_state(void) {
    uint64_t q = rd64(MOD_MAIN_BASE + G_CONSOLE);
    if (!game_object(q, CONSOLE_OPERATION_MODE + 4)) return;
    volatile int32_t *mode = (volatile int32_t *)(uintptr_t)(q + CONSOLE_OPERATION_MODE);
    if (want.low) {
        if (!console_saved) console_mode = *mode, console_saved = 1;   // the game's value, put back after
        if (*mode != 0) *mode = 0;
    } else if (console_saved) {
        *mode = console_mode, console_saved = 0;
    }
}

int gfx_tweaks_hook(Cpu *c, uint64_t pc) {
    if (pc != MOD_MAIN_BASE + HOOK_SITE) return 0;
    if (!right_build()) return 1;
    settings();
    if (!touched) return 1;
    uint64_t g = obj(c->x[0], VT_GFX, GFX_MODEL_LOD + 8);   // the graphics system the update runs on
    foliage();
    if (g) graphics(g);
    console_state();
    return 1;
}

int gfx_tweaks_available(void) {
    int set = rt_patch_set("gfx_hook");   // -1 when the lift left the optional set out (another game build)
    return set >= 0 && rt_patch_enabled(set) && right_build();
}
