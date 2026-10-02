import math
import sys
import unittest
from pathlib import Path

import torch
from torch.nn import functional as F

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from transformer_model import TinyTransformer, numeric_weight_bytes


class MultiBlockTransformerTests(unittest.TestCase):
    def test_two_blocks_have_independent_parameters(self):
        model = TinyTransformer(dim=8, hidden=12, window=4, precision="fp32", blocks=2)
        self.assertEqual(model.export_config()["blocks"], 2)
        self.assertEqual(len(model.blocks), 2)
        self.assertIsNot(model.blocks[0].query.weight, model.blocks[1].query.weight)
        x = torch.tensor([[1, 2, 3, 4]], dtype=torch.long)
        self.assertEqual(tuple(model(x).shape), (1, 4, 256))

    def test_block_count_rejects_zero_and_nine(self):
        with self.assertRaises(ValueError):
            TinyTransformer(dim=8, hidden=12, window=4, blocks=0)
        with self.assertRaises(ValueError):
            TinyTransformer(dim=8, hidden=12, window=4, blocks=9)

    def test_one_block_forward_matches_legacy_equations(self):
        torch.manual_seed(123)
        model = TinyTransformer(dim=8, hidden=12, window=4, precision="fp32", blocks=1)
        x = torch.tensor([[7, 8, 9, 10]], dtype=torch.long)
        actual = model(x)

        e = model.emb(x)
        n = F.layer_norm(e, (model.dim,), eps=1e-5)
        q, k = model.rotate(model.query(n)), model.rotate(model.key(n))
        v = model.value(n)
        t = torch.arange(x.shape[1], device=x.device)
        distance = t[:, None] - t[None, :]
        scores = q @ k.transpose(-1, -2) / math.sqrt(model.dim)
        weights = scores.masked_fill(
            (distance < 0) | (distance >= model.window), float("-inf")
        ).softmax(-1)
        h = e + model.project(weights @ v)
        h = h + 0.5 * model.down(
            F.silu(model.up(F.layer_norm(h, (model.dim,), eps=1e-5)))
        )
        expected = model.out(F.layer_norm(h, (model.dim,), eps=1e-5))

        torch.testing.assert_close(actual, expected, rtol=0, atol=0)

    def test_numeric_weight_bytes_counts_all_blocks(self):
        one = TinyTransformer(dim=8, hidden=12, window=4, precision="fp32", blocks=1)
        two = TinyTransformer(dim=8, hidden=12, window=4, precision="fp32", blocks=2)
        extra = sum(
            layer.weight.numel() * 4 + layer.bias.numel() * 4
            for layer in (
                two.blocks[1].query,
                two.blocks[1].key,
                two.blocks[1].value,
                two.blocks[1].project,
                two.blocks[1].up,
                two.blocks[1].down,
            )
        )
        self.assertEqual(numeric_weight_bytes(two) - numeric_weight_bytes(one), extra)


if __name__ == "__main__":
    unittest.main()
