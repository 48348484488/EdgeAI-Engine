# Implementação v0.5

**Objetivo:** ciclo reproduzível de treino/comparação em texto e código, CPU-only.
**Spec:** docs/v05/DESIGN.md. **Execução:** inline, sem confirmações intermediárias.

- [x] 1. Base: compilar ZIP v0.4 e testar. Guardar logs e hash de origem.
- [x] 2. Testes antes do código: Transformer causal (prefixo invariável ao futuro),
  reset, ring wrap, arquivo truncado, configuração inválida, todas as precisões;
  corpus: hashes, splits disjuntos, blocos fora de fronteira proibidos;
  perdas contadas por byte (não média simples por arquivo).
- [x] 3. Backend: tools/transformer_model.py, TransformerModel.hpp/.cpp,
  TransformerBackend.hpp/.cpp; formato EDGEAI5, dispatch em chat/logits/inspect/runtime.
  CTest transforma um demo, serializa, recarrega e compara saídas.
- [x] 4. Dados/treino: tools/language_data.py e benchmarks/language_v05.py,
  corpus congelado, métricas e checkpoints de todas as variantes/seeds.
  tools/evaluate.cpp avalia mesmo bloco em C++ (logsumexp double).
- [x] 5. tools/verify_language.py: comparar todas as saídas e métricas Python/C++.
  benchmarks/native_v05.py: tempo intercalado, hash dos modelos e RSS.
- [x] 6. tools/run_goals.py: subprocessos sem shell, JSON de progresso, logs,
  limites explícitos e retomada por identidade/hashes. Testar cache invalidado.
- [x] 7. Release/portable/ASan+UBSan, Python, arquivo extraído limpo.
  Relatório real, metas cumpridas/pendentes, ZIP e SHA256.
