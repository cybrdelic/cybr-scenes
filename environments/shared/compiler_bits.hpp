// SPDX-License-Identifier: GPL-2.0-only
#pragma once
#if defined(_MSC_VER)
#include <intrin.h>
#endif
namespace cybr_native {
inline unsigned trailing_zero_bits(unsigned value) {
    if (!value) return 32;
#if defined(_MSC_VER)
    unsigned long index;
    _BitScanForward(&index, value);
    return static_cast<unsigned>(index);
#else
    return static_cast<unsigned>(__builtin_ctz(value));
#endif
}
}
