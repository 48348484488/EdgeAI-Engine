# EdgeAI Engine

**Uma IA leve para ajudar na engenharia reversa de programas e jogos.**

O objetivo é analisar arquivos compilados, entender como o código funciona e, futuramente, ajudar a reconstruir funções equivalentes em C/C++. O projeto foi pensado para funcionar **localmente, sem GPU e com baixo consumo de recursos**.

> **Estado atual:** projeto experimental. Já existem ferramentas de análise de binários e um motor de IA compacto, mas **a reconstrução automática em C/C++ ainda não está pronta**.

## O que já faz?

| Recurso | Resultado atual |
|---|---|
| Analisar arquivos ELF (`.so` e executáveis) | Identifica metadados e funções que ainda tenham símbolos |
| Analisar instruções ARM32, Thumb16 e chamadas Thumb-2 | Localiza saltos e chamadas diretas `BL`/`BLX` em casos suportados |
| Mapear o fluxo do código (CFG) | Segue caminhos a partir de um endereço informado; análise parcial |
| Encontrar candidatos a funções | Segue chamadas diretas ARM `BL`, Thumb-2 `BL` e `BLX`, incluindo mudança de modo Thumb → ARM; ainda não confirma limites de funções |
| IA local em C++17 | Runtime de baixo consumo com ferramentas e modelo neural experimental |

**Exemplo prático:** ao fornecer uma biblioteca de jogo como `libGame.so`, as ferramentas podem listar funções nomeadas, endereços, saltos e caminhos de execução. Elas **não executam o jogo, não descobrem todas as funções sozinhas e ainda não geram seu código-fonte**.

## Como testar

Requisito para os analisadores: **Python 3**, sem pacotes externos.

```bash
# 1. Listar funções com símbolos preservados
python3 tools/elf_inspect.py libGame.so

# 2. Procurar saltos ARM32 em segmentos executáveis
python3 tools/arm_scan.py libGame.so --mode arm

# 3. Mapear o fluxo a partir de um endereço conhecido
python3 tools/arm_cfg.py libGame.so --entry 0x1000 --mode arm

# 4. Descobrir candidatos a funções e chamadas diretas ARM32
python3 tools/arm_functions.py libGame.so --entry 0x1000 --mode arm
```

Para código Thumb, use `--mode thumb` e informe o endereço alinhado, sem o bit que identifica o estado Thumb. Essas ferramentas usam decodificação parcial; **não escolha ARM ou Thumb ao acaso**.

Para testar as ferramentas:

```bash
python3 -m unittest discover -s tests -p 'test_elf_inspect.py' -v
python3 -m unittest discover -s tests -p 'test_arm_scan.py' -v
python3 -m unittest discover -s tests -p 'test_arm_cfg.py' -v
python3 -m unittest discover -s tests -p 'test_arm_functions.py' -v
python3 -m unittest discover -s tests -p 'test_thumb_calls.py' -v
```

## Teste com um jogo compilado

Incluímos um **jogo da velha pequeno em C**, compilado como executável ARM32 real.
Ele tem as rotinas `start`, `play` e `winner`. O teste compara as chamadas
que a EdgeAI encontra com o desassemblador LLVM Objdump:

```bash
python3 tools/validate_tictactoe_arm.py
```

Requer Clang, LLD e LLVM Objdump. O código de exemplo está em
[`examples/reverse/tictactoe.c`](examples/reverse/tictactoe.c).

O teste mede chamadas **diretas BL**, não reconstrói a lógica completa do
jogo. Uma transferência para `winner` por salto de cauda não conta
automaticamente como função descoberta.

## Validação com binários ARM reais

A verificação agora tem uma etapa própria: compilar três programas ARM/Thumb
pequenos com Clang e comparar chamadas diretas encontradas pela EdgeAI
com o LLVM Objdump. Ela mede acertos, falsos positivos e falsos negativos.

```bash
python3 tools/validate_arm_reference.py
```

Requer `clang`, `lld` e `llvm-objdump`. O resultado fica em JSON.
O workflow [Reverse engineering ARM reference](.github/workflows/reverse-arm-reference.yml)
também preserva o relatório como artefato de CI.

**Importante:** três programas pequenos comprovam apenas os casos testados,
não a precisão em jogos completos. Os números devem ser obtidos da execução;
não são estimados no README.

## Saltos de cauda e esboço de fluxo

Quando já conhecemos dois endereços de entrada, a ferramenta pode apontar um salto direto entre eles como **possível transferência de cauda**. Ela também gera um esboço comentado do fluxo, **não um código C++ funcional**:

```bash
python3 tools/arm_flow_outline.py jogo-arm.elf --entry 0x1080 --entry 0x1000 --mode arm
```

Os endereços acima são específicos do jogo da velha usado na validação; para outros executáveis, utilize as entradas corretas. Não há inferência automática de tipos, variáveis ou condições.

## Anotação inicial das instruções ARM

O analisador experimental agora reconhece algumas operações ARM32, como `MOV`, `CMP`, `ADD`, `SUB`, `B`, `BL` e `BX`, incluindo códigos de condição. As demais instruções ficam marcadas como **não suportadas**, sem inventar lógica:

```bash
python3 tools/arm_semantics.py jogo-arm.elf --entry 0x1080
```

Isso **não reconstrói variáveis nem produz C++**. Ainda falta analisar transferência de valores entre registradores, memória e ramificações. Os endereços de entrada dependem do executável.

## Rastreamento inicial de valores ARM32

A ferramenta `arm_constants.py` acompanha constantes em sequências lineares
de `MOV`, `ADD`, `SUB` e `CMP`. Por exemplo, após `MOV R0, #5` e
`ADD R0, R0, #3`, ela registra `R0 = 8`.

```bash
python3 tools/arm_constants.py jogo-arm.elf --entry 0x1080
```

Ela interrompe a análise diante de instruções não suportadas, condições ou
transferências de controle. **Não rastreia memória, junções de fluxo nem
reconstrói funções C++**.

## Constantes entre blocos ARM

O novo `arm_dataflow.py` percorre os caminhos do CFG para instruções ARM32 suportadas, acompanha constantes, avalia comparações `EQ`/`NE` e junta estados mantendo somente valores iguais entre todos os caminhos encontrados.

```bash
python3 tools/arm_dataflow.py jogo-arm.elf --entry 0x1000
```

A implementação **não é um descompilador**: interrompe caminhos em instruções desconhecidas, não modela memória nem efeitos completos de chamadas. As entradas e o conjunto ARM devem ser conhecidos.

## Memória ARM32: primeira análise

O módulo `arm_memory.py` reconhece `LDR`/`STR` de palavras com deslocamento imediato e acompanha valores gravados e carregados quando o endereço é conhecido:

```bash
python3 tools/arm_memory.py jogo-arm.elf --entry 0x1000
```

**Limitações:** apenas sequências lineares de instruções ARM32 incondicionais; não rastreia memória entre desvios, ponteiros desconhecidos nem mapeia automaticamente o tabuleiro do jogo. O binário é analisado, nunca executado.

## Memoria entre caminhos de execucao

O modulo `arm_memory_flow.py` acompanha acessos simples `LDR` e `STR`
entre desvios ARM32. Ao juntar caminhos, preserva somente constantes
compativeis. Escritas em endereco desconhecido invalidam a memoria conhecida;
chamadas invalidam os valores rastreados na memoria.

```bash
python3 tools/arm_memory_flow.py jogo-arm.elf --entry 0x1000
```

Ainda nao recupera automaticamente estruturas ou codigo C++.

## Acessos a memoria do jogo da velha compilado

O diagnostico `tools/inspect_tictactoe_memory.py` compila o jogo ARM32 e usa o
LLVM para listar instrucoes `LDR` e `STR` nas funcoes `start`, `play`
e `winner`. Tambem mostra o endereco do simbolo `board`:

```bash
python3 tools/inspect_tictactoe_memory.py
```

O relatorio **nao afirma** que cada instrucao acessa o tabuleiro:
comprovar essa relacao exige resolver os registradores e os enderecos efetivos.

## Endereços de memória indexados

O diagnóstico do jogo ARM inclui uma resolução conservadora de acessos
`LDR` e `STR` com deslocamento imediato ou registrador indexado, por
exemplo `[r1, r3, lsl #2]`. Os acessos ao símbolo `board` somente são
classificados como confirmados quando o endereço efetivo é conhecido e
está dentro de seus 36 bytes.

```bash
python3 tools/inspect_tictactoe_memory.py
```

O resolvedor reconhece `MOVW`/`MOVT` para construir endereços de 32 bits. Quando identifica o endereço-base de `board`, mas não sabe o índice, classifica o acesso como `board_base_dynamic_index`, **não** como endereço confirmado. Valores desconhecidos continuam não resolvidos, e a análise não atravessa todos os desvios e chamadas.

## Rastreamento simbolico entre desvios ARM

O analisador `tools/arm_symbolic_flow.py` acompanha enderecos conhecidos
pelos desvios diretos `B` e condicionais ARM suportados e reune estados
mantendo somente constantes iguais em todos os caminhos identificados.

O comando `python3 tools/inspect_tictactoe_memory.py` aplica essa
analise ao executavel ARM compilado do jogo da velha para tentar reconhecer
tanto leituras quanto gravacoes ligadas ao simbolo `board`.
`board_base_dynamic_index` significa base conhecida e indice incerto;
**nao prova qual casa do tabuleiro foi acessada**.

Esta etapa ainda nao rastreia enderecos por todos os modos ARM nem gera
codigo C++ equivalente.

## Evidencias da rotina play() ARM32

O modulo `tools/arm_play_evidence.py` inspeciona comparacoes, desvios
e acessos indexados no binario ARM32 do jogo da velha. O relatorio
`python3 tools/inspect_tictactoe_memory.py` agora inclui um esboco
comentado com os papeis candidatos de `R0` (posicao) e `R1` (jogador).

Esses papeis sao hipoteses fundamentadas na convencao de chamadas e
nos operandos. As condicoes exatas e a equivalencia com C++ ainda nao
estao demonstradas.

## Teste experimental de reconstrucao de play()

`python3 tools/validate_play_reconstruction.py` compila o jogo original ARM
para extrair evidencias, gera um **candidato C++ por regras** a partir dessas
evidencias, compila o candidato para ARM32 e compara a execucao nativa do
candidato com a funcao C original. O teste enumera os `3^9` tabuleiros,
13 posicoes de -2 a 10 e 3 valores de jogador (767.637 casos). Verifica tanto
o retorno quanto todas as 9 casas apos a chamada.

O gerador agora extrai do ARM os valores da comparacao de posicao, a
comparacao com zero, o retorno de rejeicao e a referencia a `winner()`.
Contudo, a assinatura C++, a estrutura do algoritmo e a implementacao de
`winner()` continuam fornecidas pelo modelo de sintese. Por isso, mesmo com
comportamento identico no teste, nao representa decompilacao autonoma.
O relatorio fica em `results/play_reconstruction_test.json` no CI como
artefato e especifica as hipoteses nao inferidas. O candidato **nao e
comparado byte a byte** com a funcao ARM original.

## Execucao diferencial ARM32 sob QEMU

O teste `python3 tools/validate_play_arm_emulation.py` compila
**ambas** as implementacoes (a funcao original em C e o candidato gerado
em C++) para Linux ARM32 e executa o comparador sob `qemu-arm`.
Compara retorno e as 9 posicoes do tabuleiro em 767.637 entradas.

Requisitos adicionais: `qemu-user`, `gcc-arm-linux-gnueabihf` e
`g++-arm-linux-gnueabihf`. O relatorio aparece em
`results/play_arm_emulation.json` como artefato do CI.

A estrutura do candidato e a funcao `winner()` ainda sao compartilhadas
ou fornecidas pelo gerador; o teste mede equivalencia nos casos executados,
**nao recuperacao exata do codigo original**.

## Emissor C++ dirigido por evidencias ARM

O modulo `tools/arm_cpp_emitter.py` monta instrucoes `if`, escrita
no tabuleiro e chamada de funcao usando as operacoes reconhecidas no ARM.
Ele rejeita padroes de leitura ou escrita que nao correspondam ao subconjunto
validado de `play()`. Os limites, comparacoes e valor de retorno sao
extraidos pelo modulo de inferencia ARM.

O resultado continua **limitado a um padrao conhecido**, com assinatura
C++ e estrutura de alto nivel predefinidas. Nao e ainda um descompilador
geral nem reconstrucao do codigo-fonte historico.

## Representacao intermediaria ARM (IR)

O modulo `tools/arm_ir.py` registra quatro operacoes tipadas do padrao
`play()`: guarda de limite, guarda de celula ocupada, gravacao
indexada e chamada final. O gerador transforma instrucoes ARM reconhecidas
em IR e depois em C++; o relatorio da comparacao guarda a IR emitida.
Esse subconjunto **nao** recupera funcoes ARM arbitrarias e continua
dependente da assinatura e do modelo de memoria especificos do exemplo.

## Conversao de instrucoes ARM para IR generica

O novo `tools/arm_ir_lifter.py` recebe um opcode ARM32 e seu endereco
e gera nos de IR para MOV imediato, ADD, SUB, CMP, B, BL e BX.
Condicoes e instrucoes desconhecidas recebem `unsupported` em vez de
uma interpretacao inventada. Isso e um primeiro passo para abandonar
o reconhecimento exclusivo de `play()`, nao um descompilador completo.

## IR com grafo de fluxo de controle ARM32

O modulo `tools/arm_ir_graph.py` integra o decodificador ARM32
existente ao grafo de fluxo de controle. Mantem enderecos, condicoes,
arestas de desvio, chamadas e operacoes nao reconhecidas. A API
`from_elf(bytes, entry)` produz uma IR limitada por orcamento de
instrucoes. Por enquanto, a IR do grafo **nao faz estruturacao
automatica de loops/ifs em C++**.

Os testes de regressao estao em `tests/test_arm_ir_graph.py`.
O GitHub Actions tem retornado falha sem etapas/logs disponiveis;
essa integracao ainda precisa de comprovacao no runner.

## Desvios de play() recuperados do jogo compilado

O analisador `tools/arm_compiled_branches.py` le instrucoes
desmontadas por LLVM e informa origem, condicao, caminho tomado e
caminho sequencial de desvios que permanecem dentro da funcao.
`tools/inspect_tictactoe_memory.py` anexa os candidatos ao relatorio
da funcao `play()`. Um teste compila o jogo e exige evidencias de
um desvio de igualdade. Isso nao prova automaticamente qual caminho
corresponde a uma jogada aceita ou rejeitada: para isso ainda faltam
analise semantica e associacao das instrucoes de retorno.

## Rastreio de resultados por caminho de play()

`tools/arm_play_paths.py` percorre os desvios condicionais presentes
na funcao compilada e assinala se cada caminho **pode alcancar**
uma gravacao no tabuleiro, a definicao do retorno -1, uma saida
por BX LR ou o salto para winner. O resultado aparece em
`path_events` no relatorio de `inspect_tictactoe_memory.py`.

Sao eventos possivelmente alcancaveis, nao provas de que a condicao
e suficiente para aceitar/rejeitar uma jogada: faltam condicoes de
caminho e estados dos registradores.

## Restricoes de caminho ARM32

`tools/arm_path_constraints.py` implementa uma exploracao limitada
de estados para `CMP registrador, imediato` com `BEQ`/`BNE`.
Ela conserva igualdades e exclusoes por registrador e elimina trajetorias
contraditorias. Escritas em registradores invalidam fatos dependentes
deles; desvios nao suportados mantem ambas as alternativas em vez de
inventar certezas. O relatorio do jogo compilado inclui
`path_constraints` na funcao `play()`.

**Escopo:** apenas comparacoes imediatas EQ/NE com semantica parcial.
Nao prova todos os caminhos ARM32 nem a equivalencia de codigo gerado.

## Intervalos unsigned recuperados do ARM32

`tools/arm_unsigned_paths.py` acompanha restricoes conservadoras
de `CMP registrador, #imediato` e desvios `BHI`/`BLS`.
No jogo da velha compilado, reconhece que `CMP R0, #8; BHI`
separa valores de `R0` em `0..8` e `9..4294967295`.
O relatorio de `play()` inclui `unsigned_path_constraints`.

Os testes controlados passaram em ambiente local e o modulo foi
executado sobre um ELF ARM32 real. GitHub Actions continua com falha,
portanto a validacao integrada permanece pendente. A ferramenta nao
prova equivalencia completa nem recupera automaticamente qualquer funcao.

## Caminhos completos de play() validados em ARM32

`tools/arm_play_outcomes.py` combina o intervalo unsigned de `R0`,
o resultado da comparacao de uma leitura **com origem board comprovada**
e os pontos de escrita reconhecidos. Para o binario ARM32 de exemplo,
distingue tres saidas: posicao invalida retorna -1; posicao valida com
casa ocupada retorna -1; posicao valida com casa livre grava e salta
para `winner()`. Instrucoes desconhecidas geram evento nao suportado.

`tools/generate_play_candidate.py` recusa produzir C++ quando essas
tres categorias nao particionam corretamente o dominio reconhecido.
A evidencia local reproduzida esta em
`results/arm_play_outcomes_local_2026-10-12.json`: 13 estados da
analise de caminhos, 11 instrucoes ARM em `play()` e 767.637
comparacoes nativas de comportamento sem divergencias.

**Limites:** a semantica de caminho e especifica desse padrao,
o prototipo C++ e a funcao `winner()` continuam fornecidos,
a comparacao diferencial mais recente foi nativa (nao QEMU) e
os workflows do GitHub Actions ainda nao foram validados nesta versao.

## Reconstrucao experimental de winner() a partir do ARM32

O modulo `tools/recover_winner.py` le um ELF32 little-endian **compilado**,
recupera os bytes da tabela `winner.lines` diretamente da secao de dados
e verifica enderecos base `MOVW/MOVT`, as tres leituras do tabuleiro,
o limite do loop e o padrao booleano ARM produzido pelo Clang `-O1`.
Depois emite um candidato C++ sem ler o fonte original durante a geracao.

`tools/validate_winner_reconstruction.py` compila o candidato para ARM32,
e testa a versao nativa contra `winner()` original em 19.683 tabuleiros
ternarios, 65.536 casos deterministas de 32 bits e quatro casos extremos.
Na verificacao local: **85.223 casos, zero divergencias**, e quatro testes
de recuperacao/negativos aprovados. O CI reproduz esses passos quando houver
runner disponivel. O registro da verificacao local esta em
`results/winner_reconstruction_local_2026-10-12.json`.

**Limitacoes:** depende de simbolos ELF nao removidos (`board`,
`winner.lines`), do padrao de instrucoes ARM especifico do compilador e
de uma estrutura C++ de alto nivel conhecida. Equivalencia testada em
execucao **nativa**; nao sao bytes identicos, nem validacao QEMU deste
candidato. Nao e um descompilador geral.

## Recuperacao de `winner()` em ELF ARM32 sem simbolos

O novo `tools/recover_winner_stripped.py` identifica o padrao compilado
da rotina pelo disassembly ARM, reconstrói os enderecos da tabela e do
tabuleiro com `MOVW/MOVT` e resolve seus bytes pelos segmentos
`PT_LOAD` do ELF. **Nao exige nomes de simbolos**, nem um endereco
fixo para a funcao ou a tabela. Os testes incluem um ELF relinkado
com `-Ttext=0x5000` e um ELF sem tabela de simbolos.

Para reproduzir:

```bash
python3 -m unittest discover -s tests -p 'test_recover_winner_stripped.py' -v
python3 tools/validate_winner_reconstruction.py --strip
```

Validacao local: **6 testes de recuperacao aprovados** e **85.223**
comparacoes nativas entre `winner()` original e o candidato C++
obtido do ELF stripped, sem divergencias. O candidato tambem foi
compilado para ARM32; nao foi executado sob QEMU nessa rodada.
A evidencia esta em `results/winner_stripped_local_2026-10-12.json`.

**Escopo:** ainda reconhece um fingerprint especifico do Clang ARM32
`-O1`, requer cabecalhos ELF com segmentos carregaveis e fornece
um esqueleto C++ baseado em semantica previamente reconhecida.
Nao extrai fontes arbitrarios de executaveis comerciais.

## Reconstrucao de winner() sob cinco otimizacoes ARM32

`tools/recover_winner_variants.py` reconhece **cinco configuracoes do
Clang ARM32** em ELF sem simbolos: `-O1`, `-O2`, `-O3`, `-Os`
e `-Oz`. Os padroes possuem diferencas materiais:

- `-O1`: laço com verificacao XOR/CLZ;
- `-Os`: laço compacto com comparacoes CMP/CMPEQ;
- `-Oz`: laço com ponteiros obtidos via literais PC-relativos;
- `-O2/-O3`: laço desenrolado em 24 leituras diretas do tabuleiro,
  sem tabela explicita no binario.

A ferramenta valida acessos e desvios antes de emitir o esqueleto C++.
Cada compilacao foi testada tambem com o codigo movido para `0x5000`,
sem fixar os enderecos do ELF original. Testes de corrupcao garantem
rejeicao de instrucoes nao suportadas.

Para reproduzir a bateria, com Clang, LLD, LLVM objcopy/objdump
disponiveis:

```bash
python3 -m unittest discover -s tests -p 'test_recover_winner*.py' -v
python3 tools/validate_winner_variants.py --output results/winner_variants_validation.json
```

Resultado local: **16 testes de recuperacao passaram**, considerando
os testes anteriores e os novos. Os cinco candidatos recompilados para
ARM32 passaram em **426.115 comparacoes comportamentais nativas**
(85.223 cada), **zero divergencias**. Evidencias:
`results/winner_variants_validation_local_2026-10-12.json`.

**Escopo real:** apenas padroes deste jogo gerados por **Clang**. Nao
ha validacao com GCC ARM, executavel arbitrario ou QEMU desta
versao. Estrutura e prototipo C++ sao reconhecidos por regras, nao
recuperados genericamente. GitHub Actions continua sem resultado de
job verificavel; testes locais sao independentes desse CI.

## Execucao ARM32 real sob QEMU e verificacao GCC

`tools/validate_winner_qemu.py` prepara um teste **real ARM32 Linux**:
recupera `winner()` de cada ELF Clang sem simbolos,
compila a implementacao original e o candidato com
`arm-linux-gnueabihf-gcc/g++`, liga o harness como binario ARM32
estatico e executa as **85.223 comparacoes por variante** sob
`qemu-arm`. O comando tambem tenta extrair a rotina de um ELF
compilado pelo proprio GCC, reportando `recognized`,
`unsupported_gcc_pattern` ou `gcc_probe_failed` separadamente.
Executar o codigo de ambos com GCC **nao significa** que a ferramenta
conseguiu descompilar o codigo produzido pelo GCC.

Em Ubuntu/Debian com os repositorios de pacotes habilitados:

```bash
sudo apt-get install clang lld llvm qemu-user gcc-arm-linux-gnueabihf g++-arm-linux-gnueabihf
python3 tools/validate_winner_qemu.py --output results/winner_qemu_arm32.json
```

O workflow `reverse-arm-reference.yml` executa automaticamente esse
comando e tenta publicar `results/winner_qemu_arm32.json`.
O workflow independente `.github/workflows/winner-arm32-qemu.yml`
tenta o mesmo teste em um job isolado, sem depender da bateria geral.
A tentativa mais recente desse workflow retornou falha **sem etapas
registradas**, portanto nao prova que QEMU realmente executou.
**Situacao verificada em 12/10/2026:** o ambiente local possui
Clang/LLVM, mas **nao possui QEMU nem GCC ARM**; o programa termina
com erro explicito, sem falsificar sucesso. O CI do GitHub continua
reportando falha sem etapas/logs acessiveis pela integracao. O teste
ARM32 sob QEMU **ainda nao foi concluido** nesta etapa.

Os resultados efetivamente reproduzidos no ambiente local foram:
**16 testes de recuperacao + 3 testes de contrato aprovados**,
compilacao real de um objeto ARM32 e **426.115 comparacoes nativas
sem divergencias**. Evidencia:
`results/winner_qemu_readiness_2026-10-12.json`.

## ARM32 sem GCC, sem libc, com executavel estatico real

O script `tools/validate_winner_freestanding.py` compila
`winner()` original e seu candidato C++ usando apenas **Clang + LLD**,
sem sysroot ARM, libc ou GCC. O harness C++
`tests/winner_freestanding_arm.cpp` usa as syscalls Linux ARM32
`write` e `exit` via `svc #0` e executa os mesmos 85.223 casos
por variante, quando ha `qemu-arm`.

O modo somente de compilacao valida o ELF32 `ET_EXEC`, a arquitetura
ARM e a ausencia de interpretador dinamico. Ele produz SHA-256 de
cada binario e, opcionalmente, salva cinco ELF prontos para execucao:

```bash
python3 tools/validate_winner_freestanding.py \
  --output results/winner_freestanding_arm32.json \
  --save-runners results/arm32_binaries
```

Para **exigir execucao ARM32 real**:

```bash
python3 tools/validate_winner_freestanding.py \
  --require-qemu --save-runners results/arm32_binaries
```

Validaçao local em 12/10/2026: **5 binarios ARM32 reais compilados**,
3 testes do validador aprovados, **0 casos QEMU executados** (emulador
ausente). O comando com `--require-qemu` falha explicitamente se
nao houver emulador. Evidencia com hashes:
`results/winner_freestanding_arm32_local_2026-10-12.json`.
O workflow `winner-arm32-qemu.yml` usa esse teste, instala apenas
Clang/LLVM/QEMU e publica os arquivos ELF quando executado.

## Winner: teste diferencial ampliado (2026-10-12)

O reconstrutor existente identifica `winner()` a partir de um ELF ARM32, inclusive
sem simbolos, nos niveis Clang `-O1/-O2/-O3/-Os/-Oz`. O gerador continua
limitado aos padroes de instrucoes comprovados, **nao e descompilacao generica**.

A suite nativa agora cobre **262.144** tabuleiros de quatro valores cada,
**65.536** tabuleiros com inteiros aleatorios deterministas e **4** casos
extremos: **327.684 casos por configuracao**. Um teste local com o
binario `-O1` resultou em **zero divergencias**; o C++ tambem compilou
para ARM32. O verificador independente `tools/reconstruct_winner.py`
confere a tabela de `.rodata`, os desvios e a sequencia completa
de instrucoes desse padrao e recusa alteracoes nao suportadas.

Evidencia: `results/winner_extended_local_2026-10-12.json`.
Os workflows do GitHub Actions continuam falhando sem etapas
disponiveis; **a nova rodada de cinco otimizacoes e o QEMU ainda
nao tiveram conclusao confirmada nesta revisao**.

## winner(): terceira verificacao independente do ELF (2026-10-12)

O verificador adicional `tools/arm_winner_reconstruct.py` interpreta
o ELF32 com `struct`, extrai os 24 bytes da tabela `winner.lines`
e confere a sequencia ARM32 de 29 instrucoes, os ponteiros MOVW/MOVT,
o limite do loop e os acessos a memoria. Nao usa a tabela C original
na geracao e rejeita modificacoes nao reconhecidas, incluindo indice
fora de faixa e limite do loop adulterado.

`tools/validate_winner_reconstruction.py` confronta os dados desse
terceiro verificador com os dois verificadores existentes no modo O1.
`tests/test_arm_winner_reconstruct.py` cobre ELF real e dois casos
adulterados. Em execucao local, os tres testes passaram e um C++
candidato dessa etapa compilou para ARM32. A comparacao nativa do
candidato com a implementacao C original passou em **327.684 estados**
(262.144 tabuleiros enumerados + 4 extremos + 65.536 aleatorios),
sem divergencias.

**Limites:** nao e descompilador generico; o modo novo verifica
apenas o padrao ARM32 Clang O1 reconhecido. C++ de alto nivel e
prototipo continuam previstos por um molde. A rodada acima nao
executou QEMU e nao representa aprovacao do GitHub Actions.

## IR estrutural de laços ARM32 (2026-10-12)

O novo `tools/arm_loop_analysis.py` identifica **laços naturais por dominadores**
e arestas de retorno em qualquer função ARM32 selecionada no ELF, sem
regras específicas do jogo da velha. Registra entradas, saídas, candidatos
a contadores, leituras e escritas indexadas, inclusive endereçamento
pós-indexado (`LDR R3, [R2], #4`). O relatório de
`tools/inspect_tictactoe_memory.py` passa a incluir
`control_flow_structure` para `winner`, `play` e `start`.

A implementação foi testada localmente em **9 cenários, 9 aprovados**,
incluindo um segundo programa ARM32 real (`examples/reverse/array_sum.c`),
laços aninhados e rejeição de laços falsos. Um confronto de cinco variantes
Clang 17 do jogo registrou 1 laço em `-O1`, `-Os` e `-Oz`, e nenhum em
`-O2`/`-O3`, pois essas otimizações expandiram o laço em código sem
aresta de retorno. Evidências e hashes dos ELFs estão em
`results/arm_loop_variants_local_2026-10-12.json`.

**Limites:** detectar um laço de máquina não é reconstruir seu `for`
original. Valores dos registradores, aliasing, laços irreduzíveis e
reconhecimento sem nome/limite da função ainda exigem novas etapas.
Esta rodada testou ELFs ARM32 locais, sem executar ARM sob QEMU; o
GitHub Actions ainda precisa de validação independente.

## Reconvergencia generica de caminhos ARM32 (2026-10-12)

`tools/arm_loop_analysis.py` agora exporta o grafo de controle
alcancavel, as arestas tipadas e os pontos de saida. O novo
`tools/arm_control_regions.py` usa pos-dominadores compactados
em bitsets para diferenciar bifurcacoes que se reencontram
daquelas cujos caminhos seguem ate saidas diferentes.

No ELF ARM32 compilado de jogo da velha, o verificador estrutural
local encontrou duas bifurcacoes de `winner()` com destino comum
`0x1070`, duas bifurcacoes de `play()` sem reconvergencia
intrafuncional e nenhuma em `start()`. Oito testes locais
passaram, incluindo grafo linear de 3.000 nos, ciclos sem saida,
retorno condicional e fluxo indireto desconhecido.

Arquivo: `results/arm_control_regions_local_2026-10-12.json`.
Os testes de integracao estao em `tests/test_arm_control_regions.py`
e o workflow salva `arm_winner_regions_latest.json` e
`arm_play_regions_latest.json` quando conseguir executar.

**Limite:** analise de estrutura estatica, nao equivalencia C++
nem prova de que o programa encerra; GitHub Actions continua
sem validacao completa nesta revisao.

## Qual é o próximo objetivo?

Ampliar o decodificador ARM/Thumb-2, reconhecer os limites reais das funções e validar os mapas de chamadas em binários ARM reais. A ferramenta `arm_functions.py` gera **candidatos** a partir de chamadas diretas ARM32 `BL` e Thumb-2 `BL`/`BLX` imediato, mas não cobre instruções Thumb-2 em geral, chamadas indiretas, mudanças dinâmicas de modo nem limites completos das funções. Depois, avançar para pseudocódigo e reconstrução verificável em C/C++.

## E a IA?

A EdgeAI possui um runtime local escrito em **C++17**, com ferramentas determinísticas e um pequeno backend neural. O perfil experimental v0.16 mira até **64 MiB de RAM** em uma carga de teste Linux, modelo de até **16 MiB** e **1 a 2 threads**. São metas de um perfil específico, não garantias para qualquer computador.

Na avaliação registrada, as ferramentas determinísticas acertaram **20/20** tarefas, enquanto o modelo neural de desenvolvimento obteve **0/20** respostas consideradas úteis. Portanto, **a IA ainda não realiza engenharia reversa autonomamente**.

Para compilar o runtime:

```bash
cmake -S . -B build-low -DCMAKE_BUILD_TYPE=Release -DEDGEAI_LOW_RESOURCE=ON -DEDGEAI_BUILD_TESTS=ON -DEDGEAI_BUILD_BENCHMARK=OFF
cmake --build build-low -j2
ctest --test-dir build-low --output-on-failure
```

## Documentação

- [Limites do analisador ELF](docs/elf-inspection.md)
- [Runtime de baixo consumo](docs/low-resource-runtime.md)
- [Metas técnicas](METAS.md)
- [Histórico de alterações](CHANGELOG.md)

**Resumo:** a EdgeAI está construindo os fundamentos para automatizar a engenharia reversa em PCs fracos. As ferramentas atuais produzem análises estáticas iniciais; a compreensão automática e a reconstrução completa ainda são objetivos em desenvolvimento.
