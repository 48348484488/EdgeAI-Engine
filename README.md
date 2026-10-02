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

### Profundidade: diagnóstico e melhor candidato

A ablação **equal-updates** deu ao modelo de 2 blocos exatamente o mesmo stream de minibatches e o mesmo número de optimizer updates do baseline de 1 bloco. Isso não resolveu a diferença: o baseline ficou em **147/582 exatos (149 `correct`)** e o 2-blocos random-identity em **138/582**. Portanto, menos updates no orçamento fixo de CPU não era a explicação principal.

O probe de dinâmica mostrou a causa mais provável: após apenas 128 updates, o bloco herdado havia mudado cerca de **11–12%** da própria norma, enquanto o miolo aleatório do novo bloco havia mudado cerca de **48–55%**. A partir disso, testamos uma inicialização que copia `Q/K/V/up` do bloco treinado para o bloco novo, mantendo `project/down` zerados para preservar exatamente a função inicial.

| Variante de 2 blocos | Exato/correct no teste original | Observação |
|---|---:|---|
| random-identity + equal updates | 138/582 | baseline de ablação |
| copy-inner + LR normal | 145/582 | +7 sobre random-identity |
| **copy-inner + LR interno 0,25×** | **163/582** | melhor agregado |

O baseline de 1 bloco tem **147/582 exatos** e **149/582 `correct`**. O candidato de 2 blocos com copy-inner + LR interno 0,25× chegou a **163/582** em ambas as métricas, mas no teste original venceu claramente apenas a seed 22; por isso o resultado agregado sozinho não é suficiente para promovê-lo como padrão.

Para uma replicação adicional, congelamos os modelos e construímos depois um holdout de **128 entradas novas por seed**, sem qualquer retreino: strings de tamanho 5, somas com operandos 20–29 e coeficientes 30–39, faixas que não aparecem no dataset v0.7 congelado. Nesse holdout pós-hoc, 1 bloco fez **15/384** exatos e o candidato fez **60/384**, vencendo em **3/3 seeds** (7→10, 4→41 e 4→9). É um sinal forte de generalização dentro dessas tarefas sintéticas, mas o holdout foi criado após observarmos os testes originais e não é um benchmark pré-registrado.

O custo continua real: 2 blocos usa **93.699 parâmetros**, dobra o estado KV e, no holdout executado no mesmo runner, ficou cerca de **18–21% mais lento** internamente que 1 bloco. Por isso, **1 bloco continua sendo o padrão de runtime**, enquanto copy-inner + LR interno 0,25× é o candidato neural experimental preferido para a próxima rodada de pesquisa.

Evidências: `results/v012_equal_steps/`, `results/v012/block_dynamics.json`, `results/v012_copy_init/`, `results/v012_copy_init_low_lr/` e `results/v012_fresh_holdout/`.

Paridade Python/C++: 4/4 casos passaram, com maior erro absoluto de **3,5763e-7**.

## Verificação v0.12

A verificação final da branch executa Release, suíte Python, paridade Python/C++, build sem SIMD, ASan+UBSan e auditoria dos modelos legados. O resultado reproduzível fica em `results/v012/verification.json`.

- Modelos/checkpoints legados esperados: **142**
- Modelos/checkpoints experimentais v0.12 preservados no Git: **24**

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
