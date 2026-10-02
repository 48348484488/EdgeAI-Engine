# EDGEAI4 mixed-precision file format

All integer/floating fields are little-endian. Floats are IEEE754 float32.
No Python object/pickle is in `.edge`. PyTorch `.pt` checkpoints are separate files.
Native runtime still reads legacy EDGEAI2 and EDGEAI3; saving HybridModel emits EDGEAI4.

Header (56 bytes):
- magic: 8 bytes `EDGEAI4\0`
- version: u32 = 4
- six u32: dim, hidden, key_dim, window, loops, max_generate
- three f32: global decay/write/mix logits
- embedding element count: u64, must equal 256 * dim

Followed by embedding float32 values, row-major [256,dim]. Then six **typed matrices**:
query [key_dim,dim], key [key_dim,dim], value [dim,dim], project [dim,dim],
up [hidden,dim], down [dim,hidden]. Then a **plain dense matrix** gates [3,dim],
then one **typed matrix** output [256,dim]. No trailing payload permitted.

A typed matrix starts with a u32 tag:
- 0: dense FP32. u32 rows, u32 cols, rows*cols f32 weights, rows f32 bias.
- 1: INT8 W8A32. u32 rows, u32 cols, u64 payload bytes (=rows*cols), signed i8 weights,
  rows f32 scales, rows f32 bias. Codes in [-127,127]; -128 is rejected.
  Scales must be positive finite, with finite 127*scale. Zero rows use positive epsilon scale.
- 2: packed ternary. u32 rows, u32 cols, u64 payload bytes (=ceil(rows*cols/4)),
  packed bytes, rows f32 scales, rows f32 bias. 00=0, 01=+1, 10=-1; 11 rejected.
  Flatten all rows before packing; odd columns are supported by the portable path.

Quantization: INT8 row scale = max(abs(row), 1e-8)/127, zero point 0, round-to-even,
clip [-127,127]. Effective weight = signed code * row scale. Ternary quantization
retains the v0.3 convention: subtract row mean, scale=mean(abs(centered row)) clamped
to 1e-5, round and clip [-1,1]. Bias is never quantized. Ternary and INT8 therefore
have different centering policies; comparisons are not a pure bit-count intervention.

Inference: inputs, intermediate values, recurrent state, accumulation and bias are FP32.
INT8 matrix-vector kernels unpack/convert a small block on demand; no full FP32 copy
of INT8 weights is cached. Runtime dispatch chooses AVX2 on compatible x86 GCC/Clang,
or scalar. Explicit lookup2 is a ternary kernel and falls back to scalar for FP32/INT8.

Matrix numeric byte accounting excludes dimensions/tags. `weight_bytes()` includes
all numeric embedding/core/gates/output/scales/global gates. This is not process RSS.
Loader limits tensor dimensions/elements via Binary.hpp and checks file lengths before
allocation. It rejects unknown tags, inconsistent shapes, NaN/Inf parameters, forbidden
codes, bad scales, truncation and trailing payload. Host must be little-endian.
