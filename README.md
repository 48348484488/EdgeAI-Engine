# EdgeAI Engine

**EdgeAI Engine** é um motor experimental de IA local em C++ criado para pesquisar uma pergunta importante:

> Quanto de capacidade útil conseguimos colocar em uma IA que roda localmente, usando pouca CPU, RAM e energia?

O projeto combina um **modelo neural próprio e pequeno** com ferramentas determinísticas, memória local e busca de código. O foco é medir ganhos reais — não fingir que o modelo atual já é comparável a ChatGPT ou Claude.

**Versão estável atual: v0.11**  
**Experimento mais recente: 2 blocos (candidato v0.12)**

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

Testamos **1 bloco vs. 2 blocos Transformer** com os mesmos dados, três seeds e o mesmo orçamento de CPU.

| Medida | 1 bloco | 2 blocos |
|---|---:|---:|
| Parâmetros | 71.827 | 93.699 |
| NLL mediano nos 194 testes | 2,8149 | **2,4919** |
| Acurácia de tokens | 57,27% | **60,20%** |
| Linhas corretas com teacher forcing | 18,21% | **20,96%** |

O modelo de 2 blocos melhorou o NLL de teste em **3/3 seeds**, mesmo executando menos passos no mesmo tempo de CPU. Porém, continuou com **0 linhas completas corretas** nos testes de extrapolação e na tarefa nova.

Isso é evidência de ganho de capacidade neste protocolo, **não** prova de inteligência geral e ainda não muda o runtime padrão.

Relatório completo: [docs/v012/BLOCKS_EXPERIMENT.md](docs/v012/BLOCKS_EXPERIMENT.md)

### Próximo passo

Adicionar suporte nativo opcional a múltiplos blocos no runtime C++, manter compatibilidade com os modelos de 1 bloco e então medir geração real, RAM e latência antes de promover 2 blocos como padrão.

## Mais detalhes

- [BENCHMARK_RESULTS.md](BENCHMARK_RESULTS.md) — resultados e metodologia da versão atual
- [CHANGELOG.md](CHANGELOG.md) — histórico de mudanças
- [METAS.md](METAS.md) — metas técnicas do projeto

---

**EdgeAI Engine é um projeto de pesquisa experimental.** Cada avanço deve vir acompanhado de teste, benchmark ou evidência reproduzível.
