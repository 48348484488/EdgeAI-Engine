#!/usr/bin/env python3
"""Generic, evidence-preserving audit of ordered runtime events.

Consumes a JSON rule set, not game-specific source code. Can validate ARM
emulator logs, native game traces and UI state transitions without treating
synthetic fixtures as proof of original-game parity.
"""
import argparse
import json
import math
import re
from pathlib import Path


def audit(log_text, rules):
    lines = log_text.splitlines()
    steps = rules.get("steps", [])
    if not isinstance(steps, list) or not steps:
        raise ValueError("steps must be a nonempty array")
    names = [s["name"] for s in steps]
    if len(names) != len(set(names)):
        raise ValueError("duplicate step names")
    matches = {}
    errors = []
    cursor = 0
    for step in steps:
        pattern = re.compile(step["pattern"])
        hit = next(((i, line) for i, line in enumerate(lines[cursor:], cursor)
                    if pattern.search(line)), None)
        if hit is None:
            errors.append("missing_or_out_of_order:" + step["name"])
            continue
        matches[step["name"]] = {"line": hit[0] + 1, "text": hit[1]}
        cursor = hit[0] + 1

    for guard in rules.get("forbidden_between", []):
        start, end = guard["start"], guard["end"]
        if start not in names or end not in names:
            raise ValueError("unknown guard boundary")
        if start not in matches or end not in matches:
            continue
        pattern = re.compile(guard["pattern"])
        for i in range(matches[start]["line"], matches[end]["line"] - 1):
            if pattern.search(lines[i]):
                errors.append("forbidden_between:%s:%s:line_%d" %
                              (start, end, i + 1))

    for guard in rules.get("forbidden_same_frame", []):
        begin = re.compile(guard["start_pattern"])
        forbidden = re.compile(guard["forbidden_pattern"])
        starts = [(i + 1, m.group("frame"))
                  for i, line in enumerate(lines)
                  for m in [begin.search(line)] if m]
        if not starts:
            errors.append("missing_frame_anchor:" + guard.get("name", "guard"))
            continue
        for line_no, frame in starts:
            for i, line in enumerate(lines):
                m = forbidden.search(line)
                if m and m.group("frame") == frame:
                    errors.append("same_frame_leak:%s:frame_%s:line_%d" %
                                  (guard.get("name", "guard"), frame, i + 1))

    # Compare captured numeric fields across ordered runtime steps. Useful for
    # orientation changes, inventory counters, health deltas and placement
    # counts without hardcoding a particular game or log format.
    for check in rules.get("numeric_comparisons", []):
        left, right = check["left"], check["right"]
        op = check["op"]
        if op not in ("eq", "ne", "lt", "le", "gt", "ge"):
            raise ValueError("unsupported numeric comparison operator: " + op)
        if left["step"] not in names or right["step"] not in names:
            raise ValueError("unknown numeric comparison step")
        if left["step"] not in matches or right["step"] not in matches:
            continue

        def value(spec):
            step = next(s for s in steps if s["name"] == spec["step"])
            line = matches[spec["step"]]["text"]
            found = re.search(step["pattern"], line)
            if found is None or spec["group"] not in found.groupdict():
                raise ValueError("missing named capture: " + spec["group"])
            try:
                result = float(found.group(spec["group"]))
            except (TypeError, ValueError):
                raise ValueError("non-numeric capture: " + spec["group"])
            if not math.isfinite(result):
                raise ValueError("nonfinite capture: " + spec["group"])
            return result

        a, b = value(left), value(right)
        valid = {"eq": a == b, "ne": a != b, "lt": a < b,
                 "le": a <= b, "gt": a > b, "ge": a >= b}[op]
        if not valid:
            errors.append("numeric_comparison_failed:%s:%s:%s" %
                          (left["step"], op, right["step"]))

    return {"ok": not errors, "observed_lines": len(lines),
            "matched_steps": matches, "errors": errors,
            "source": "supplied runtime log; authenticity not inferred"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("--rules", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = audit(args.log.read_text(encoding="utf8", errors="replace"),
                   json.loads(args.rules.read_text(encoding="utf8")))
    rendered = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf8")
    print(rendered, end="")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
