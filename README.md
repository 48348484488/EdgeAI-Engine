# EdgeAI Engine

**EdgeAI Engine** é um motor experimental de IA local em C++ criado para pesquisar uma pergunta importante:

> Quanto de capacidade útil conseguimos colocar em uma IA que roda localmente, usando pouca CPU, RAM e energia?

O projeto combina um **modelo neural próprio e pequeno** com ferramentas determinísticas, memória local e busca de código. O foco é medir ganhos reais — não fingir que o modelo atual já é comparável a ChatGPT ou Claude.

**Versão em validação: v0.12**  
**Resultado atual: suporte multi-bloco validado; 2 blocos ainda não substituem 1 bloco como padrão**

## O que ela já sabe fazer

| Recurso | Estado atual |
|---|---|
| Buscar funções, classes e símbolos em código local | ✅ Funciona |
| Priorizar definições sobre comentários, strings e chamadas | ✅ v0.11 |
| Reutilizar índice em RAM entre consultas | ✅ Funciona |
| Detectar arquivos alterados/adicionados/removidos | ✅ Funciona |
| Memória local simples | ✅ Funciona |
| Calculadora determinística | ✅ Funciona |
| Roteamento automático entre busca, memória, cálculo e modelo neural | ✅ Funciona |
| Executar modelos próprios `.edge` em CPU | ✅ Experimental |
| Conversa e raciocínio geral no nível de grandes LLMs | ❌ Ainda não |

A busca de código suporta C/C++, Python, Pawn, JavaScript/TypeScript, Rust, Go e outras extensões listadas em `src/CodeSearch.cpp`.

## Dados reais da v0.11

Benchmark controlado usando 18 módulos do CPython e 35 consultas:

| Medida | Resultado |
|---|---:|
| Definição correta em 1º lugar | **24/27 (88,9%)** |
| Definição correta no Top 5 | **26/27 (96,3%)** |
| Nomes inexistentes corretamente vazios | **8/8** |
| 35 consultas na mesma sessão | **27,659 ms** |
| Testes C++ Release | **13/13** |
| Testes Python | **108/108** |
| Modelos/checkpoints preservados | **142/142** |

A v0.10 acertava 16/27 definições em primeiro lugar. A v0.11 chegou a 24/27 com cerca de **6% de aumento no tempo da sessão** nesse mesmo teste.

Esses números medem **busca de código**, não inteligência geral.

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

A ideia é simples: não gastar rede neural em tarefas que podem ser resolvidas de forma mais barata e confiável.

## Testar rapidamente

Linux x86-64:

```bash
./bin/linux-x86_64/edgeai_chat --code-root . --memory :memory:
```

Dentro do chat:

```text
buscar codigo: greedy_token
calcule 128 * 32
lembrar: EdgeAI usa busca local
buscar memoria: EdgeAI
```

Busca direta:

```bash
./bin/linux-x86_64/edgeai_code_search . "greedy_token" --limit 5
```

## Compilar

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j2
ctest --test-dir build --output-on-failure
```

O código é C++17. O caminho Linux x86-64 foi testado. Windows/ARM e PCs realmente fracos ainda precisam de validação prática.

## O que o projeto ainda não é

O EdgeAI **não é atualmente um substituto para Claude, ChatGPT ou outros LLMs grandes**. O modelo neural próprio ainda é pequeno e limitado.

Também não há, por enquanto, evidência de:

- inteligência geral comparável a grandes modelos;
- correção autônoma confiável de bugs;
- compreensão semântica completa de um repositório;
- menor consumo de energia que grandes LLMs;
- desempenho confirmado em Windows, ARM ou hardware muito fraco.

Quando algo não foi medido, o projeto não trata como resultado.

## Objetivo

O objetivo de longo prazo é aumentar a capacidade útil mantendo o sistema:

- **local**;
- **CPU-first**;
- **leve em memória**;
- **rápido para tarefas comuns**;
- **mensurável e reproduzível**.

A estratégia é combinar modelos pequenos com memória, ferramentas e kernels eficientes em vez de simplesmente aumentar o número de parâmetros.

### Experimento mais recente

A v0.12 adiciona suporte real a múltiplos blocos no Python, no formato **EDGEAI8** e no runtime C++. A paridade Python/C++ passou para 1 e 2 blocos, inclusive com sequência maior que a janela de atenção; o maior erro absoluto observado foi **3,58e-7** para tolerância de **6e-5**.

No teste controlado de **geração nativa** foram usados os mesmos dados, seeds 11/22/33, uma thread e 60 segundos de CPU por arquitetura/seed. Cada checkpoint foi escolhido apenas pela validation NLL e depois avaliado em 194 casos de teste.

| Seed | 1 bloco | 2 blocos |
|---|---:|---:|
| 11 | **54/194** | 43/194 |
| 22 | 37/194 | **49/194** |
| 33 | **54/194** | 37/194 |

Somando as três seeds, foram **145/582** respostas corretas para 1 bloco e **129/582** para 2 blocos. Portanto, neste protocolo, aumentar a profundidade para 2 blocos **não produziu ganho consistente de geração**.

O modelo de 2 blocos também custa mais: **93.699 vs. 71.827 parâmetros**, arquivo `.edge` de **178.976 vs. 154.400 bytes** e cache KV calculado de **49.152 vs. 24.576 bytes**. A mediana interna de geração também foi maior nos três pares medidos.

Um benchmark teacher-forced anterior mostrou melhora de NLL/tokens para 2 blocos, mas a avaliação posterior de geração nativa é o critério mais próximo do uso real e não confirmou essa vantagem. Por isso, **1 bloco permanece como padrão** enquanto investigamos treinamento/arquitetura melhores.

Os JSONs reproduzíveis estão em `results/v012/`. Os checkpoints completos permanecem preservados no artefato do GitHub Actions do benchmark.

### Próximo passo

Em vez de simplesmente adicionar profundidade, a próxima etapa deve investigar por que o segundo bloco melhora algumas métricas intermediárias mas não a geração final de forma consistente, mantendo o mesmo protocolo controlado.

## Mais detalhes

- [BENCHMARK_RESULTS.md](BENCHMARK_RESULTS.md) — resultados e metodologia da versão atual
- [CHANGELOG.md](CHANGELOG.md) — histórico de mudanças
- [METAS.md](METAS.md) — metas técnicas do projeto

---

**EdgeAI Engine é um projeto de pesquisa experimental.** Cada avanço deve vir acompanhado de teste, benchmark ou evidência reproduzível.
