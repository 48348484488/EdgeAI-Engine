#!/usr/bin/env python3
"""Validate runtime UI ownership from event logs; no original-game parity claims."""
import json
import re
import sys
from pathlib import Path


def audit(log, spec):
    """Check ordered runtime markers; never infer original-game parity."""
    markers = {}
    for name, pair in spec["panels"].items():
        markers[pair["open"]] = ("open", name)
        markers[pair["close"]] = ("close", name)
    for marker in spec["gameplay"]:
        markers[marker] = ("gameplay", None)
    capture = spec.get("capture")
    if capture:
        markers[capture] = ("capture", None)
    expected = 2 * len(spec["panels"]) + len(spec["gameplay"]) + bool(capture)
    if len(markers) != expected:
        raise ValueError("duplicate markers")
    touch_rule = spec.get("touch_down")
    touch_pattern = None
    allowed = set()
    if touch_rule is not None:
        if not isinstance(touch_rule.get("prefix"), str) or not touch_rule["prefix"]:
            raise ValueError("touch_down.prefix must be a nonempty string")
        touch_pattern = re.compile(touch_rule.get("action_regex", r"\baction=(\d+)\b"))
        if touch_pattern.groups != 1:
            raise ValueError("touch_down.action_regex requires one capture group")
        allowed = set(touch_rule.get("allowed_during_modal", [0]))
        if any(type(value) is not int for value in allowed):
            raise ValueError("touch action ids must be integers")
    active, pending = None, False
    violations = []
    opens = 0
    modal_touches = 0
    for line_no, line in enumerate(log.splitlines(), 1):
        if active is not None and touch_rule is not None and touch_rule["prefix"] in line.split():
            modal_touches += 1
            match = touch_pattern.search(line)
            if match is None:
                violations.append((line_no, "unparseable_modal_touch"))
            elif int(match.group(1)) not in allowed:
                violations.append((line_no, "gameplay_touch_owned_by_modal"))
        events = [value for key, value in markers.items() if key in line.split()]
        if len(events) > 1:
            violations.append((line_no, "ambiguous"))
            continue
        if not events:
            continue
        kind, name = events[0]
        if kind == "open":
            opens += 1
            if active is not None:
                violations.append((line_no, "overlapping"))
            if pending:
                violations.append((line_no, "missing_capture_before_next_open"))
            active, pending = name, bool(capture)
        elif kind == "close":
            if active != name or pending:
                violations.append((line_no, "invalid_close"))
            active, pending = None, False
        elif kind == "capture":
            if active is None:
                violations.append((line_no, "orphan_capture"))
            pending = False
        elif active is not None:
            violations.append((line_no, "gameplay_during_modal"))
    if pending:
        violations.append((len(log.splitlines()), "missing_capture"))
    if not opens:
        raise ValueError("no observed panel opens")
    return {"opens": opens, "modal_touches": modal_touches,
            "violations": violations, "passed": not violations,
            "original_game_parity_proven": False}


def main():
    if len(sys.argv) not in (3, 4):
        raise SystemExit("usage: edgeai_modal_input_audit.py log.txt spec.json [report.json]")
    report = audit(Path(sys.argv[1]).read_text(encoding="utf-8"),
                   json.loads(Path(sys.argv[2]).read_text(encoding="utf-8")))
    payload = json.dumps(report, indent=2) + "\n"
    if len(sys.argv) == 4:
        Path(sys.argv[3]).write_text(payload, encoding="utf-8")
    print(payload, end="")
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
