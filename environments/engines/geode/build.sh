#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export OPENBLAS_NUM_THREADS=1
python build_v3.py
g++ -O3 -std=c++17 -fopenmp -mavx2 -ffp-contract=off -fno-math-errno src/cathedral_v3.cpp -o cathedral_v3
