# EdgeAI Engine v0.4 — precisão seletiva em CPU

Engine C++17 com FP32, INT8 e ternário no mesmo modelo. **Protótipo de pesquisa,
não um assistente avançado nem uma IA demonstrada superior a Claude.** A inferência
nativa não precisa de GPU, Python, PyTorch, internet ou chave de API.

Esta versão testa a hipótese da v0.3: preservar precisão no caminho da memória e
comprimir o restante. A arquitetura e o número de parâmetros foram mantidos.
Os resultados não justificam escalar o núcleo totalmente ternário sem outras mudanças.

## Resultado principal

No teste sintético de recuperação de associações, com três inicializações:

| Política do núcleo | Acerto médio |
|---|---:|
| FP32 | 48,50% |
| Ternário | 13,83% |
| Somente Q/K FP32; restante ternário | 14,36% |
| Memória FP32; FFN ternário | 46,32% |
| Memória INT8; FFN ternário | 45,35% |
| INT8 nas seis projeções | 48,11% |
| Transformer FP32 de referência | 52,51% |

O Transformer tem 24.176 parâmetros, contra 24.102 dos híbridos. A variação entre
inicializações é grande. Isso não demonstra equivalência estatística nem capacidade
de conversação. São símbolos conjuntos (chave,valor), não linguagem natural.

Uma ablação separada converteu a saída dos checkpoints INT8 para INT8, sem retreinar:
48,08% de acerto médio, 52.120 bytes numéricos de pesos contra 96.408 em FP32
(45,9% menos). O arquivo tem 52.312 bytes. **Não houve aceleração nesse micro-modelo**:
medianas de 2,70 µs por passo de byte contra 2,58 µs FP32 no host de laboratório.
RSS ficou indistinguível na resolução observada; não confundir bytes de pesos com
RAM total. Energia não medida: sensores indisponíveis.

Detalhes, intervalos observados e todos os resultados em `BENCHMARK_RESULTS.md`.

## Executar — Linux x86-64

Binários incluídos, testados no Linux x86-64 do laboratório:

```bash
chmod +x bin/linux-x86_64/*
./bin/linux-x86_64/edgeai_chat models/mixed_tiny.edge --mode eco
```

Dependências de glibc/libstdc++ podem impedir executar esses binários em distribuições
antigas. Compilar localmente evita depender da versão de biblioteca do nosso host.
Não existe garantia de funcionar em qualquer PC.

## Compilar — Linux/macOS

CMake >= 3.16 e compilador C++17:

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j 2
ctest --test-dir build --output-on-failure
./build/edgeai_chat models/mixed_tiny.edge --mode eco
./build/edgeai_inspect models/mixed_tiny.edge
```

macOS não foi testado. Os kernels AVX2 especializados são para x86 com GCC/Clang;
outras combinações utilizam o caminho portável. O executável inteiro não exige AVX2.

## Windows

No terminal de desenvolvimento do Visual Studio, com CMake e compilador C++17:

```bat
build_windows.bat
build\Release\edgeai_chat.exe models\mixed_tiny.edge --mode eco
```

**Não há `.exe` Windows incluído e esta versão não foi testada no Windows.** Outros
geradores podem colocar o executável diretamente em `build\edgeai_chat.exe`.

## O que o programa faz agora

```text
253 * 719
lembrar: o projeto usa precisao seletiva
buscar memoria: precisao
usuario: ola
sair
```

Cálculos e busca textual usam os módulos determinísticos. Perguntas abertas usam o
modelo experimental fornecido, que ainda gera texto repetitivo. Não há assistente
geral treinado em escala. Sem modelo, o backend de desenvolvimento é identificado.

`token_score` é a probabilidade máxima de um token, não confiança calibrada de que
uma resposta está correta. `models/recall/` e `models/head_ptq/` contêm modelos para
o ensaio sintético, **não modelos de chat**. Para demonstrar o caminho de linguagem,
use `models/mixed_tiny.edge` (também microscópico e sem qualidade de assistente).

## Precisões e formato

EDGEAI4 aceita FP32, INT8 por linha e ternário packed nas projeções e na saída.
Embedding, gates e estado continuam FP32. INT8 aqui é **W8A32**: pesos INT8,
ativações e acumulação FP32. Não é um motor inteiramente de operações inteiras.
Não se guarda cópia FP32 completa dos pesos INT8 dentro da engine.

O leitor preserva EDGEAI2/EDGEAI3. Salvar um `HybridModel` pelo C++ emite EDGEAI4.
O formato e as validações estão em `docs/FORMAT-v0.4.md`. No Python, a exportação
valida parâmetros e substitui o arquivo atomicamente. `.pt` é checkpoint separado;
a engine lê somente `.edge`.

## Treinar e exportar

Treino opcional: Python, NumPy e PyTorch. Testado com PyTorch 2.10.0+cpu.
O runtime C++ não depende deles. Instalação CPU-only: referências em `docs/SOURCES.md`.

```bash
python tools/train_mixed.py data/tiny_corpus.txt --valid data/validation.txt --policy int8 --output-precision int8 --steps 160 --threads 1 --out models/mixed_tiny.edge
```

Políticas disponíveis: `fp32`, `ternary`, `qk_fp32`, `memory_fp32`, `memory_int8`,
`int8`. O padrão da ferramenta é `memory_int8`; o comando acima seleciona explicitamente
a alternativa que apresentou maior acerto médio entre as duas variantes compactas.
A escolha ainda precisa ser retestada em texto/código reais e modelos maiores.

`--output-precision` aceita `fp32` (padrão), `int8` e `ternary`. Durante o treino,
pesos mestres, gradientes e estados são FP32 com quantização simulada e STE. O treino
não fica automaticamente menor ou mais rápido porque o arquivo final é INT8.
Saídas: `.edge`, `.pt`, `.training.json`; o checkpoint de demonstração é escolhido
pela validação separada, não pelo teste sintético.

## Reproduzir pesquisa e testes

```bash
python benchmarks/precision_v04.py --steps 400 --seeds 11 22 33 --threads 1
python benchmarks/output_ptq.py
python tools/verify_mixed.py --binary build/edgeai_logits --inspect build/edgeai_inspect
python tools/verify_parity.py --binary build/edgeai_logits --out results/legacy-parity.json
python -m unittest discover -s tests -p 'test_*.py'
python benchmarks/run_precision_native.py --binary build/edgeai_runtime_benchmark
python benchmarks/measure_energy.py --out results/energy.json -- ./build/edgeai_runtime_benchmark models/mixed_tiny.edge 100000
```

Protocolo previamente definido em `docs/PROTOCOL-v0.4.md`: inicialização e lotes
verificados por hashes, três sementes, número fixo de passos, conjuntos de teste
separados e nenhuma seleção do melhor resultado. A cabeça INT8 pós-treino é uma
ablação separada, usando os mesmos checkpoints congelados.

```bash
cmake -S . -B build-portable -DCMAKE_BUILD_TYPE=Release -DEDGEAI_DISABLE_SIMD=ON
cmake --build build-portable -j 2
ctest --test-dir build-portable --output-on-failure

cmake -S . -B build-sanitizer -DCMAKE_BUILD_TYPE=Debug -DEDGEAI_SANITIZERS=ON -DCMAKE_CXX_COMPILER=clang++
cmake --build build-sanitizer -j 2
ctest --test-dir build-sanitizer --output-on-failure
```

O CTest inclui teste de CLI via Python quando o interpretador está disponível.
Os testes de treinamento/paridade com PyTorch são executados separadamente.

## Limites preservados

Cada `ask` reinicia o estado; não há histórico de conversa automático. Memória textual
é arquivo de linhas carregado em RAM, não RAG semântico/mmap/SQLite. Pesos também são
carregados em RAM. Inferência usa uma thread. ECO/BALANCED/MAX limitam contexto e
profundidade; não são modos de potência medidos. Profundidade treinada não é cortada
com base em confiança softmax. Não implementamos especialistas, SSM paralelo, INT8
nas ativações, quantização do embedding, NEON ou aprendizado de linguagem em escala.

Tempos foram medidos em VM com Xeon, não em PC antigo. Passos de bytes não são tokens
BPE ou respostas úteis. Energia tem valor nulo quando não há contador legível.

## Arquivos de evidência

`results/` contém os resultados da v0.4, inclusive logs esperadamente vermelhos antes
de implementar as funções. `results-v0.3/` e `docs/history/` preservam a entrega anterior.
O log `precision-quality-interrupted.log` é uma execução interrompida e não participa
das tabelas; a execução completa foi repetida com o protocolo inalterado.
