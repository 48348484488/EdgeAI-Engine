#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:-.}"
REMOTE="/data/local/tmp/edgeai"
for f in libedgeai.so libc++_shared.so edgeai_chat; do
  test -f "$ROOT/arm64-v8a/$f" || { echo "missing $ROOT/arm64-v8a/$f" >&2; exit 2; }
done
adb get-state >/dev/null
adb shell "rm -rf '$REMOTE' && mkdir -p '$REMOTE'"
adb push "$ROOT/arm64-v8a/libedgeai.so" "$REMOTE/libedgeai.so" >/dev/null
adb push "$ROOT/arm64-v8a/libc++_shared.so" "$REMOTE/libc++_shared.so" >/dev/null
adb push "$ROOT/arm64-v8a/edgeai_chat" "$REMOTE/edgeai_chat" >/dev/null
adb shell "chmod 755 '$REMOTE/edgeai_chat'"
OUT="$(adb shell "cd '$REMOTE' && LD_LIBRARY_PATH='$REMOTE' ./edgeai_chat --memory :memory: --prompt 'Subtract 17 from 42'")"
printf '%s
' "$OUT"
grep -q '^25$' <<<"$OUT"
grep -q 'route=calculator' <<<"$OUT"
grep -q 'neural=0' <<<"$OUT"
echo "Android physical smoke passed"
