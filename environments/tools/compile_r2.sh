#!/usr/bin/env bash
set -eu
ROOT=$(cd "$(dirname "$0")/.." && pwd); cd "$ROOT"
for k in geo hot geode obsidian; do
 case $k in
 geo) source=engines/geo/cybr-geo/native/spectral_scenes.cpp;extra="";;
 hot) source=engines/hot/cybr-geo/native/spectral_desert.cpp;extra="";;
 geode) source=engines/geode/src/cathedral_v3.cpp;extra="-mavx2 -ffp-contract=off";;
 obsidian) source=engines/obsidian/src/render.cpp;extra="-Iengines/obsidian/include";;
 esac
 echo "COMPILING $k $(date -Is)"
 g++ -std=c++17 -O3 -march=native -fno-math-errno -fopenmp -Ishared $extra "$source" -o "build/${k}_r2"
 if [ "$k" != obsidian ]; then "build/${k}_r2" --self-test; fi
 echo "COMPILED $k $(date -Is)"
done
