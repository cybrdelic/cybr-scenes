#!/usr/bin/env bash
set -eu
ROOT=$(cd "$(dirname "$0")/.." && pwd)
exec python "$ROOT/tools/compile_originals.py"
