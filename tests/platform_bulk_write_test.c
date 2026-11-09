// Synthetic Linux write-watch regression; no game content required.
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "platform/platform.h"
int main(void) {
    const uint64_t a = 0x6000000000ull, n = 4 * 4096;
    uint64_t pages[4];
    assert(plat_mem_reserve(a, n, 1));
    assert(plat_mem_commit(a, n));
    memset((void *)(uintptr_t)a, 0, n);
    uint64_t count = plat_mem_written(a, n, pages, 4, 1);
    if (count == UINT64_MAX) { puts("SKIP: asynchronous write watch unavailable"); return 77; }
    assert(plat_mem_written(a, n, pages, 4, 0) == 0);
    assert(plat_mem_prepare_write(a + 7, n - 14));
    memset((void *)(uintptr_t)(a + 7), 0x5a, n - 14);
    assert(plat_mem_written(a, n, pages, 4, 1) == 4);
    for (unsigned i = 0; i < 4; i++) assert(pages[i] == a + i * 4096);
    assert(plat_mem_written(a, n, pages, 4, 0) == 0);
    *(volatile unsigned char *)(uintptr_t)(a + 2 * 4096) = 0xa5;
    assert(plat_mem_written(a, n, pages, 4, 1) == 1 && pages[0] == a + 2 * 4096);
    assert(!plat_mem_prepare_write(a, 0));
    assert(!plat_mem_prepare_write(UINT64_MAX - 7, 16));
    puts("bulk write watch: full range tracked, reset clean, subsequent single-page write tracked");
    return 0;
}
