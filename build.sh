#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j "${EDGEAI_BUILD_JOBS:-2}"
ctest --test-dir build --output-on-failure
