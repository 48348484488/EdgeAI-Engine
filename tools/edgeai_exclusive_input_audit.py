#!/usr/bin/env python3
"""Audit exclusive gameplay/UI modes from real ordered runtime events.

Generic for construction, inventory editing, vehicle controls, photo modes,
and other stateful UIs. This checks *observed* logs, not visual parity.
"""
import argparse
import json
from pathlib import Path


def _marker(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty string")
    return value


def audit(log, spec):
    if not isinstance(log, str) or not isinstance(spec, dict):
        raise ValueError("log must be text and spec must be an object")
    enter = _marker(spec.get("enter"), "enter")
    exit_marker = _marker(spec.get("exit"), "exit")
    capture_spec = spec.get("capture")
    if isinstance(capture_spec, str):
        captures = [_marker(capture_spec, "capture")]
    elif isinstance(capture_spec, list) and capture_spec:
        captures = [_marker(value, "capture item") for value in capture_spec]
    else:
        raise ValueError("capture must be a marker or nonempty list of markers")
    forbidden = spec.get("forbidden", [])
    if not isinstance(forbidden, list) or not forbidden:
        raise ValueError("forbidden must contain at least one gameplay marker")
    forbidden = [_marker(v, "forbidden item") for v in forbidden]
    markers = [enter, exit_marker, *captures, *forbidden]
    if len(set(markers)) != len(markers):
        raise ValueError("event markers must be unique")
    required = spec.get("minimum_captures", 1)
    if type(required) is not int or required < 0:
        raise ValueError("minimum_captures must be a nonnegative integer")
    require_exit = spec.get("require_exit", True)
    if type(require_exit) is not bool:
        raise ValueError("require_exit must be boolean")

    active = False
    entries = 0
    exits = 0
    captures = 0
    violations = []
    for line_no, line in enumerate(log.splitlines(), 1):
        matched = [name for name in markers if name in line]
        if len(matched) > 1:
            violations.append([line_no, "ambiguous_event"])
            continue
        if not matched:
            continue
        event = matched[0]
        if event == enter:
            if active:
                violations.append([line_no, "duplicate_enter"])
            active = True
            entries += 1
        elif event == exit_marker:
            if not active:
                violations.append([line_no, "orphan_exit"])
            active = False
            exits += 1
        elif event in captures:
            if not active:
                violations.append([line_no, "capture_outside_mode"])
            else:
                captures += 1
        elif active:
            violations.append([line_no, "gameplay_leak:" + event])
    if entries == 0:
        violations.append([0, "mode_never_observed"])
    if captures < required:
        violations.append([0, "insufficient_observed_captures"])
    if active and require_exit:
        violations.append([len(log.splitlines()), "mode_not_closed"])
    return {
        "mode_entries": entries,
        "mode_exits": exits,
        "captured_touches": captures,
        "violations": violations,
        "passed": not violations,
        "original_game_parity_proven": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    parser.add_argument("spec", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = audit(args.log.read_text(encoding="utf-8"),
                   json.loads(args.spec.read_text(encoding="utf-8")))
    payload = json.dumps(result, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(payload, encoding="utf-8")
    print(payload, end="")
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
