#!/usr/bin/env python3
"""Fail closed unless the documented Linux x86-64 AVX2 replay profile is active."""
import ctypes
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import sys

DISABLED = 'AVX512F,AVX512CD,AVX512_KNL,AVX512_KNM,AVX512_SKX,AVX512_CLX,AVX512_CNL,AVX512_ICL,AVX512_SPR'

def require(condition, message):
    if not condition:
        raise SystemExit('Unsupported whole-region exact replay profile: ' + message)

require(platform.system() == 'Linux' and platform.machine().lower() in {'x86_64','amd64'},
        'requires Linux x86-64; no ARM or other-architecture bitwise reproduction is claimed.')
require(os.getenv('OPENBLAS_CORETYPE') == 'Haswell', 'set OPENBLAS_CORETYPE=Haswell before starting Python (use ./run.sh).')
require(os.getenv('NPY_DISABLE_CPU_FEATURES') == DISABLED, 'the complete pinned AVX512 disable list must be set before NumPy import (use ./run.sh).')
# Check actual hardware before importing a library asked to use AVX2/FMA code.
flags = [set(line.partition(':')[2].split()) for line in Path('/proc/cpuinfo').read_text().splitlines() if line.startswith('flags')]
require(bool(flags) and all({'avx2','fma'} <= row for row in flags), 'processor must expose AVX2 and FMA on every available CPU.')
require('numpy' not in sys.modules, 'profile validation must precede NumPy import.')
import numpy as np
from numpy._core._multiarray_umath import __cpu_features__, __cpu_dispatch__
require(np.__version__ == '2.3.5', 'requires the pinned NumPy 2.3.5 wheel.')
require(__cpu_features__.get('AVX2') and __cpu_features__.get('FMA3'), 'NumPy AVX2/FMA dispatch unavailable.')
require(not any(__cpu_features__.get(name) for name in __cpu_dispatch__ if name.startswith('AVX512')), 'NumPy AVX512 dispatch remains enabled.')
libraries = list((Path(np.__file__).resolve().parent.parent/'numpy.libs').glob('*openblas*.so'))
require(len(libraries) == 1, 'expected the pinned NumPy wheel with one bundled OpenBLAS shared library.')
library = ctypes.CDLL(str(libraries[0]))
function = getattr(library,'scipy_openblas_get_corename64_',None)
require(function is not None, 'bundled OpenBLAS does not expose the expected core-name query.')
function.restype = ctypes.c_char_p
core = function().decode()
require(core == 'Haswell', 'OpenBLAS selected '+core+' instead of Haswell.')
report = {'passed':True,'profile':'linux-x86_64-avx2-haswell-v1','python':platform.python_version(),
          'machine':platform.machine(),'OPENBLAS_CORETYPE':core,'NPY_DISABLE_CPU_FEATURES':DISABLED,
          'numpy_cpu_features':__cpu_features__,
          'packages':{name:importlib.metadata.version(name) for name in ['numpy','scipy','Pillow','trimesh','shapely','pyproj','rasterio']},
          'scope':'Explicit supported x86-64 CPU-dispatch contract, not universal cross-architecture bitwise reproduction.'}
if len(sys.argv)>1:
    target=Path(sys.argv[1]);target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
