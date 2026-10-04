#!/usr/bin/env python3
import argparse
import pathlib
import re
import subprocess
import sys
import shutil


EXCLUDED = {
    "src/CodeSearch.cpp",
    "src/HybridBackend.cpp",
    "src/EdgeModel.cpp",
    "src/TernaryBackend.cpp",
    "android/app/src/main/cpp/jni.cpp",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=".")
    parser.add_argument("--build")
    parser.add_argument("--cmake", default="cmake")
    parser.add_argument("--binary")
    args = parser.parse_args()
    root = pathlib.Path(args.source).resolve()
    cmake_text = (root / "CMakeLists.txt").read_text(encoding="utf-8")
    match = re.search(r"set\(EDGEAI_LOW_RESOURCE_SOURCES(.*?)\n\)", cmake_text, re.S)
    if not match:
        raise AssertionError("EDGEAI_LOW_RESOURCE_SOURCES allowlist is missing")
    sources = set(re.findall(r"(?:src|android)/[^\s)]+", match.group(1)))
    leaked = sorted(EXCLUDED & sources)
    if leaked:
        raise AssertionError(f"excluded sources leaked into focused target: {leaked}")
    if "add_library(edgeai_low_resource" not in cmake_text:
        raise AssertionError("focused library target is missing")
    if "add_executable(edgeai_low_resource_cli" not in cmake_text:
        raise AssertionError("focused CLI target is missing")
    if args.build:
        build = pathlib.Path(args.build).resolve()
        subprocess.run([
            args.cmake, "-S", str(root), "-B", str(build),
            "-DEDGEAI_LOW_RESOURCE=ON", "-DEDGEAI_BUILD_TESTS=ON",
            "-DEDGEAI_BUILD_BENCHMARK=OFF",
        ], check=True)
        subprocess.run([args.cmake, "--build", str(build), "--target", "edgeai_low_resource_cli"], check=True)
    if args.binary:
        inspector = shutil.which("llvm-nm") or shutil.which("nm")
        if not inspector:
            raise AssertionError("symbol inspector is required when --binary is used")
        symbols = subprocess.run([inspector, "-C", args.binary], check=True, capture_output=True, text=True).stdout
        forbidden_symbols = ("edgeai::CodeIndex", "edgeai::HybridBackend", "edgeai::EdgeModel",
                             "edgeai::TernaryBackend", "Java_com_edgeai")
        leaked_symbols = [name for name in forbidden_symbols if name in symbols]
        if leaked_symbols:
            raise AssertionError(f"excluded symbols leaked into focused binary: {leaked_symbols}")
    print("low-resource composition: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
