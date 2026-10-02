# EdgeAI Engine v0.12 — Transformer multi-bloco nativo

Base: v0.11. A v0.12 adiciona suporte real a múltiplos blocos do Python ao runtime C++, mantendo compatibilidade com modelos antigos.

## O que mudou

- Novo formato `EDGEAI8` para modelos com mais de um bloco.
- `TinyTransformer` aceita de 1 a 8 blocos.
- Runtime C++ executa todos os blocos em sequência com cache KV independente por bloco.
- `EDGEAI5/6/7` continuam carregando como modelos de um bloco.
- Exportação de um bloco continua usando o formato legado correspondente.
- `edgeai_inspect` distingue corretamente `EDGEAI7` e `EDGEAI8`.

## Paridade Python ↔ C++

O verificador usa 1 e 2 blocos, kernels `scalar` e `auto`, sequência de 11 tokens e janela 4 para forçar wrap do cache KV.

| Medida | Resultado |
|---|---:|
| Casos | 4/4 |
| Maior erro absoluto | 3,5763e-7 |
| Tolerância absoluta | 6e-5 |
| Tolerância relativa | 6e-5 |

## Experimento controlado — 60 s de CPU por arquitetura/seed

Mesmo dataset congelado, tokenizer, `dim=48`, `hidden=128`, janela 64, batch 16, AdamW e uma thread. Seeds 11, 22 e 33. Seleção apenas por validation NLL; os testes ficam fora da seleção.

| Medida | 1 bloco | 2 blocos |
|---|---:|---:|
| Parâmetros | 71.827 | 93.699 |
| Arquivo `.edge` | 154.400 B | 178.976 B |
| Pesos numéricos residentes | 152.168 B | 176.616 B |
| Estado KV | 24.576 B | 49.152 B |
| Working memory numérica | 29.420 B | 56.300 B |
| Mediana de steps em 60 s | 11.269 | 6.897 |
| Mediana validation NLL | **0,4101** | 0,4352 |
| Geração nativa exata | **147/582 (25,26%)** | 138/582 (23,71%) |
| Respostas corretas pela métrica do dataset | **149/582 (25,60%)** | 138/582 (23,71%) |
| Mediana de tempo interno por caso | **0,650 ms** | 0,779 ms |

Por seed, 2 blocos melhorou o exact-match apenas na seed 22 (37 → 46). Nas seeds 11 e 33, caiu de 53 → 48 e 57 → 44. Portanto, o ganho não foi consistente.

Custos do segundo bloco nesse modelo:

- +30,45% de parâmetros;
- +15,92% no arquivo `.edge`;
- +100% de estado KV;
- +91,37% de working memory numérica;
- cerca de 38,80% menos steps no mesmo orçamento de CPU;
- cerca de 19,82% mais tempo interno mediano por caso.

## Ablação equal-update com inicialização identidade

Depois do experimento de 60 s, a inicialização do bloco extra foi alterada para começar como **identidade residual**, de forma que adicionar o segundo bloco não mude a função do modelo antes do treino. Os artefatos históricos de `results/v012/` foram gerados pelo protocolo anterior (`edge-sft-v012-blocks-1`); o código atual usa o protocolo versionado de inicialização por identidade. Portanto, uma nova execução no HEAD atual não deve ser tratada como reprodução bit a bit daqueles artefatos antigos.

Para separar profundidade de quantidade de updates, a ablação `results/v012_equal_steps/` congelou o baseline de 1 bloco e deu ao modelo atual de 2 blocos exatamente o mesmo stream de minibatches, os mesmos pontos de validação e o mesmo número de optimizer updates por seed.

| Seed | 1 bloco correct | 2 blocos equal-update correct | Steps pareados |
|---:|---:|---:|---:|
| 11 | 53/194 | **55/194** | 11.269 |
| 22 | 37/194 | 37/194 | 11.286 |
| 33 | **59/194** | 46/194 | 9.661 |
| **Total** | **149/582** | 138/582 | — |

No agregado exato, o baseline ficou em **147/582** e 2 blocos em **138/582**. A mediana de validation NLL favoreceu 2 blocos (**0,2725** contra 0,4101), mas isso não se converteu em melhor geração livre. Para receber os mesmos updates, 2 blocos consumiu **1,197×** o CPU de treino na mediana e teve **1,048×** a latência nativa mediana.

Assim, “2 blocos perdeu apenas porque completou menos steps em 60 s” não explica o resultado. O próximo diagnóstico relevante é de dinâmica de otimização por bloco (gradientes, mudança funcional, warm-up/congelamento), não apenas mais orçamento.

## Diagnóstico curto anterior

O ensaio de 12 s registrado em `results/v012/blocks.json`, com avaliação teacher-forced, favoreceu 2 blocos em NLL e acurácia de tokens. Esse sinal continua útil, mas não é a decisão final: no protocolo principal de 60 s com geração nativa livre, 2 blocos não melhorou de forma consistente.

## Decisão

**1 bloco permanece o padrão.** O suporte multi-bloco continua disponível como infraestrutura de pesquisa, porque funciona e passa paridade, mas 2 blocos não justificou o custo extra neste protocolo.

## Verificação final

- Release CTest: **15/15**.
- Python: **138/138**.
- Sem SIMD: **15/15 CTest**.
- ASan + UBSan: **15/15 CTest**.
- 142 modelos/checkpoints legados permaneceram sem alteração.
- 24 novos arquivos de modelo/checkpoint v0.12 foram preservados.
- Energia e pico de RSS não foram medidos: `null`.

Limite: o dataset é sintético e pequeno. Estes números medem este protocolo; não demonstram inteligência geral, desempenho em PC fraco real, Windows/ARM ou superioridade sobre grandes LLMs.

---

## Histórico: EdgeAI Engine v0.11 — ranking estrutural de busca de codigo

Base efetiva: v0.10. **Sem novo treinamento, sem LLM externo real e sem alteracao dos modelos neurais.**

## Mudanca

A busca local continua lexical e deterministica, mas agora o ranking diferencia melhor definicoes de usos. Linhas com formas de definicao comuns (`def`, `class`, `function`, `fn`, `func`, `stock`, `public`, `forward`) recebem prioridade; comentarios e ocorrencias dentro de strings sao penalizados. Ocorrencias com corpo em C/C++-like recebem sinal estrutural adicional. A busca tambem deixa de descartar todas as ocorrencias secundarias de um arquivo: multiplos trechos relevantes do mesmo arquivo podem aparecer no top-N.

Isso **nao e parser completo**, AST multi-linguagem ou compreensao semantica. Macros, sintaxes incomuns, aliases e construcoes ambiguas ainda podem ser ordenadas incorretamente.

## Benchmark controlado v0.10 x v0.11

Mesmo snapshot CPython distribuido no projeto: 18 modulos, 27 consultas positivas derivadas de definicoes top-level por AST e 8 nomes ausentes. Cinco sessoes por versao no mesmo host, um processo por sessao. Evidencia de cada hit foi conferida contra o arquivo fonte.

| Metrica | v0.10 | v0.11 |
|---|---:|---:|
| Definicao esperada top-1 | 16/27 | **24/27** |
| Definicao esperada top-5 | 18/27 | **26/27** |
| Nomes ausentes vazios | 8/8 | **8/8** |
| Mediana da sessao (35 consultas) | 26.104 ms | **27.659 ms** |

Neste host, a sessao v0.11 ficou cerca de 5.95% mais lenta que v0.10, enquanto top-1 subiu de 59.26% para 88.89%. Isso mede apenas esse corpus e esse host; nao generalizar para outros repositorios ou PCs fracos.

## Teste de regressao novo

O teste de busca agora inclui um arquivo Python em que comentario, string e chamada aparecem antes da definicao real. Antes da implementacao, o teste falhou porque a chamada anterior venceu a definicao. Depois da mudanca, a definicao real fica em primeiro lugar e mais de uma ocorrencia util do mesmo arquivo e preservada.

## Verificacao

- Release CTest: **13/13**.
- Python: **108/108**.
- Build portavel com `EDGEAI_DISABLE_SIMD=ON`: **13/13 CTest**.
- ASan + UBSan: **13/13 CTest**.
- **142 arquivos `.edge/.pt` identicos por SHA-256 a v0.10**.
- Nenhum treinamento novo e nenhuma alegacao de ganho de inteligencia neural.

## Limites

O benchmark e de recuperacao lexical de codigo, nao de programacao autonoma. Nao houve comparacao com Claude/Opus, medicao de energia, Windows/ARM ou teste no PC fraco real. A v0.11 melhora a qualidade de navegacao em codigo; nao demonstra melhora do pequeno Transformer do EdgeAI.
