// Game graphics settings (gfx_tweaks.c): foliage distance, 3D object detail, grass density, shadow distance, the game's
// own screen-space contact shadows and its handheld quality preset, changed live from the menu.
#pragma once
#include <stdint.h>

#include "cpu.h"

// The SVC number a code patch puts in front of a game instruction to run a host hook there (recomp/patches-v111.txt,
// set gfx_hook). Horizon's SVCs stop at 0x7f, so the number is free; svc.c hands it to gfx_tweaks_hook.
#define RT_SVC_HOST_HOOK 0x4e58

// The hook at the start of the graphics system's per-frame update. 1 when pc is that site (the hook ran), 0 for
// another address. Keeps every register.
int gfx_tweaks_hook(Cpu *c, uint64_t pc);
// 1 when this build has the hook (the optional gfx_hook patch set is in the generated C and switched on) and main is
// the game build the offsets belong to: the menu shows the rows.
int gfx_tweaks_available(void);
