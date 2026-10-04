"""Verify deterministic fields and emitted artifact hashes across two runs."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def _read_report(directory: Path) -> dict[str, Any]:
    path = directory / "training.json"
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"unable to read training report at {path}: {exc}") from exc
    if not isinstance(report, dict) or not isinstance(report.get("timing"), dict):
        raise ValueError(f"training report at {path} is missing its timing object")
    return report


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_hashes(report: dict[str, Any], directory: Path) -> dict[str, str]:
    hashes = report.get("hashes")
    artifacts = hashes.get("artifacts") if isinstance(hashes, dict) else None
    tokenizer = hashes.get("tokenizer") if isinstance(hashes, dict) else None
    if not isinstance(tokenizer, str) or not tokenizer:
        raise ValueError("training report is missing a tokenizer hash")
    runs = report.get("runs")
    if not isinstance(runs, list) or not runs or any(
            not isinstance(run, dict) or run.get("tokenizer_sha256") != tokenizer
            for run in runs):
        raise ValueError("training report tokenizer hash does not match its runs")
    if not isinstance(artifacts, dict) or not artifacts:
        raise ValueError("training report is missing artifact hashes")

    result: dict[str, str] = {}
    for name, expected in artifacts.items():
        relative = Path(name)
        if (not isinstance(name, str) or relative.is_absolute()
                or ".." in relative.parts or not isinstance(expected, str)):
            raise ValueError(f"invalid artifact hash entry: {name!r}")
        artifact_path = directory / relative
        try:
            actual = _sha256(artifact_path)
        except OSError as exc:
            raise ValueError(f"artifact hash file is missing or unreadable: {name}") from exc
        if actual != expected:
            raise ValueError(f"artifact hash mismatch for {name}")
        result[relative.as_posix()] = expected
    return result


def verify_pair(first_dir: Path, second_dir: Path) -> dict[str, str]:
    """Require equal reports except for top-level wall/CPU timing and verify files."""
    first_dir, second_dir = Path(first_dir), Path(second_dir)
    first, second = _read_report(first_dir), _read_report(second_dir)
    first_deterministic = {key: value for key, value in first.items() if key != "timing"}
    second_deterministic = {key: value for key, value in second.items() if key != "timing"}
    if first_deterministic != second_deterministic:
        raise ValueError("deterministic report differs between quick runs")
    first_hashes = _artifact_hashes(first, first_dir)
    second_hashes = _artifact_hashes(second, second_dir)
    if first_hashes != second_hashes:
        raise ValueError("artifact hash entries differ between quick runs")
    return first_hashes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("first_run", type=Path)
    parser.add_argument("second_run", type=Path)
    args = parser.parse_args(argv)
    artifact_hashes = verify_pair(args.first_run, args.second_run)
    print(json.dumps({"verified_artifacts": artifact_hashes}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
