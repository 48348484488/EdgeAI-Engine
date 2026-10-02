# Formato EDGEAI3 — contrato binário

Todos os inteiros e números FP32 são little-endian; matrizes row-major. O leitor C++ valida
o arquivo antes de usá-lo. A versão anterior EDGEAI2 continua reconhecida pela factory;
os formatos não são intercambiáveis e o leitor v0.2 não entende EDGEAI3.

## Cabeçalho e pesos, em ordem

1. Magic de 8 bytes: `EDGEAI3\0`.
2. `uint32 version = 3`.
3. Seis uint32: dimensão `dim`, dimensão FFN `hidden`, dimensão de chave `key_dim`,
   janela `window`, profundidade `loops` e limite `max_generate`.
4. Três float32: logits-base de esquecimento, escrita e mistura.
5. Um uint64: quantidade de elementos do embedding, necessariamente `256 * dim`.
6. Embedding: `256 * dim` float32.
7. Seis matrizes ternárias, na ordem query, key, value, project, up e down.
8. Matriz densa de gates: 3 linhas × dim colunas.
9. Matriz densa de saída: 256 linhas × dim colunas.

Matriz ternária: uint32 rows, uint32 cols, uint64 tamanho packed, bytes packed,
`rows` float32 de escala e `rows` float32 de bias.
Quatro códigos por byte, do par menos significativo ao mais significativo:
`00 = 0`, `01 = +1`, `10 = -1`; `11` é inválido. Empacotamento contínuo row-major,
inclusive quando a quantidade de colunas não é múltipla de quatro. Pesos efetivos
por linha são código assinado × escala. Espaço packed = ceil(rows * cols / 4).

Matriz densa: uint32 rows, uint32 cols, `rows * cols` float32 de pesos,
`rows` float32 de bias. Nenhum payload adicional ao final é aceito.
O arquivo não guarda estado de conversa. `reset()` zera estado e buffer de atenção.
Não há mmap: os dados são lidos para memória do processo.

## Equações da memória

Com chave k e consulta q normalizadas, valor v e matriz de estado S:

```text
g = linear_gates(layernorm(embedding(token)))
alpha = sigmoid(decay_logit + g[0])
beta  = sigmoid(write_logit + g[1])
mix   = sigmoid(mix_logit   + g[2])
S = alpha * S
old = transpose(k) * S
S = S + beta * outer(k, v - old)
long_memory = transpose(q) * S
```

Atenção local usa buffer circular limitado, inclui o token atual e nunca tokens futuros.
Memórias local e delta são misturadas por `mix`. O readout repete o mesmo FFN pelo número
fixo de passos treinados, sem modificar novamente a memória temporal. Essa repetição não
é uma garantia de raciocínio adicional nem um critério de confiança calibrada.

Os exportadores em `benchmarks/archive/` são históricos e não devem ser usados para gerar
arquivos do formato final. Use `tools/train_hybrid.py` / `tools/hybrid_model.py`.
