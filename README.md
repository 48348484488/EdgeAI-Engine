# EdgeAI Engine

**EdgeAI Engine** é um motor experimental de IA local em C++ para pesquisar quanta capacidade útil pode rodar localmente com pouca CPU, RAM e energia.

O projeto combina um **modelo neural próprio e pequeno** com ferramentas determinísticas, memória local e busca de código. O foco é medir ganhos reais — não fingir que o modelo atual já é comparável a ChatGPT ou Claude.

**Versão verificada nesta branch: v0.12.0**  
**`main` permanece em v0.11 até a integração desta branch.**

## O que já funciona

| Recurso | Estado |
|---|---|
| Busca local de funções, classes e símbolos | ✅ |
| Ranking que prioriza definições sobre comentários/strings/chamadas | ✅ v0.11 |
| Índice de código reutilizado em RAM e atualização de arquivos | ✅ |
| Memória local e calculadora determinística | ✅ |
| Roteamento entre ferramentas e modelo neural | ✅ |
| Modelos próprios `.edge` em CPU | ✅ Experimental |
| Transformer nativo com 1..8 blocos | ✅ v0.12 |
| Formato multi-bloco `EDGEAI8` | ✅ v0.12 |
| Conversa/raciocínio geral no nível de grandes LLMs | ❌ |

A busca de código suporta C/C++, Python, Pawn, JavaScript/TypeScript, Rust, Go e outras extensões listadas em `src/CodeSearch.cpp`.

## Dados reais

### Busca de código v0.11

| Medida | Resultado |
|---|---:|
| Definição correta em 1º lugar | **24/27 (88,9%)** |
| Definição correta no Top 5 | **26/27 (96,3%)** |
| Nomes inexistentes corretamente vazios | **8/8** |
| 35 consultas na mesma sessão | **27,659 ms** |

### Transformer v0.12 — 1 bloco vs. 2 blocos

Três seeds, 60 s de CPU por arquitetura/seed e avaliação final por geração C++ nativa nos mesmos 194 casos por seed.

| Medida | 1 bloco | 2 blocos |
|---|---:|---:|
| Parâmetros | 71.827 | 93.699 |
| Arquivo `.edge` | 154.400 B | 178.976 B |
| Estado KV | 24.576 B | 49.152 B |
| Working memory numérica | 29.420 B | 56.300 B |
| Mediana de steps em 60 s | 11.269 | 6.897 |
| Mediana validation NLL | **0,4101** | 0,4352 |
| Geração nativa exata | **147/582 (25,26%)** | 138/582 (23,71%) |
| Mediana de tempo interno por caso | **0,650 ms** | 0,779 ms |

O ensaio curto teacher-forced de 12 s havia favorecido 2 blocos, mas a avaliação principal de 60 s com geração livre não reproduziu um ganho consistente: 2 blocos venceu apenas 1 das 3 seeds. Por isso, **1 bloco continua sendo o padrão**, enquanto o suporte multi-bloco permanece disponível para pesquisa.

### Ablação equal-updates

Para testar se 2 blocos perdia apenas porque conseguia menos updates dentro dos mesmos 60 s de CPU, repetimos o lado de 2 blocos usando **exatamente o mesmo stream de minibatches, os mesmos checkpoints de validação e o mesmo número de optimizer updates do baseline de 1 bloco** em cada seed.

| Seed | 1 bloco baseline (exato) | 2 blocos equal-updates (exato) |
|---|---:|---:|
| 11 | 53/194 | **55/194** |
| 22 | 37/194 | 37/194 |
| 33 | **57/194** | 46/194 |
| **Total** | **147/582** | 138/582 |

Pela métrica `correct` usada para expressões, o baseline soma **149/582** e 2 blocos **138/582**. Portanto, igualar a exposição ao treinamento **não removeu a diferença de geração**. O modelo de 2 blocos precisou de cerca de **1,197×** o CPU de treino para receber os mesmos updates. Isso descarta “menos passos no mesmo orçamento de CPU” como explicação principal, mas não prova qual mecanismo de otimização causa a instabilidade entre seeds.

O próximo diagnóstico deve medir gradientes e mudança funcional por bloco durante o treino e testar warm-up/congelamento do segundo bloco, em vez de simplesmente aumentar o orçamento.

Evidências equal-update: `results/v012_equal_steps/training.json` e `results/v012_equal_steps/evaluation.json`.

Paridade Python/C++: 4/4 casos passaram, com maior erro absoluto de **3,5763e-7**.

## Verificação v0.12

- Release CTest: **15/15**
- Python: **138/138**
- Sem SIMD: **15/15 CTest**
- ASan + UBSan: **15/15 CTest**
- Modelos/checkpoints legados preservados: **142/142**
- Novos artefatos v0.12: **24**

## Como funciona

```text
Pergunta
   ↓
Router
   ├── cálculo     → Calculator
   ├── memória     → LocalMemory
   ├── código      → CodeIndex
   └── outros      → modelo neural
```

A estratégia é não gastar rede neural em tarefas que uma ferramenta determinística pode resolver de forma mais barata e confiável.

## Compilar

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j2
ctest --test-dir build --output-on-failure
```

O código é C++17. Linux x86-64 foi validado. Windows, ARM e PCs realmente fracos ainda precisam de teste prático.

## Limites atuais

O EdgeAI **não é um substituto para Claude, ChatGPT ou outros LLMs grandes**. Ainda não há evidência de inteligência geral comparável, correção autônoma confiável de bugs, compreensão semântica completa de repositórios ou menor consumo de energia que grandes modelos.

O benchmark neural usa tarefas sintéticas. Energia e pico de RSS não foram medidos nesta rodada. Quando algo não foi medido, o projeto não trata como resultado.

## Próximos focos

- melhorar capacidade por unidade de CPU em vez de apenas aumentar profundidade;
- medir ARM/Windows e hardware fraco real;
- testar mudanças de dados/treino que melhorem geração livre sem dobrar o cache KV;
- continuar combinando modelos pequenos com ferramentas e memória.

## Mais detalhes

- [BENCHMARK_RESULTS.md](BENCHMARK_RESULTS.md) — resultados e metodologia atuais
- [docs/v012/BLOCKS_EXPERIMENT.md](docs/v012/BLOCKS_EXPERIMENT.md) — experimento 1×2 blocos
- [CHANGELOG.md](CHANGELOG.md) — histórico
- [METAS.md](METAS.md) — metas técnicas

---

**EdgeAI Engine é um projeto de pesquisa experimental.** Cada avanço deve vir acompanhado de teste, benchmark ou evidência reproduzível.
