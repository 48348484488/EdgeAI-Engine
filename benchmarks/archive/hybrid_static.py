"""EDGEAI3 reference equations. CPU training only; native inference is in C++.
This is a compact experimental delta-memory/local-attention model, not GatedDeltaNet.
"""
import math
import struct
from pathlib import Path
import torch
from torch import nn
from torch.nn import functional as F
from train_tiny import write_ternary, write_dense, write_floats, w_u32, w_u64, w_f32

class BitLinear(nn.Linear):
    def effective(self):
        centered = self.weight - self.weight.mean(1, keepdim=True)
        scale = centered.abs().mean(1, keepdim=True).clamp_min(1e-5)
        quantized = (centered / scale).round().clamp(-1, 1) * scale
        return centered + (quantized - centered).detach()
    def forward(self, x):
        return F.linear(x, self.effective(), self.bias)

class HybridTiny(nn.Module):
    def __init__(self, dim=32, hidden=64, key_dim=16, window=16, loops=1, ternary=True):
        super().__init__()
        if not (4 <= dim <= 2048 and 4 <= hidden <= 8192 and 1 <= key_dim <= 256 and 1 <= window <= 4096 and 1 <= loops <= 16):
            raise ValueError("invalid model configuration")
        self.dim, self.hidden, self.key_dim, self.window, self.loops = dim, hidden, key_dim, window, loops
        self.ternary = ternary
        linear = BitLinear if ternary else nn.Linear
        self.emb = nn.Embedding(256, dim)
        self.query, self.key = linear(dim, key_dim), linear(dim, key_dim)
        self.value, self.project = linear(dim, dim), linear(dim, dim)
        self.up, self.down = linear(dim, hidden), linear(hidden, dim)
        self.out = nn.Linear(dim, 256)
        self.decay_logit = nn.Parameter(torch.tensor(4.0))
        self.write_logit = nn.Parameter(torch.tensor(1.0))
        self.mix_logit = nn.Parameter(torch.tensor(0.0))

    def forward(self, tokens, memory_mode="hybrid"):
        if tokens.ndim != 2 or tokens.shape[1] == 0:
            raise ValueError("expected nonempty [batch, sequence] tokens")
        batch, length = tokens.shape
        e = self.emb(tokens)
        n = F.layer_norm(e, (self.dim,), eps=1e-5)
        q = F.normalize(self.query(n), dim=-1, eps=1e-6)
        k = F.normalize(self.key(n), dim=-1, eps=1e-6)
        v = self.value(n)
        state = torch.zeros(batch, self.key_dim, self.dim, device=e.device, dtype=e.dtype)
        a, beta, gate = self.decay_logit.sigmoid(), self.write_logit.sigmoid(), self.mix_logit.sigmoid()
        history = []
        for t in range(length):
            state = a * state
            predicted = torch.einsum("bk,bkd->bd", k[:, t], state)
            state = state + beta * k[:, t, :, None] * (v[:, t] - predicted)[:, None, :]
            history.append(torch.einsum("bk,bkd->bd", q[:, t], state))
        long = torch.stack(history, 1)
        # Full training tensor for short sequences; native inference uses a fixed ring.
        positions = torch.arange(length, device=e.device)
        distance = positions[:, None] - positions[None, :]
        mask = (distance < 0) | (distance >= self.window)
        scores = (q @ k.transpose(-1, -2)) * math.sqrt(self.key_dim)
        near = scores.masked_fill(mask, float("-inf")).softmax(-1) @ v
        if memory_mode == "delta":
            mix = long
        elif memory_mode == "local":
            mix = near
        elif memory_mode == "hybrid":
            mix = gate * long + (1 - gate) * near
        else:
            raise ValueError("unknown memory_mode")
        h = e + self.project(mix)
        for _ in range(self.loops):
            h = h + 0.5 * self.down(F.silu(self.up(F.layer_norm(h, (self.dim,), eps=1e-5))))
        return self.out(F.layer_norm(h, (self.dim,), eps=1e-5))

def export(model, path, max_generate=96):
    if not model.ternary:
        raise ValueError("FP32 ablation cannot be exported to ternary without a separate evaluation")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        f.write(b"EDGEAI3\0")
        w_u32(f, 3)
        for n in (model.dim, model.hidden, model.key_dim, model.window, model.loops, max_generate):
            w_u32(f, n)
        for g in (model.decay_logit, model.write_logit, model.mix_logit):
            w_f32(f, g.detach().item())
        w_u64(f, model.emb.weight.numel())
        write_floats(f, model.emb.weight)
        for layer in (model.query, model.key, model.value, model.project, model.up, model.down):
            write_ternary(f, layer)
        write_dense(f, model.out)
