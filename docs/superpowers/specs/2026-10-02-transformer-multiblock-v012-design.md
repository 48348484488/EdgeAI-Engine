# EdgeAI Engine v0.12 — Transformer multi-bloco

Data: 2026-10-02

## Objetivo

Adicionar suporte real a Transformers com mais de um bloco no EdgeAI, do treinamento Python ao runtime C++, sem quebrar os modelos `EDGEAI5/6/7` existentes.

A primeira utilização será um experimento controlado de **1 bloco vs. 2 blocos**. O objetivo não é provar "inteligência geral", e sim medir se um segundo bloco melhora a capacidade neural o bastante para justificar custo extra de CPU, memória e tamanho do modelo.

## Escopo

A v0.12 deve entregar:

1. arquitetura Python com número configurável de blocos;
2. novo formato nativo multi-bloco;
3. carregamento e inferência multi-bloco em C++;
4. compatibilidade de leitura com `EDGEAI5`, `EDGEAI6` e `EDGEAI7`;
5. paridade numérica Python/C++ para 1 e 2 blocos;
6. benchmark 1×2 blocos com dados, seeds e orçamento de CPU equivalentes;
7. relatório de qualidade, parâmetros, bytes, latência e memória.

Fora do escopo: multi-head attention, MoE, GPU, novo tokenizer, aumento do dataset ou comparação com modelos comerciais.

## Modelo

### Bloco

Cada bloco mantém a estrutura já usada pelo Transformer atual:

- LayerNorm sem parâmetros;
- Q, K, V;
- RoPE;
- atenção causal em janela;
- projeção da atenção;
- residual;
- LayerNorm;
- MLP `up -> SiLU -> down`;
- residual com fator 0,5.

O embedding é compartilhado antes do primeiro bloco. O `output` é compartilhado e aplicado somente após o último bloco.

### Estruturas C++

`TransformerModel` passa a representar:

- configuração global;
- tokenizer;
- embedding;
- `std::vector<TransformerBlock>`;
- matriz `output`.

`TransformerBlock` contém:

- `query`;
- `key`;
- `value`;
- `project`;
- `up`;
- `down`.

A configuração ganha `blocks`, com limite inicial **1..8** para impedir modelos acidentalmente gigantes.

## Formato EDGEAI8

Modelos multi-bloco serão escritos como `EDGEAI8`.

Cabeçalho:

1. magic `EDGEAI8\0`;
2. versão `8`;
3. `dim`;
4. `hidden`;
5. `window`;
6. `max_generate`;
7. `rope_base`;
8. `block_count`;
9. `tokenizer_mode`;
10. `merge_count`;
11. pares BPE, quando existirem;
12. embedding;
13. para cada bloco: Q, K, V, project, up, down;
14. output.

`tokenizer_mode`:

- `0`: byte tokenizer;
- `1`: BPE com BOS;
- `2`: BPE de instrução com BOS/EOS/response.

Limites de tamanho e validação continuam obrigatórios antes de alocar payloads.

### Compatibilidade

- `EDGEAI5/6/7` continuam carregando sem conversão manual.
- Ao carregar um formato antigo, o runtime cria internamente **1 bloco**.
- Modelos de 1 bloco existentes não precisam ser reexportados.
- O exportador Python usa `EDGEAI8` quando `blocks > 1`.
- Para `blocks == 1`, o exportador pode continuar usando o formato legado correspondente para preservar paridade histórica.

## Runtime C++

Cada bloco terá cache KV próprio:

`blocks × window × dim × 2 × sizeof(float)`.

O fluxo por token será:

```text
embedding
  ↓
block 0 attention + MLP
  ↓
block 1 attention + MLP
  ↓
...
  ↓
final LayerNorm
  ↓
output head
```

Todos os blocos usam a mesma posição de token para RoPE.

`reset()` limpa posição e uso de todos os caches.

`numeric_working_bytes()` e `state_payload_bytes()` passam a contabilizar todos os blocos.

## Python

`TinyTransformer` ganha `blocks=1`.

Os blocos serão módulos independentes dentro de `nn.ModuleList`. O comportamento de `blocks=1` deve permanecer numericamente compatível com a implementação atual dentro da tolerância já usada nos testes de paridade.

O exportador valida:

- quantidade de blocos;
- shapes;
- precisão de todas as matrizes;
- FP32 finito dos masters;
- vocabulário/tokenizer;
- limite de geração.

## TDD e testes

Antes da implementação, os testes devem falhar ao exigir:

1. criação de modelo com 2 blocos;
2. round-trip `EDGEAI8`;
3. rejeição de `block_count=0` e acima do limite;
4. caches KV independentes por bloco;
5. `reset()` completo;
6. `parameter_count()`, `weight_bytes()` e `state_payload_bytes()` corretos;
7. leitura dos modelos antigos;
8. paridade Python/C++ para 1 e 2 blocos;
9. rejeição de arquivo truncado e payload extra.

A implementação só entra após o RED ser observado.

## Experimento 1 bloco × 2 blocos

### Controle

Usar o conjunto de instruções já congelado no projeto.

Para as duas arquiteturas:

- mesmas divisões train/validation/test;
- mesmo tokenizer;
- mesmos `dim`, `hidden`, `window`;
- mesmas seeds;
- 1 thread;
- mesmo orçamento de **CPU time**, não mesmo número de steps;
- mesma função de perda e política de seleção;
- teste não participa da seleção.

Seeds iniciais: **11, 22 e 33**.

Orçamento inicial: **60 segundos de CPU por arquitetura por seed**, mantendo o protocolo já usado no projeto.

### Métricas

Registrar por arquitetura:

- parâmetros;
- tamanho do `.edge`;
- steps completados no orçamento;
- validation NLL;
- test exact-match por família;
- test exact-match total;
- latência nativa por token;
- pico de RSS quando disponível;
- working bytes e cache bytes calculados;
- energia somente se houver sensor real; caso contrário `null`.

### Critério de decisão

Não escolher 2 blocos apenas porque é maior.

O relatório deve mostrar separadamente:

- ganho de qualidade;
- custo de parâmetros;
- custo de arquivo;
- custo de memória;
- custo de latência.

Se 2 blocos não produzir melhoria consistente nas seeds, o modelo de 1 bloco permanece padrão.

Nenhum resultado será descrito como superioridade sobre ChatGPT, Claude ou "inteligência geral".

## Arquivos esperados

Principais mudanças:

- `tools/transformer_model.py`;
- `include/edgeai/TransformerModel.hpp`;
- `src/TransformerModel.cpp`;
- `include/edgeai/TransformerBackend.hpp`;
- `src/TransformerBackend.cpp`;
- `tests/test_transformer.cpp`;
- testes Python de export/paridade;
- benchmark v0.12;
- `BENCHMARK_RESULTS.md`;
- `README.md`;
- `CHANGELOG.md`;
- versão CMake.

## Critério de conclusão

A v0.12 só pode ser chamada de concluída quando:

- toda a suíte existente continuar verde;
- testes novos multi-bloco estiverem verdes;
- sanitizers e caminho sem SIMD passarem;
- modelos legados continuarem carregando;
- paridade Python/C++ estiver documentada;
- experimento 1×2 tiver resultados reproduzíveis;
- README relatar apenas capacidades e números comprovados.
