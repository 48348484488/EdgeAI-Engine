"""Selective weight precision for the existing hybrid equations.

Training uses FP32 master weights and straight-through quantization. INT8 is
symmetric per output row; activations, memory state, embedding and gates are FP32.
No algorithmic change to HybridTiny.forward is made here.
"""
import os
import tempfile
from pathlib import Path
import torch
from torch import nn
from torch.nn import functional as F
from hybrid_model import HybridTiny, BitLinear
from train_tiny import write_ternary, write_dense, write_floats, w_u32, w_u64, w_f32

CORE_NAMES = ('query', 'key', 'value', 'project', 'up', 'down')
POLICIES = {
    'fp32': ('fp32',)*6,
    'ternary': ('ternary',)*6,
    'qk_fp32': ('fp32','fp32','ternary','ternary','ternary','ternary'),
    'memory_fp32': ('fp32','fp32','fp32','fp32','ternary','ternary'),
    'memory_int8': ('int8','int8','int8','int8','ternary','ternary'),
    'int8': ('int8',)*6,
}
DTYPES = {'fp32': 0, 'int8': 1, 'ternary': 2}

class Int8Linear(nn.Linear):
    def quantized(self):
        weight = self.weight.detach()
        scale = weight.abs().amax(1, keepdim=True).clamp_min(1e-8) / 127
        codes = (weight / scale).round().clamp(-127, 127).to(torch.int8)
        return codes, scale
    def effective(self):
        codes, scale = self.quantized()
        quantized = codes.to(self.weight.dtype) * scale
        return self.weight + (quantized - self.weight).detach()
    def forward(self, x):
        return F.linear(x, self.effective(), self.bias)

def replace_linear(source, precision):
    if precision == 'fp32':
        return source
    cls = {'int8': Int8Linear, 'ternary': BitLinear}.get(precision)
    if cls is None:
        raise ValueError('unsupported precision: ' + str(precision))
    # Constructing a quantized layer must not alter the global random stream.
    with torch.random.fork_rng(devices=[]):
        target = cls(source.in_features, source.out_features, bias=source.bias is not None)
    target.load_state_dict(source.state_dict())
    return target

class MixedHybrid(HybridTiny):
    def __init__(self, dim=32, hidden=64, key_dim=16, window=16, loops=1,
                 policy='memory_int8', output_precision='fp32'):
        if policy not in POLICIES or output_precision not in DTYPES:
            raise ValueError('unknown precision policy/output precision')
        super().__init__(dim, hidden, key_dim, window, loops,
                         ternary=False, adaptive_gates=True)
        self.policy, self.output_precision = policy, output_precision
        for name, precision in zip(CORE_NAMES, POLICIES[policy]):
            setattr(self, name, replace_linear(getattr(self, name), precision))
        self.out = replace_linear(self.out, output_precision)
    def export_config(self):
        return dict(dim=self.dim, hidden=self.hidden, key_dim=self.key_dim,
                    window=self.window, loops=self.loops, policy=self.policy,
                    output_precision=self.output_precision)

def layer_precision(layer):
    return 'int8' if isinstance(layer, Int8Linear) else 'ternary' if isinstance(layer, BitLinear) else 'fp32'

def layer_payload_bytes(layer):
    count, rows = layer.weight.numel(), layer.out_features
    kind = layer_precision(layer)
    if kind == 'fp32':
        return (count + rows)*4
    return (count if kind == 'int8' else (count+3)//4) + rows*8

def numeric_weight_bytes(model):
    return model.emb.weight.numel()*4 + 12 + sum(layer_payload_bytes(getattr(model, name))
             for name in CORE_NAMES + ('gates', 'out'))

def write_mixed(f, layer):
    kind = layer_precision(layer)
    w_u32(f, DTYPES[kind])
    if kind == 'fp32':
        write_dense(f, layer)
    elif kind == 'ternary':
        write_ternary(f, layer)
    else:
        codes, scale = layer.quantized()
        w_u32(f, layer.out_features); w_u32(f, layer.in_features)
        w_u64(f, codes.numel())
        f.write(codes.cpu().numpy().tobytes())
        write_floats(f, scale)
        write_floats(f, layer.bias)

def export_mixed(model, path, max_generate=96):
    if not isinstance(model, MixedHybrid) or not model.adaptive_gates:
        raise ValueError('export requires MixedHybrid with adaptive gates')
    if not 1 <= max_generate <= 4096:
        raise ValueError('max_generate outside [1,4096]')
    for name, p in model.named_parameters():
        if p.dtype != torch.float32 or p.device.type != 'cpu' or not torch.isfinite(p).all():
            raise ValueError('export requires finite CPU FP32 master weights: ' + name)
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
            tmp = Path(f.name)
            f.write(b'EDGEAI4\0'); w_u32(f, 4)
            for n in (model.dim, model.hidden, model.key_dim, model.window, model.loops, max_generate):
                w_u32(f, n)
            for gate in (model.decay_logit, model.write_logit, model.mix_logit):
                w_f32(f, gate.detach().item())
            w_u64(f, model.emb.weight.numel()); write_floats(f, model.emb.weight)
            for name in CORE_NAMES:
                write_mixed(f, getattr(model, name))
            write_dense(f, model.gates)
            write_mixed(f, model.out)
        os.replace(tmp, path)
    finally:
        if tmp is not None and tmp.exists():
            tmp.unlink()
