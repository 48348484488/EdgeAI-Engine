#!/usr/bin/env python3
"""Generic frame-scoped UI transition/input ownership audit.

Accepts engine logs containing INPUT_TRANSITION and INPUT_DISPATCH markers.
A touch that changes UI modes must not be dispatched into the newly opened
mode during that same frame. This proves only the observed trace invariant;
it does not prove that the intended button was touched or rendered correctly.
"""
import argparse
import json
import re
from pathlib import Path

TRANSITION = re.compile(
    r"(?:^|[^A-Za-z0-9])INPUT_TRANSITION\s+frame=(\d+)\s+from=([A-Za-z0-9_-]+)"
    r"\s+to=([A-Za-z0-9_-]+)\b"
)
DISPATCH = re.compile(
    r"(?:^|[^A-Za-z0-9])INPUT_DISPATCH\s+frame=(\d+)\s+scope=([A-Za-z0-9_-]+)\b"
)


def audit(text: str) -> dict:
    transitions = []
    dispatches = []
    malformed = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if "INPUT_TRANSITION" in line:
            match = TRANSITION.search(line)
            if match is None:
                malformed.append({"line": line_number, "reason": "invalid_transition"})
            else:
                transitions.append({
                    "frame": int(match[1]), "from": match[2],
                    "to": match[3], "line": line_number
                })
        if "INPUT_DISPATCH" in line:
            match = DISPATCH.search(line)
            if match is None:
                malformed.append({"line": line_number, "reason": "invalid_dispatch"})
            else:
                dispatches.append({
                    "frame": int(match[1]), "scope": match[2],
                    "line": line_number
                })
    violations = list(malformed)
    for transition in transitions:
        for dispatch in dispatches:
            if (dispatch["frame"] == transition["frame"] and
                    dispatch["scope"] == transition["to"] and
                    dispatch["line"] > transition["line"]):
                violations.append({
                    "reason": "new_scope_received_transition_frame_touch",
                    "frame": transition["frame"],
                    "scope": transition["to"],
                    "transition_line": transition["line"],
                    "dispatch_line": dispatch["line"]
                })
    return {
        "transition_count": len(transitions),
        "dispatch_count": len(dispatches),
        "violation_count": len(violations),
        "violations": violations,
        "validated": bool(transitions) and bool(dispatches) and not violations,
        "limitation": "Observed input routing only; not visual or original-game parity"
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--require-transition", action="store_true")
    args = parser.parse_args()
    result = audit(args.log.read_text(encoding="utf-8", errors="replace"))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return int(result["violation_count"] > 0 or
               (args.require_transition and result["transition_count"] == 0))


if __name__ == "__main__":
    raise SystemExit(main())
