"""Build bundled linear-scrambled Sobol directions; no runtime SciPy dependency."""
from pathlib import Path
from scipy.stats import qmc
s=qmc.Sobol(d=1024,scramble=True,seed=771395,bits=32)
p=Path(__file__).with_name('sobol_directions.h')
with p.open('w') as f:
 f.write('#pragma once\n// SciPy Joe-Kuo direction numbers, deterministic linear scramble.\nstatic constexpr uint32_t SOBOL_DIRECTIONS[1024][32] = {\n')
 for row in s._sv:f.write('{'+','.join(hex(int(v))+'u' for v in row)+'},\n')
 f.write('};\n')
print(p)
