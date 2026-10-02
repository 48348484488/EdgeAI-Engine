# Revisão da alteração

Revisão local, não avaliação independente por outro agente. Foram inspecionados os contratos de refresh/snapshot, ranking, orçamento de índice, fonte como UTF-8, limites de entrada e preservação de pesos.

Correções reproduzidas com testes antes do fechamento:
- Banner desatualizado após alterar a versão.
- Overflow de consulta com CR na borda de truncamento.
- Snapshot inicial do CLI em lote podia ficar antigo antes de chegar a primeira pergunta.

Limites mantidos explícitos: leitura integral em cada consulta, cache somente em RAM, snapshot não transacional, exclusões lexicais não detectam todos os segredos, compilação/teste apenas Linux, sem qualidade neural nova, sem medição de energia.
