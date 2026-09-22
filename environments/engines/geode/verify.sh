#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p verification_v3
./cathedral_v3 --self-test > verification_v3/native_optics.json
g++ -O3 -std=c++17 -fopenmp -mavx2 -ffp-contract=off -fno-math-errno verification_v3/test_rough_quartz.cpp -o verification_v3/test_rough_quartz
verification_v3/test_rough_quartz > verification_v3/rough_quartz_test.json
OPENBLAS_NUM_THREADS=1 python verification_v3/verify_geometry.py
OPENBLAS_NUM_THREADS=1 python verification_v3/test_filter.py
OPENBLAS_NUM_THREADS=1 python verification_v3/verify_outputs.py
