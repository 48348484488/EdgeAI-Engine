"""Real compiler regression: retain the board base across play() branches."""
import importlib.util
from pathlib import Path
import unittest

root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("edgeai_game_memory",root/"tools"/"inspect_tictactoe_memory.py")
game=importlib.util.module_from_spec(spec)
spec.loader.exec_module(game)

class CompiledGameMemoryTests(unittest.TestCase):
    def test_play_read_and_write_use_board_base(self):
        report=game.evaluate()
        play=next(item for item in report["functions"] if item["name"]=="play")
        accesses=[entry for entry in play["accesses"]
                  if entry["board_relation"]=="board_base_dynamic_index"]
        self.assertTrue(any(x["mnemonic"].startswith("ldr") for x in accesses))
        self.assertTrue(any(x["mnemonic"].startswith("str") for x in accesses))
        self.assertTrue(all(x["base_address"]==report["board_symbol_address"] for x in accesses))
        self.assertTrue(all(x["resolved_address"] is None for x in accesses))

if __name__=="__main__":
    unittest.main()
