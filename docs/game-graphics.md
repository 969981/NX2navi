# Game graphics settings

The menu's Screen tab has a "Game graphics" group that changes the game's own rendering parameters while it runs:

| Setting | Key (`nx2navi.ini`, `[display]`) | Values | What changes |
|---|---|---|---|
| Foliage distance | `gfx_foliage` | 25 to 400 (percent) | the distances small trees, bushes and flowers are drawn to |
| 3D object detail | `gfx_objects` | 100 to 400 | the distance scale of the models' level of detail |
| Grass density | `gfx_grass` | 0 to 300 | how much grass grows (0: none; above 300 it breaks up) |
| Shadow distance | `gfx_shadows` | 25 to 400 | the scenery's shadow distance (160 m) and the characters' |
| Screen-space shadows | `gfx_contact_shadows` | 1, 0 | the game's own contact shadows (not `contact_shadows`, the runtime's pass) |
| Base quality | `gfx_base_quality` | normal, low | low: the game's handheld graphics preset |

Each percentage multiplies the game's own value, so 100 is the game as shipped, and a change applies at the next
frame. The code is [runtime/gfx_tweaks.c](../runtime/gfx_tweaks.c). Everything below is for **game version 1.1.1**
(main build id `e0f3ccfaf50065ae4ea01eb5aeb13b1a…`); "Porting to another game build" says what to do for another one.

## How it works

1. **A hook in the game's own frame.** The graphics system's per-frame update (main+0x31d3200) starts with
   `svc #0x4e58`, put there by the patch set `gfx_hook` of [recomp/patches-v111.txt](../recomp/patches-v111.txt). The
   generator lifts both the original instruction and the replacement, and `rt_patch_on[gfx_hook]` picks one
   ([recomp/patches.py](../recomp/patches.py)). `NX2NAVI_GFX_HOOK=0` switches it off.
2. **The SVC runs host code.** [runtime/svc.c](../runtime/svc.c) hands SVC 0x4e58 (`RT_SVC_HOST_HOOK`, an SVC number
   Horizon does not use) to `gfx_tweaks_hook`, with the site's address. The generated code stores the registers back
   before the SVC and reloads them after, and the hook changes none of them, so the game's function then runs as
   before.
3. **The hook writes the parameters.** Starting from x0 (the graphics system) and two globals, it follows pointers
   to the parameter objects. Each value it scales keeps the game's own value: it is read again whenever the object
   moved or the game wrote its own value since. The write is the game's value times the setting.

Why this way:

- **On the game's thread, at the right moment.** The hook runs where the game itself is about to read these
  parameters, so a write never races with the game and applies to the frame being built. Writing the same memory
  from the menu's thread could not promise either.
- **No game code is rewritten.** The hook only changes data the game reads anyway (its parameter objects, loaded
  from its own files), the same values its own settings would hold. The code patch is one instruction in front of a
  function, switchable at run time like every other patch set.
- **Live.** The settings are read again when the menu changes one (`cfg_version`), so nothing needs a restart.
- **Off means untouched.** Nothing is written until a setting leaves its default, and 100 % writes the game's own
  values back.

### Safety on another game build

The offsets are 1.1.1's. Three things keep another build from being harmed:

- **The patch set is `optional`.** When the instruction at the site is not the expected one, the generator leaves
  the set out with a note (`patches: optional set gfx_hook left out: ...`) instead of stopping, so the rest of the
  game still lifts and builds (`prune` in [recomp/patches.py](../recomp/patches.py)). Without the set,
  `rt_patch_set("gfx_hook")` is -1: the hook never runs and the menu does not show the rows.
- **The build id is checked.** `gfx_tweaks_available` and the hook both compare main's build id with `MAIN_BUILD_ID`.
  On another build the rows stay hidden and the hook writes nothing, even if the site happened to match. The log says
  why once: `gfx tweaks: main's build id ... is not the one the offsets are for`.
- **Vtables are checked.** The graphics system and the last object of every pointer chain must have exactly the
  vtable of 1.1.1. The objects in between must have a vtable inside main. A chain that does not match is skipped for
  that frame, so a moved offset reads, but never writes.

## The values (1.1.1)

`main+X` is an offset in main's image (its base is `MOD_MAIN_BASE`). "vt" is the address an object's first word
holds. The class names are the game's own: its reflection keeps a type name in slot 12 of a parameter class's vtable
(a function `adrp x0; add x0; ret` returning `"game__gfx__ModelLodParam"`).

```
graphics system  = x0 at main+0x31d3200          vt 0x4b8bc00 (VT_GFX)
  +0xd50 holder -> +0x150 game::gfx::ModelLodParam             vt 0x4b87a88 (VT_MODEL_LOD)
        +0x48, +0x4c, +0x50  level-of-detail distance scales, floats      game: 1, 0.8, 1
  +0xb30 scenery shadow settings (no type name)                vt 0x4b8a0a8 (VT_SCENE_SHADOW)
        +0xb4  shadow distance in metres, float                            game: 160
  +0xba8 character shadow renderer -> +0xc18 holder -> +0x150 game::gfx::LocalDepthShadowParam
                                                                vt 0x4b86828 (VT_CHAR_SHADOW)
        +0x90, +0x94  distance the shadows end at and start to fade from, floats   game: 30 (+0x90)
  +0xc08 screen-space contact shadow pass
        +0x318  bit 0: drawn
*(main+0x4e22540) foliage component, name "Foliage"            vt 0x4b24800 (G_FOLIAGE, VT_FOLIAGE)
  +0xf0 foliage system -> +0x2a90 holder -> +0x150 game::foliage::ResFoliageScene
                                                                vt 0x4b23228 (VT_FOLIAGE_SCENE)
        +0x68  grass density, float                                        game: 150
        +0x40, +0x48 -> game::foliage::ResLodSetting           vt 0x4b235d0 (VT_FOLIAGE_LOD)
              +0x38  8 distances, floats                                   game: 135 ... and 50 ...
*(main+0x4e97dd8) the game's copy of the nn::oe state           (G_CONSOLE)
        +0x20  GetOperationMode (0 handheld, 1 docked), int32: low writes 0
        +0x24 GetPerformanceMode, +0x28 GetCurrentFocusState, +0x2c GetCurrentGraphicsScale
```

The "game:" values are what the log showed in Kokiri Forest (`gfx tweaks: <name>: the game's value <v>`: the first value
of each run, the first time it is scaled). They come from the game's data files, not all from the constructors. Checked
in play: a rock that switched its level of detail and grass that vanished at a spot both stay at Very High.

## Porting to another game build

The rest of the game builds without this feature (see above). To bring it back:

1. **Run the finder** on the new main: a game folder's `exefs/main` (stored unpacked), or the dump's own packed one
   (with lz4 / zbic installed):

   ```
   python tools/find_gfx_offsets.py <game>/exefs/main
   ```

   It prints the `#define` block of `gfx_tweaks.c` and the `site` line for the new patch file. Each value comes with
   the rule that found it, and anything it could not find is marked. `--expect` checks the rules against 1.1.1's
   values; on 1.1.1 it finds all of them.

2. **Check the field offsets.** The finder also counts how often the game's own code follows each pointer chain
   (`load +a, then +b from what it gave`). In 1.1.1:

   | Chain | 1.1.1 count | Offsets it backs |
   |---|---|---|
   | `+0x2a90 -> +0x150` | 23 | foliage system's holder, the holder's object |
   | `+0xc18 -> +0x150` | 16 | character shadow holder |
   | `+0xd50 -> +0x150` | 29 | graphics system's ModelLodParam holder |
   | `+0x1e8 -> +0xba8` | 7 | the graphics system (owner +0x1e8), its character shadow renderer |
   | `+0xc08 -> byte +0x318` | 2 | contact shadow pass and its flag |

   It also checks that the hook's function reads the graphics system's +0xb30 and +0xd50. A count that drops to 0
   means that offset moved: find the new one in the functions that use its neighbours (step 3). The offsets inside
   the parameter objects can be read from their constructors, which the vtables lead to:

   | Class (constructor in 1.1.1) | Constructor stores | Offset |
   |---|---|---|
   | ModelLodParam (main+0xf7e7d0, 0x60 bytes) | 1.0, 0.8 (0x3f4ccccd), 1.0 with `stp x8, x9, [x19, #0x48]` | scales +0x48 |
   | LocalDepthShadowParam (main+0xf903c0) | 0.6, 0.4, 150, 100 at +0x88 | distances +0x90 |
   | ResLodSetting (main+0xfea770, 0x68 bytes) | 135, 40, 30, 35, 40, 60, 10, 45 at +0x38, 0.3 at +0x58 | distances +0x38 |
   | ResFoliageScene (main+0xe33c90, 0xb8 bytes) | 50 at +0x68, the path `Work/Game/FoliageDropParam/...` at +0x38 | grass +0x68 |
   | scenery shadow settings (main+0xdbda00) | 1.5, 15, 120, 120 at +0xa8 | distance +0xb4 |
   | nn::oe state (main+0xe376a0) | GetOperationMode's result `str w0, [x19, #0x20]`, then itself to the global | mode +0x20 |

3. **What each rule relies on**, should one stop working:
   - *Hook site*: the update starts with `ldrb w8, [x0, #imm]; tbz w8, #1, ...; pacibsp`, and its first instructions
     include `fmov s0, #1.0`, `movi d1, #0` and `tst w1, #1`. Its one caller (main+0x31c00cc) does `ldr x0, [x19,
     #0x1e8]; bl <update>` in the method at slot 2 of the graphics owner's vtable (main+0x4b895b0).
   - *VT_GFX*: the class's methods sit together: its first slots point at the functions around the hook
     (main+0x31d48b0, 0x31d4d80, 0x31d55e0, then the destructor 0x31d2e10 and 0x31d31d0, the function just before
     the hook).
   - *Named vtables*: the type name strings above (and the foliage component's slot 27, which returns its editor icon
     path `Icon=%PROJECT_TOOL%\Internal\ORIcon\foliage.png`).
   - *G_FOLIAGE*: the component is a singleton. The vtable of its disposer ends right before the component's vtable
     header, and that disposer's destructor loads the global, deletes the object and clears the global
     (`str xzr`).
   - *G_CONSOLE*: the only constructor that calls `nn::oe::GetOperationMode`, `GetPerformanceMode`,
     `GetCurrentFocusState` and `GetCurrentGraphicsScale` in a row (imports, named in main's dynamic symbols) and
     stores itself in a global.
   - *VT_SCENE_SHADOW*: its constructor's float constants.

   With the old and new mains side by side, a function can also be matched by its shape: the same calls, constants
   and field offsets. `recomp/gen.py` lifts both to C (`f_<address>` per function), which can be compared directly.

4. **Write it in.** Copy the `site gfx_hook ...` line (and `set gfx_hook ... optional`) into the new
   `recomp/patches-v<ver>.txt`. Put the new values into `gfx_tweaks.c`, and the new build id (the NSO header at
   +0x40, as `tools/make_game.py` `MAIN_BUILD_ID` has it) into `MAIN_BUILD_ID`. Supporting several builds at once
   means turning the `#define` block into one table per build id.

5. **Check in play.** Start the game with every setting changed, without the menu:

   ```
   set NX2NAVI_GFX_FOLIAGE=300
   set NX2NAVI_GFX_OBJECTS=200
   set NX2NAVI_GFX_GRASS=150
   set NX2NAVI_GFX_SHADOWS=200
   ocarina.exe
   ```

   Then walk into Kokiri Forest. `logs/nx2navi.log` should show `patches: ... gfx_hook on` and, once per value,
   `gfx tweaks: <name>: the game's value <v>`, with values like 1.1.1's above (game data seldom changes). A missing
   line means its chain stopped at a check. Then look at it: find a spot where grass vanishes or a rock changes its
   level of detail as you step back at 100 %, and check that it stays at 300 %.
