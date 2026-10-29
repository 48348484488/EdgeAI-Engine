#!/usr/bin/env python3
"""EdgeAI Unity UI provenance analyzer (static, CPU-only, no APK execution).

Input: original decompiled Unity C# event wiring and optional C++ port.
Output: evidence-backed button -> callback -> source effect, with line numbers,
missing native bindings, category IDs, and unsupported/unknown assertions.
Never substitute filename similarity for a verified Unity Sprite PathID.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

BUILD_CONTROLS = (
    "btn_build", "btn_changeButton", "btn_null",
    "btn_fundation", "btn_wall", "btn_stair", "btn_floor",
    "btn_window", "btn_obstacle",
    "btn_opRotate", "btn_opMove", "btn_opRepair",
    "btn_opUp", "btn_opDestory", "btn_lantu",
)

def extract_method(source, name):
    """Return balanced method body and 1-based span, or None."""
    pat = re.compile(r"\b(?:private|public|protected|internal)\s+"
                     r"(?:void|bool|int)\s+" + re.escape(name) +
                     r"\s*\([^)]*\)\s*\{", re.MULTILINE)
    found = pat.search(source)
    if not found:
        return None
    start = found.end() - 1
    depth = 0
    quote = None
    esc = False
    for i in range(start, len(source)):
        char = source[i]
        if quote:
            if esc:
                esc = False
            elif char == "\\":
                esc = True
            elif char == quote:
                quote = None
            continue
        if char in ('"', "'"):
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return (source[start + 1:i],
                        1 + source.count("\n", 0, found.start()),
                        1 + source.count("\n", 0, i))
    raise ValueError("Unbalanced source C# method: " + name)

def audit(source, native=None, original_path="BattlePanel.cs",
          native_path="main.cpp"):
    if "ClickListener.Get" not in source or "FillBuildChildsIcons" not in source:
        raise ValueError("Input lacks source Unity BattlePanel construction code")
    callbacks = {}
    pattern = re.compile(r"ClickListener\.Get\(\s*(btn_\w+)"
                         r"(?:\.gameObject)?\s*,[^;\n]*?\)"
                         r"\s*\.onClick\s*=\s*(\w+)\s*;")
    for match in pattern.finditer(source):
        button, handler = match.group(1, 2)
        # Other UI controls (e.g. btn_head) are deliberately rebound for
        # different target types at runtime. Audit only construction controls;
        # do not treat their unrelated dynamic handlers as ambiguous builds.
        if button not in BUILD_CONTROLS:
            continue
        if button in callbacks and callbacks[button]["callback"] != handler:
            raise ValueError("Ambiguous click wiring: " + button)
        callbacks[button] = {
            "callback": handler, "line": 1 + source.count("\n", 0, match.start())
        }
    controls = []
    for button in BUILD_CONTROLS:
        binding = callbacks.get(button)
        row = {
            "button": button,
            "source_binding": binding,
            "callback": binding["callback"] if binding else None,
            "source_bound": binding is not None,
            "runtime_native_reference": (
                ("LIOS_HUD::Build_" + button) in native if native is not None
                else None
            ),
        }
        if binding:
            body = extract_method(source, binding["callback"])
            if body is None:
                raise ValueError("Wired original Unity handler missing: "
                                 + binding["callback"])
            text, lo, hi = body
            row["handler_lines"] = [lo, hi]
            row["handler_sha256"] = hashlib.sha256(text.encode()).hexdigest()
            cat = re.findall(r"\bFillBuildChildsIcons\(\s*(\d+)\s*\)", text)
            if cat:
                if len(cat) != 1:
                    raise ValueError("Ambiguous category id: " + button)
                row["unity_buildpart_type"] = int(cat[0])
            row["effects"] = sorted(set(re.findall(
                r"\b(?:OnWantEnterBuildState|OnWantExitBuildState|"
                r"WantPlacePrefab|WantRemovePrefab|ChangePrefab|"
                r"SelfRotateAngle|OnceAngle|CFixBuilding|CUpgradeBuilding|"
                r"CRotateBuilding|ChangeMode|ShowBagBuilds|"
                r"CheckBuildChildsClose|FillBuildChildsIcons|"
                r"CurrentAimPart|CurrentPreview)\b", text)))
        controls.append(row)
    wired = [c for c in controls if c["source_bound"]]
    categories = {c["button"]: c["unity_buildpart_type"] for c in controls
                  if "unity_buildpart_type" in c}
    # Source's dynamic submenu cannot be reconstructed from a static list of
    # filename guesses. cfg.BuildPart.icon + GetBasicPartByType(type) decide
    # exact icon and order. Keep missing config visibly unresolved.
    original_submenu = extract_method(source, "FillBuildChildsIcons")
    if original_submenu is None or "GetBasicPartByType(type)" not in original_submenu[0]:
        raise ValueError("Unity m_buildChilds data source not proven")
    required = ("GetBasicPartByType(type)", "View.SetItemSprite(",
                "View.SetLabelText(", "SetActive(false)")
    missing = [x for x in required if x not in original_submenu[0]]
    if missing:
        raise ValueError("Incomplete original dynamic-submenu evidence: "
                         + ", ".join(missing))
    native_issues = []
    if native is not None:
        for control in wired:
            if not control["runtime_native_reference"]:
                native_issues.append({
                    "button": control["button"],
                    "issue": "no_source_rect_reference_in_native_client",
                    "severity": "missing",
                })
        if "saveCurrentBlueprint()" in native and "btn_lantu" in native:
            native_issues.append({
                "button": "btn_lantu",
                "issue": "native_blueprint_save_action_not_proven_by_Unity_click_wiring",
                "severity": "wrong_behavior",
            })
        if "building.orientation=(building.orientation+1)%4" in native:
            native_issues.append({
                "button": "btn_opRotate",
                "issue": "native_rotation_90_degrees_ignores_unity_BuildPart_OnceAngle",
                "severity": "wrong_behavior",
            })
    return {
        "schema": "edgeai.unity-ui-evidence.v1",
        "analysis": "static-source-provenance_only",
        "original": original_path,
        "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "native": native_path if native is not None else None,
        "native_sha256": hashlib.sha256(native.encode()).hexdigest()
                         if native is not None else None,
        "controls": controls,
        "original_callbacks_verified": len(wired),
        "source_category_types": categories,
        "original_submenu_data_source": {
            "method": "FillBuildChildsIcons",
            "span": original_submenu[1:],
            "lookup": "BuildManager.GetBasicPartByType(type)",
            "sprite": "BuildPart.icon",
            "label": "BuildPart.name",
            "order": "source_config_order",
        },
        "unbound_buttons": [c["button"] for c in controls if not c["source_bound"]],
        "native_issues": native_issues,
        "fidelity_proven": False,
        "limitations": [
            "Decompiled C# is static evidence, not a runtime screen recording.",
            "No extraction of BuildPart.oc table; dynamic submenu item count, "
            "icon mapping and model selection remain unproven.",
            "Native references are static signals, not behavioral equivalence.",
            "No UI screenshot pixel parity or Android touch test performed.",
        ],
    }

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--native", type=Path)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--require-original-controls", action="store_true")
    args = ap.parse_args()
    original = args.source.read_text(encoding="utf-8")
    native = args.native.read_text(encoding="utf-8") if args.native else None
    report = audit(original, native, str(args.source), str(args.native)
                   if args.native else "")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False)+"\n",
                           encoding="utf-8")
    if args.require_original_controls:
        expected = ("btn_build", "btn_changeButton", "btn_null", "btn_wall",
                    "btn_fundation", "btn_stair", "btn_floor",
                    "btn_window", "btn_obstacle", "btn_opRotate",
                    "btn_opMove", "btn_opRepair", "btn_opUp",
                    "btn_opDestory")
        absent = [x for x in expected if x in report["unbound_buttons"]]
        if absent:
            raise SystemExit("Original callbacks missing: " + repr(absent))
    print("EDGEAI_UNITY_BUILD_HUD_AUDIT_PASS",
          "original_handlers="+str(report["original_callbacks_verified"]),
          "native_issues="+str(len(report["native_issues"])),
          "missing_source="+str(len(report["unbound_buttons"])), flush=True)

if __name__ == "__main__":
    main()
