# EdgeAI Engine v0.6 — resultados reais e limites

Ciclo executado em 25/09/2026. Evidência principal: `results/v06/`.
**Seis treinos de pesquisa, três inicializações por sistema, CPU somente.**
Os modelos continuam experimentais; não há demonstração de capacidade comparável
com Claude/Opus, nem medida de economia de energia.

## 1. Entrega e hipótese

Implementamos byte-BPE reversível em Python e C++17; vocabulário variável e tokenizador
embutido no formato EDGEAI6. Todos os 256 bytes existem, sem descartar caracteres.
O modelo usa um Transformer pequeno já disponível, não uma arquitetura nova.
A hipótese era melhorar qualidade/custo usando unidades maiores que um byte.
Protocolo escrito antes dos ensaios: `docs/v06/DESIGN.md`.

BPE é uma técnica conhecida. Implementação e fontes em `docs/SOURCES.md`.
A configuração usa 256 merges, resultando em 512 símbolos de conteúdo + BOS.
O baseline usa 256 bytes + BOS. Uma janela de 64 tokens cobre quantidades diferentes
 de texto nos dois casos; dimensões internas diferem para aproximar parâmetros.

## 2. Corpus independente da engine

Snapshot de **18 módulos de CPython** da instalação local: 12 treino, 3 validação,
3 teste. Preservamos os bytes originais, licença e copyright da distribuição.
Não houve download confirmado de um tag; `upstream_commit_verified=false`.
Versão da instalação, caminhos e hashes estão em `data/cpython_snapshot/manifest.json`.
Não há material da própria EdgeAI sendo usado como corpus nesta comparação.

Treino: **357,941 bytes**. Validação após filtragem:
**104,763 bytes**. Teste: **29,480 bytes**, os mesmos
116 blocos para ambos os sistemas. Removemos dois blocos da validação e nenhum do
 teste por similaridade normalizada com partições anteriores. Grupos são módulos;
shingles léxicos de tamanho 5 detectam quase duplicatas sob os limites documentados.
Isto não remove toda similaridade semântica, sintaxe/idiomas comuns ou influência
entre módulos. **É um projeto/domínio externo, não avaliação entre vários projetos.**

O tokenizador foi aprendido apenas nos arquivos de treino e reproduzido com
fingerprint idêntico. Custos de aprender merges/pretokenizar estão nos JSONs,
separados do orçamento do modelo; não são computação gratuita.
Código e comentários são principalmente Python/inglês, não conversa em português.

## 3. Qualidade sob o mesmo orçamento de CPU

Uma thread; 20 segundos de `process_time` por treino; sementes 11/22/33; batch 8;
sequência 64 tokens; AdamW lr 0,002, weight_decay 0,01; clipping de norma 1.
Contabiliza amostragem, forward, backward, otimizador, hash/contagem de lotes.
Exclui inicialização, tokenizador, validação, teste, exportação e compilação.
Termina uma atualização completa, portanto há pequeno excedente de orçamento.
Melhor checkpoint escolhido na validação nos pontos 25/50/75/100%, nunca no teste.

| Sistema | Parâmetros | Bits/byte médio ↓ | Faixa das 3 seeds | CPU média de treino | Arquivo inteiro |
|---|---:|---:|---:|---:|---:|
| byte257 | 71,529 | 2.7394 | 2.7183–2.7543 | 20.00340 s | 126,272 B |
| bpe513 | 71,633 | 2.4283 | 2.4026–2.4533 | 20.00387 s | 153,904 B |

A redução média do erro de previsão foi **11.35%** neste conjunto.
A faixa é mínimo–máximo, não intervalo de confiança. Não são porcentagens de
inteligência. Baseline bigrama add-0,1: **3.5574 bits/byte**.

Métrica: NLL da sequência **canônica** de tokens, dividida pelos bytes originais e
ln(2). BOS fornece contexto para o primeiro símbolo mas não conta como byte nem
alvo. BPE tem 15.633 alvos no teste contra 29.480 bytes; não se comparam diretamente
acurácias de tokens entre vocabulários. Essa NLL não marginaliza todas as possíveis
tokenizações de uma string. Código do denominador tem teste de distribuição uniforme.

### Todos os ensaios, sem escolher a melhor seed pelo teste

| Sistema | Seed | Atualizações | Atualização selecionada | Bits/byte teste | CPU treino (s) | Bytes representados pelos alvos de treino |
|---|---:|---:|---:|---:|---:|---:|
| bpe513 | 11 | 3451 | 3451 | 2.429060 | 20.005647 | 3,737,089 |
| bpe513 | 22 | 3487 | 3487 | 2.402636 | 20.002664 | 3,769,515 |
| bpe513 | 33 | 3421 | 3421 | 2.453349 | 20.003288 | 3,709,704 |
| byte257 | 11 | 3402 | 3402 | 2.718300 | 20.004321 | 1,741,824 |
| byte257 | 22 | 3367 | 3367 | 2.745563 | 20.001008 | 1,723,904 |
| byte257 | 33 | 3263 | 3263 | 2.754334 | 20.004869 | 1,670,656 |

BPE observa mais bytes por lote e por janela. Mesmo CPU e parâmetros aproximados
não significam mesmos FLOPs, mesma exposição aos dados, mesmas ativações ou energia.
Essa é uma comparação de sistemas/configurações, não efeito causal isolado do BPE.
Os arquivos BPE são **21.88% maiores**, pois mais parâmetros ficam no embedding
FP32 e há a tabela de merges. INT8 aqui é **W8A32**, com parâmetros mestres/gradientes/
otimizador FP32 no treinamento. Quantização simulada não é treinamento inteiro INT8.

## 4. Execução nativa sobre o mesmo texto

Host: `AMD EPYC 9V74 80-Core Processor`, `Linux-6.18.44-x86_64-with-glibc2.41`.
Máquina virtual moderna, não PC antigo. CPU fixada em 0 para esses
subprocessos. Cinco repetições por checkpoint, ordem intercalada embaralhada:
**30 execuções**, 15 por sistema. Medianas abaixo. Todos processam os mesmos
29.480 bytes de teste, com reset por bloco; **teacher forcing + avaliação**, não
latência para resolver uma pergunta nem benchmark de tokens gerados úteis.

| Sistema | Carregar (ms) | Tokenizar (ms) | Forward + pontuar (ms) | Total interno (ms) | RSS pico (KiB) |
|---|---:|---:|---:|---:|---:|
| byte257 | 0.215 | 0.041 | 298.934 | 299.477 | 2052 |
| bpe513 | 0.291 | 1.144 | 153.530 | 155.179 | 2180 |

Na mediana, o custo total interno dessa avaliação ficou **1.93× mais rápido**
com BPE. O cronômetro total inclui carga, leitura, tokenização, resets e pontuação;
exclui inicialização externa do processo pelo sistema operacional. Medianas dos
componentes não precisam somar exatamente a mediana do total.
Números não equivalem a consumo elétrico e não se comparam com os da v0.5, cujo
corpus/protocolo eram diferentes. Geração de 64 tokens é registrada separadamente
em `native.json`: gera quantidades diferentes de bytes, sem equivalência de trabalho.

| Sistema | Pesos numéricos (bytes) | Estado numérico (bytes) | Working buffers, incluindo estado (bytes) |
|---|---:|---:|---:|
| byte257 | 126088 | 32768 | 37156 |
| bpe513 | 151672 | 24576 | 29220 |

Pesos/estado/buffers não incluem todos os objetos, strings, alocador ou runtime;
RSS é do processo inteiro. Não somar estado ao working buffer. Tamanho do arquivo,
peso residente e RAM total são medidas distintas.

## 5. Capacidade útil: resultado separado

28 tarefas pequenas, escritas para diagnóstico: 12 aritméticas, 8 cópias exatas,
8 funções com expressão de retorno restrita, cada uma verificada em cinco entradas.
Prompts exatos ausentes do treino; não é benchmark externo padronizado nem controle
de toda possível contaminação semântica. Não houve treinamento de instruções.
Geração greedy limitada a 48 tokens; aritmética/cópia exigem saída textual exata;
código usa apenas a primeira linha e um interpretador AST restrito, sem `eval`,
`exec`, shell ou execução arbitrária de programas. Não há EOS aprendido: resultados
longos/extra podem falhar pelo critério exato. Critérios foram fixados antes da medição.

| Sistema | Seed | Aritmética | Cópia/instrução | Código restrito |
|---|---:|---:|---:|---:|
| byte257 | 11 | 0/12 | 0/8 | 0/8 |
| bpe513 | 11 | 0/12 | 0/8 | 0/8 |
| byte257 | 22 | 0/12 | 0/8 | 0/8 |
| bpe513 | 22 | 0/12 | 0/8 | 0/8 |
| bpe513 | 33 | 0/12 | 0/8 | 0/8 |
| byte257 | 33 | 0/12 | 0/8 | 0/8 |

Calculadora determinística da engine: **12/12**, reportada à parte.
Isso não é habilidade adquirida pelo modelo neural. Todos os prompts, respostas
(inclusive hex bruto) e resultados ficam em `capability.json`.
**Reduzir bits/byte ainda não tornou estes modelos assistentes úteis.**

## 6. Correção, testes e empacotamento

- Dez suítes CTest (inclui o teste CLI em Python), em Release, portátil sem SIMD
  especializado e Clang ASan+UBSan.
- 57 testes Python: lossless roundtrip, todos os bytes/Unicode, merges inválidos,
  BOS, causalidade, gradientes, splits/hashes, denominador, cache e metadados seguros.
- 24 novos casos de tokens/logits Python/C++ para BPE; 27 casos do Transformer
  legado; formatos anteriores preservados e revalidados pelas suítes.
- Todos os seis checkpoints treinados comparados em todos os logits;
  erro máximo observado **1.2159348e-05** (tolerância absoluta/relativa 6e-5).
- NLL nativa também confere com Python em todos os blocos de teste.
- Perfil `independent`: 12/12 etapas; `independent-quick`: 12/12 etapas.
- Verificação da extração/recompilação do ZIP e dos binários distribuídos registrada
  em `results/v06/release_verification.json` após a conferência final.

Na revisão, metadados TorchVersion causaram falha de carregamento seguro. Corrigimos
para string simples e repetimos os seis treinos com nova identidade de código;
não desativamos `weights_only`. Logs `red_*` e `native_checkpoint_failure.log`
são falhas esperadas/históricas antes da correção, não o estado final.
Comparação dos binários finais: `SHA256SUMS.txt` cobre os arquivos do pacote.

## 7. Energia, plataformas e decisão

Energia disponível: **não**; `package_energy_joules=null`.
O comando medido terminou com exit_code 0. Não converter TDP, tempo,
utilização de CPU ou tamanho do arquivo em joules. RAPL, quando existir, mede pacote
 e também pode incluir outros processos; não é automaticamente energia na tomada.

Incluímos binários Linux x86-64. Windows tem fonte/script mas não foi testado;
não há `.exe` Windows, APK nem verificação em PC antigo. PyTorch é só para pesquisa;
inferência usa C++17 sem GPU, internet ou biblioteca neural externa.

**Decisão:** manter byte-BPE como configuração candidata para o próximo ensaio,
preservando byte-only como referência menor. Antes de escalar muito, a próxima meta
é melhorar tarefas explicitamente verificáveis com dados próprios para instruções,
separando treino/teste por famílias. Não marcar essa meta futura como já executada.
Não há benchmark com Claude, nem descoberta de arquitetura de fronteira.
