param(
  [Parameter(Mandatory=$false)]
  [string]$ArtifactRoot = "."
)
$ErrorActionPreference = "Stop"
$remote = "/data/local/tmp/edgeai"
$files = @("libedgeai.so","libc++_shared.so","edgeai_chat")
foreach ($f in $files) {
  $p = Join-Path (Join-Path $ArtifactRoot "arm64-v8a") $f
  if (-not (Test-Path $p)) { throw "Missing $p" }
}
adb get-state | Out-Null
adb shell "rm -rf '$remote' && mkdir -p '$remote'"
foreach ($f in $files) {
  $p = Join-Path (Join-Path $ArtifactRoot "arm64-v8a") $f
  adb push $p "$remote/$f" | Out-Null
}
adb shell "chmod 755 '$remote/edgeai_chat'"
$out = adb shell "cd '$remote' && LD_LIBRARY_PATH='$remote' ./edgeai_chat --memory :memory: --prompt 'Subtract 17 from 42'"
$out | Write-Output
if (-not ($out -match "(?m)^25\r?$")) { throw "Expected calculator result 25" }
if (-not ($out -match "route=calculator")) { throw "Expected calculator route" }
if (-not ($out -match "neural=0")) { throw "Expected deterministic route" }
Write-Output "Android physical smoke passed"
