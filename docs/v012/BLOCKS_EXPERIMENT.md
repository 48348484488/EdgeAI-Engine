# Experimento estrutural v0.12: 1 bloco vs. 2 blocos

Objetivo: verificar se um segundo bloco Transformer melhora a capacidade útil do EdgeAI quando o orçamento de CPU permanece igual.

## Infraestrutura validada

- Python `TinyTransformer`: 1..8 blocos.
- Runtime C++: execução multi-bloco sequencial.
- Formato `EDGEAI8` para modelos multi-bloco.
- `EDGEAI5/6/7` continuam compatíveis como um bloco.
- Cache KV independente por bloco.
- Paridade Python/C++ em scalar e auto, incluindo wrap de janela.

## Fase A — diagnóstico curto teacher-forced

O primeiro diagnóstico usou 12 s de CPU por arquitetura/seed e avaliação teacher-forced. Nesse protocolo, 2 blocos mostrou sinal positivo:

| Medida | 1 bloco | 2 blocos |
|---|---:|---:|
| Mediana NLL de teste | 2,8149 | **2,4919** |
| Acurácia de tokens | 57,27% | **60,20%** |
| Linhas exatas teacher-forced | 106/582 (18,21%) | **122/582 (20,96%)** |

Esse teste fornece o prefixo correto ao prever o próximo token. Portanto, ele não mede sozinho a capacidade de gerar uma resposta completa sem ajuda.

## Fase B — protocolo principal de 60 s + geração nativa

Controle:

- seeds 11, 22 e 33;
- 60 s de process CPU por arquitetura/seed;
- uma thread;
- mesmo dataset `data/instructions_v07`;
- mesmo tokenizer, dimensão, hidden, janela, optimizer, loss e política de seleção;
- checkpoint escolhido por validation NLL;
- testes não usados para seleção;
- avaliação final por `edgeai_generate` C++.

### Resultado por seed

| Seed | Exact 1 bloco | Exact 2 blocos | Val NLL 1 bloco | Val NLL 2 blocos |
|---:|---:|---:|---:|---:|
| 11 | **53/194** | 48/194 | **0,4313** | 0,4892 |
| 22 | 37/194 | **46/194** | 0,4101 | **0,3170** |
| 33 | **57/194** | 44/194 | **0,3104** | 0,4352 |

### Resultado agregado

| Medida | 1 bloco | 2 blocos |
|---|---:|---:|
| Parâmetros | 71.827 | 93.699 |
| `.edge` | 154.400 B | 178.976 B |
| Pesos numéricos | 152.168 B | 176.616 B |
| Estado KV | 24.576 B | 49.152 B |
| Working memory numérica | 29.420 B | 56.300 B |
| Mediana de steps | 11.269 | 6.897 |
| Mediana validation NLL | **0,4101** | 0,4352 |
| Exact generation | **147/582 (25,26%)** | 138/582 (23,71%) |
| Correct generation | **149/582 (25,60%)** | 138/582 (23,71%) |
| EOS | 578/582 | **582/582** |
| Mediana interna por caso | **0,650 ms** | 0,779 ms |
| Mediana externa por caso | **1,863 ms** | 2,040 ms |

2 blocos aumentou parâmetros em 30,45%, arquivo em 15,92%, cache KV em 100% e working memory em 91,37%. No mesmo orçamento, completou cerca de 38,80% menos steps.

**Nota de protocolo:** os artefatos da Fase B em `results/v012/` foram gerados antes da mudança que inicializa blocos adicionais como identidade residual. Eles registram `edge-sft-v012-blocks-1`. O HEAD atual versiona a inicialização por identidade; portanto, rerodar o comando da Fase B no código atual é um novo ensaio, não uma reprodução bit a bit dos arquivos armazenados.

## Fase C — equal-update com bloco extra inicialmente identidade

Para testar a hipótese de que o modelo profundo perdeu apenas por executar menos optimizer updates no mesmo orçamento de CPU, congelamos o lado de 1 bloco da Fase B e treinamos apenas o lado de 2 blocos atual com:

- mesma seed e checkpoint de origem;
- mesmo tokenizer/dataset;
- mesmo stream de minibatches;
- mesmos pontos de validação;
- exatamente o mesmo número de updates do baseline de 1 bloco em cada seed;
- bloco adicional inicializado como identidade residual.

| Seed | Steps | Correct 1 bloco | Correct 2 blocos | Val NLL 1 bloco | Val NLL 2 blocos |
|---:|---:|---:|---:|---:|---:|
| 11 | 11.269 | 53/194 | **55/194** | 0,4313 | **0,2152** |
| 22 | 11.286 | 37/194 | 37/194 | 0,4101 | **0,2725** |
| 33 | 9.661 | **59/194** | 46/194 | **0,3104** | 0,4058 |
| **Total** | — | **149/582** | 138/582 | **mediana 0,4101** | **mediana 0,2725** |

O exact agregado foi **147/582** para o baseline de 1 bloco e **138/582** para 2 blocos. O lado de 2 blocos consumiu **1,197×** o CPU de treino na mediana para receber os mesmos updates e teve **1,048×** a latência nativa mediana.

A Fase C elimina “menos updates” como explicação principal para a diferença agregada. Também mostra uma divergência importante: validation NLL pode melhorar sem melhorar geração greedy final.

Dados: `results/v012_equal_steps/training.json` e `results/v012_equal_steps/evaluation.json`.

## Decisão

**1 bloco permanece o modelo padrão.**

Motivo: 2 blocos não apresentou ganho consistente entre seeds no teste final de geração livre, perdeu o agregado de exact/correct e aumentou todos os custos principais. O suporte multi-bloco permanece no runtime porque está correto e é útil para novos experimentos.

O diagnóstico curto teacher-forced não foi descartado: ele mostra que profundidade extra pode melhorar representação/local token prediction em certas condições. A v0.12 apenas conclui que, com este orçamento e este treino, isso não se converteu em melhor geração final.

## Verificação

- 15/15 CTests Release.
- 138/138 testes Python.
- 15/15 CTests com SIMD desativado.
- 15/15 CTests com ASan + UBSan.
- Paridade: 4/4, erro absoluto máximo 3,5763e-7.
- 142 artefatos legados intactos.
- 24 artefatos v0.12 adicionados.

## Limites

Dataset sintético e pequeno; Linux x86-64. Pico de RSS, energia, Windows, ARM e PC fraco real não foram medidos. Nenhum resultado deste documento implica inteligência geral ou comparação direta com grandes LLMs.

## Reproduzir

A Fase B armazenada pertence ao código usado na execução original (commit `50f2b5760ecb6691ae93b7e3bd6310028be63c38`). O HEAD atual usa inicialização por identidade e não deve ser apresentado como reprodução idêntica daquela rodada.

A ablação equal-update do protocolo atual pode ser executada com:

```bash
python benchmarks/instruction_blocks_equal_steps_v012.py --seeds 11 22 33 --threads 1 --baseline results/v012/training.json --out results/v012_equal_steps/training.json --model-dir models/v012_equalsteps
python benchmarks/instruction_blocks_equal_steps_eval_v012.py --build build --training results/v012_equal_steps/training.json --baseline-eval results/v012/evaluation.json --out results/v012_equal_steps/evaluation.json
python tools/verify_multiblock.py --build build --out results/v012/multiblock_parity.json
```

Dados brutos: `results/v012/` e `results/v012_equal_steps/`.
