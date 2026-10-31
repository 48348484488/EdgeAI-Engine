#!/usr/bin/env python3
"""Generic logcat startup-stage audit for graphics/game engines.

A stage manifest is a list of ordered regex markers. Missing stages are
reported as unverified; a live PID alone never proves a rendered frame.
"""
import argparse
import datetime as dt
import json
import re
from pathlib import Path

STAMP = re.compile(r"^(\d\d)-(\d\d) (\d\d):(\d\d):(\d\d)\.(\d{3})")


def timestamp(line):
    match = STAMP.match(line)
    if not match:
        return None
    mo, day, hour, minute, second, millis = map(int, match.groups())
    try:
        return dt.datetime(2000, mo, day, hour, minute, second, millis * 1000)
    except ValueError:
        return None


def audit(log, spec):
    stages = spec.get("stages")
    if not isinstance(stages, list) or not stages:
        raise ValueError("stages must be a nonempty list")
    names = []
    patterns = []
    for stage in stages:
        if not isinstance(stage, dict) or not isinstance(stage.get("name"), str) or not stage["name"]:
            raise ValueError("each stage needs a nonempty name")
        names.append(stage["name"])
        patterns.append(re.compile(stage["pattern"]))
    if len(names) != len(set(names)):
        raise ValueError("stage names must be unique")
    found = []
    skipped_optional = []
    cursor = 0
    last_log_time = None
    for lineno, line in enumerate(log.splitlines(), 1):
        stamp = timestamp(line)
        if stamp is not None:
            last_log_time = stamp
        for index in range(cursor, len(patterns)):
            if not all(bool(stages[k].get("optional", False)) for k in range(cursor, index)):
                break
            if patterns[index].search(line):
                skipped_optional.extend(names[k] for k in range(cursor, index))
                found.append({"name": names[index], "line": lineno,
                              "timestamp": stamp.isoformat(timespec="milliseconds") if stamp else None})
                cursor = index + 1
                break
    next_required = next((names[i] for i in range(cursor, len(stages))
                          if not stages[i].get("optional", False)), None)
    skipped_optional.extend(names[i] for i in range(cursor, len(stages))
                            if stages[i].get("optional", False))
    complete = next_required is None
    last_time = dt.datetime.fromisoformat(found[-1]["timestamp"]) if found and found[-1]["timestamp"] else None
    age = (last_log_time - last_time).total_seconds() if last_time and last_log_time else None
    return {"status": "complete" if complete else "incomplete",
            "matched_stages": found, "expected_stages": len(stages),
            "last_stage": found[-1]["name"] if found else None,
            "next_stage": next_required,
            "skipped_optional_stages": skipped_optional,
            "seconds_since_last_stage": round(max(0, age), 3) if age is not None else None,
            "render_verified": complete,
            "warning": None if complete else "No proof of final render stage"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--logcat", type=Path, required=True)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = audit(args.logcat.read_text(errors="replace"), json.loads(args.spec.read_text()))
    output = json.dumps(result, indent=2) + "\n"
    if args.report:
        args.report.write_text(output)
    print(output, end="")
    raise SystemExit(0 if result["status"] == "complete" else 2)


if __name__ == "__main__":
    main()
