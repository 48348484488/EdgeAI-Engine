#!/usr/bin/env python3
"""Validate runtime UI ownership from event logs; no original-game parity claims."""
import json
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
    active, pending = None, False
    violations = []
    opens = 0
    for line_no, line in enumerate(log.splitlines(), 1):
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
    return {"opens": opens, "violations": violations,
            "passed": not violations, "original_game_parity_proven": False}
