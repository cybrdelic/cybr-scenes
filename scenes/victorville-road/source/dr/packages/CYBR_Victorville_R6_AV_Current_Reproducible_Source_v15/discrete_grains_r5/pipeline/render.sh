#!/bin/sh
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export LIBGL_ALWAYS_SOFTWARE=1 EGL_PLATFORM=surfaceless
export LP_NUM_THREADS=2
export XDG_CACHE_HOME="$ROOT/cache" MESA_SHADER_CACHE_DIR="$ROOT/cache"
exec "${BLENDER_BIN:-blender}" -b -t 2 --python-exit-code 1 --python "$ROOT/render.py" -- "$1"
