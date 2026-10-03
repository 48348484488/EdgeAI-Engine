#!/usr/bin/env bash
set -euo pipefail

APK="${1:-android/app/build/outputs/apk/debug/app-debug.apk}"
PKG="com.edgeai.smoke"
ACTIVITY="$PKG/.MainActivity"
TAG="EDGEAI_SMOKE"

test -f "$APK"
adb wait-for-device
adb install -r "$APK"
adb shell pm path "$PKG" | grep -q '^package:'

fail_on_android_crash() {
  local log="$1"
  if grep -E -q 'FATAL EXCEPTION|ANR in com\.edgeai\.smoke|Fatal signal|UnsatisfiedLinkError' "$log"; then
    echo "Android crash/ANR detected" >&2
    grep -E 'FATAL EXCEPTION|ANR in com\.edgeai\.smoke|Fatal signal|UnsatisfiedLinkError' "$log" >&2 || true
    return 1
  fi
}

run_case() {
  local name="$1"
  local prompt="$2"
  local expected="$3"
  local filtered="/tmp/edgeai-${name}.log"
  local full="/tmp/edgeai-${name}-full.log"

  adb shell am force-stop "$PKG" || true
  adb logcat -c
  adb shell "am start -W -n \"$ACTIVITY\" --es prompt '$prompt'" | tee "/tmp/edgeai-${name}-am-start.txt"

  local found=0
  for _ in $(seq 1 20); do
    adb logcat -d > "$full"
    grep -F "$TAG" "$full" > "$filtered" || true
    if grep -E -q "$expected" "$filtered"; then
      found=1
      break
    fi
    sleep 1
  done

  cat "$filtered" || true
  fail_on_android_crash "$full"
  if ! grep -E -q 'elapsed_us=[0-9]+' "$filtered"; then
    echo "Latency marker missing for case: $name" >&2
    return 1
  fi
  if [[ "$found" != 1 ]]; then
    echo "Expected result not found for case: $name" >&2
    tail -n 250 "$full" >&2
    return 1
  fi
}

run_case calc "Subtract 17 from 42" '25.*route=calculator.*neural=0'
run_case copy "Copy exactly: edge" 'edge.*route=text_copy.*neural=0'
run_case uppercase "Uppercase: edge ai" 'EDGE AI.*route=text_uppercase.*neural=0'
run_case reverse "Reverse: abcdef" 'fedcba.*route=text_reverse.*neural=0'
run_case symbolic "Return only x + 57" 'x\+57.*route=symbolic_expression.*neural=0'
run_case neural "neural smoke" 'route=neural.*neural=1'

adb shell dumpsys meminfo "$PKG" | tee /tmp/edgeai-meminfo.txt
adb shell dumpsys activity activities | grep -F "$PKG" | head -n 20 | tee /tmp/edgeai-activity.txt || true
adb logcat -d > /tmp/edgeai-final-logcat.txt
fail_on_android_crash /tmp/edgeai-final-logcat.txt
adb shell am force-stop "$PKG"

echo "EdgeAI Android emulator smoke passed"
