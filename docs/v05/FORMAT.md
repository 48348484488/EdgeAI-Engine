# EDGEAI5 — Transformer de janela limitada

Inteiros little-endian, floats IEEE754 FP32. Host big-endian é rejeitado explicitamente.
Formato específico deste backend, não formato universal para qualquer LLM.

Header de 40 bytes, em ordem:
- magic 8 bytes `EDGEAI5\0`;
- versão u32 =5;
- dim, hidden, window, max_generate: quatro u32;
- rope_base: f32;
- embedding_count: u64, exatamente 256*dim.

Depois: embeddings [256,dim] FP32 row-major; sete matrizes tipadas MixedMatrix,
na ordem query, key, value, project [dim,dim], up [hidden,dim], down [dim,hidden],
output [256,dim]. Cada matriz tem bias. Tags e quantização iguais a EDGEAI4,
descritas em ../FORMAT-v0.4.md: 0 FP32, 1 INT8 por linha, 2 ternário 2 bits.
Escalas/bias e embeddings continuam FP32. Não são armazenadas cópias FP32 dos pesos
compactados no runtime. Masters FP32 pertencem ao checkpoint de treino .pt separado.

Dim par 4..2048, hidden 4..8192, window 1..4096, max_generate 1..4096, rope_base
finito >1. Loader rejeita dimensão/payload inconsistente, NaN/Inf, tags/códigos
inválidos, truncamento e bytes extras. Export Python usa substituição atômica.
O save C++ grava diretamente: não usar o mesmo caminho de um arquivo aberto pelo leitor.

Inferência: um bloco causal, RoPE, janela local circular. Estado KV = 2*window*dim
floats; vetor de scores e temporários são contabilizados à parte. Reset remove o
histórico lógico, mesmo sem zerar o buffer antigo. Limite da implementação para
posição RoPE: reset necessário antes de 2^24 passos; não promete contexto ilimitado.
`loops_used` é 1, não número de bytes gerados; token_score não é confiança em correção.

EDGEAI2/3/4 continuam lidos por seus backends anteriores. Binários antigos não leem
EDGEAI5. O avaliador em lote desta versão suporta EDGEAI3/4/5; EDGEAI2 continua coberto
pelos testes de logits antigos, não pelo novo avaliador em lote.

## EDGBLK1 — blocos de teste nativo

Magic 8 bytes `EDGBLK1\0`; u32 número de blocos. Cada bloco: u32 quantidade N de
alvos seguido de N+1 bytes brutos. Input = bytes[0:N], alvo = bytes[1:N+1]. O estado
reinicia entre blocos. N entre1 e4096, até1 milhão de blocos, payload total até128MiB.
Sem documentos concatenados silenciosamente; truncamento e bytes extras são rejeitados.
Avaliador soma logsumexp em double e publica número de alvos, NLL e acertos.
