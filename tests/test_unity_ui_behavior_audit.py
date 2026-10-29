#!/usr/bin/env python3
"""Regression tests for EdgeAI source-provenance Unity UI analyzer."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
try:
    from edgeai_unity_ui_behavior_audit import audit, extract_method
except ModuleNotFoundError:
    from unity_ui_behavior_audit import audit, extract_method

ORIGINAL = """
public class BattlePanel {
  private void Init() {
    ClickListener.Get(btn_wall.gameObject, string.Empty).onClick = OnClickWall;
    ClickListener.Get(btn_build, string.Empty).onClick = OnClickBuild;
    ClickListener.Get(btn_null, string.Empty).onClick = OnClickBagAdd;
    ClickListener.Get(btn_opRotate, string.Empty).onClick = OnClickOpRotate;
  }
  private void OnClickWall(GameObject go) {
    CheckBuildChildsClose(go);
    FillBuildChildsIcons(3);
  }
  private void OnClickBuild(GameObject go) { WantPlacePrefab(); }
  private void OnClickBagAdd(GameObject go) { ShowBagBuilds(); }
  private void OnClickOpRotate(GameObject go) {
    if (CurrentPreview != null) { SelfRotateAngle += OnceAngle; }
  }
  private void FillBuildChildsIcons(int type) {
    var parts = GetBasicPartByType(type);
    View.SetItemSprite(cell.m_icon, p.icon);
    View.SetLabelText(cell.txt_nameText, p.name);
    cell.gameObject.SetActive(false);
  }
}
"""
class TestUnityBehaviorAudit(unittest.TestCase):
    def test_provenance_and_category(self):
        r = audit(ORIGINAL, 'LIOS_HUD::Build_btn_wall;')
        self.assertEqual(r["source_category_types"]["btn_wall"], 3)
        self.assertEqual(r["original_callbacks_verified"], 4)
        self.assertIn("btn_lantu", r["unbound_buttons"])
        self.assertFalse(r["fidelity_proven"])
        self.assertEqual(r["original_submenu_data_source"]["sprite"], "BuildPart.icon")
        self.assertTrue(any(i["button"]=="btn_build" for i in r["native_issues"]))
        self.assertFalse(any(i["button"]=="btn_wall" for i in r["native_issues"]))
    def test_method_nesting_and_braces_in_string(self):
        src='private void Foo() { if(true) { var x="}"; } return; }'
        self.assertIn('return;', extract_method(src,'Foo')[0])
    def test_missing_source_rejected(self):
        with self.assertRaises(ValueError):
            audit("public class Nothing {}")
    def test_missing_handler_rejected(self):
        with self.assertRaises(ValueError):
            audit(ORIGINAL.replace("private void OnClickWall", "private void Different"))
    def test_fake_blueprint_and_rotation_detected(self):
        r=audit(ORIGINAL,'btn_lantu; saveCurrentBlueprint(); '
                'building.orientation=(building.orientation+1)%4;')
        issues={i["issue"] for i in r["native_issues"]}
        self.assertIn("native_blueprint_save_action_not_proven_by_Unity_click_wiring",issues)
        self.assertIn("native_rotation_90_degrees_ignores_unity_BuildPart_OnceAngle",issues)
if __name__ == "__main__":
    unittest.main()
