# v0.5 — comparação por custo e execução de metas

- Transformer causal de uma camada, RoPE e ring KV nativos, formato EDGEAI5.
- FP32/INT8 no baseline; híbrido anterior e formatos EDGEAI2/3/4 preservados.
- Corpus de código/docs congelado, split por família de arquivos, hashes e exclusão
  de blocos copiados literalmente da referência de treino/validação.
- 15 treinos de atualizações fixas; follow-up explícito com 6 treinos por CPU.
- Avaliação nativa de todos os checkpoints e testes de paridade integrais.
- Executor local de metas, perfis quick/research, logs/status e retomada validada.
- UTF-8 de exibição sanitizado sem alterar bytes enviados de volta ao modelo.
- Correção do contador de loops do Transformer e banner da versão.
- Sem alegações de IA avançada, superioridade a Claude ou energia não medida.

# v0.4

- Added typed EDGEAI4 projection/output storage: FP32, per-row symmetric INT8 W8A32,
  packed ternary. EDGEAI2/3 reading retained.
- Added native Int8Matrix and MixedMatrix; scalar and runtime-dispatched AVX2 INT8
  matvec without retaining a full dequantized matrix.
- Added MixedHybrid, six policies, explicit output precision, atomic typed exporter,
  and a CPU-only educational trainer. Existing hybrid equations unchanged.
- Added controlled matched-initialization/data ablations, near-parameter-matched
  Transformer, longer recall stress set and separate frozen output-head PTQ.
- Added matrix/model validation tests, malformed dtype cases, Python/C++ parity
  for each precision combination, portable and sanitizer coverage.
- Added native process CPU timing and strict token/kernel argument validation.
- Preserved prior results and legacy demonstration models. No general intelligence,
  energy advantage or speedup against FP32 has been demonstrated by this release.

## 0.6.0
- Native reversible byte BPE and embedded tokenizer in EDGEAI6; old formats preserved.
- Variable vocabulary in Python training and C++ Transformer inference.
- Frozen independently authored CPython module corpus with licenses and hashes.
- Near-duplicate filtering, train-only tokenizer reproduction and equal-CPU trials.
- Same-raw-byte native evaluation, trained parity and explicit utility diagnostics.
- Independent goal profiles, host-aware artifact reuse, nonfinite activation rejection.
