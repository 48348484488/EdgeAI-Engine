# EdgeAI Engine

**Uma IA leve para ajudar na engenharia reversa de programas e jogos.**

O objetivo é analisar arquivos compilados, entender como o código funciona e, futuramente, ajudar a reconstruir funções equivalentes em C/C++. O projeto foi pensado para funcionar **localmente, sem GPU e com baixo consumo de recursos**.

> **Estado atual:** projeto experimental. Já existem ferramentas de análise de binários e um motor de IA compacto, mas **a reconstrução automática em C/C++ ainda não está pronta**.

### Integração com o Oxide ARM64 (análise estática, sem executar o jogo)

O analisador `tools/inspect_arm64_split.py` reutiliza o parser ELF da EdgeAI
para inspecionar, por streaming e mmap, `libil2cpp.so`, `libunity.so` e
`libloader.so` dentro de um split APK. Suporta arquivos de ate 320 MiB
por biblioteca, incluindo `libil2cpp.so` de 236 MB (acima do limite
do comando legado), sem carregar o binario inteiro na memoria Python.

Ele identifica arquitetura, simbolos nomeados que sobreviveram ao strip,
dependencias ELF `DT_NEEDED`, SONAME, tamanho e SHA-256. A
[validacao em CI](.github/workflows/oxide-arm64-elf-audit.yml) usa o
split ARM64 original do repositorio publico Oxide, confere seu hash
e publica JSON — **sem executar o jogo, desativar protecoes ou
inferir posicoes de jogadores**. Esses metadados nao equivalem a
decompilacao nem substituem o runtime Android.

### Argumentos de entrada ARM64 e comparações verificadas

`tools/aarch64_arg_guards.py` rastreia cópias conservadoras de `W/X0..7`
para registradores preservados `W/X19..28` e comparações com imediato
seguidas de `B.EQ` ou `B.NE`. Interrompe inferências quando um efeito
sobre o registrador é desconhecido, há escrita intermediária, desvio
incondicional ou entrada por salto no intervalo analisado.

Na [execução real #38570345080](https://github.com/48348484488/oxide/actions/runs/38570345080),
**59 testes passaram**. A EdgeAI encontrou em `UnityInitialize` original
a cadeia `MOV W21,W1` → `CMP W21,#0x2E0` → `B.NE`, indicando
uma comparação *candidata* do segundo argumento com **736**. A verificação
não determina a semântica desse valor, o caminho tomado, nem recupera
dados de jogador ou câmera.

### AArch64: mapeamento de desvios compilados

O utilitario `tools/aarch64_branch_map.py` localiza transferencias de controle
AArch64 (`B`, `BL`, `B.cond`, `CBZ`, `TBZ`, `RET`, `BR` e `BLR`) dentro
de uma funcao conhecida de biblioteca ELF64 no APK. Nao executa o jogo.
Ha testes reais de compilacao AArch64 em `tests/test_aarch64_branch_map.py`.

O adaptador no Oxide foi validado em runner publico sobre `JNI_OnLoad`
de `libloader.so`, encontrando 117 candidatos nos 4.524 bytes
indicados pelo simbolo. Isso nao prova semantica, alcançabilidade,
decompilacao nem descoberta de coordenadas de jogadores.

### Busca de simbolos da biblioteca IL2CPP ARM64

`tools/aarch64_symbol_triage.py` filtra, por substrings exatas
case-insensitive, **somente nomes STT_FUNC** preservados em ELF64, usando
streaming e `mmap`. Os testes AArch64 com compiler real e a leitura da
biblioteca IL2CPP do Oxide passaram no
[workflow #38563095341](https://github.com/48348484488/oxide/actions/runs/38563095341).
Nenhum dos 1.747 simbolos ELF tinha `player`, `camera`, `position` ou
`network` no nome; quatro resultados para `transform` pertencem ao
`std::__ndk1::collate` de C++. **Nao significa que a logica de
jogadores nao exista**, apenas que nao esta exposta com esses nomes.


### Validacao ARM64 contra quatro entradas reais do motor Unity

A EdgeAI executou seu parser, construtor de CFG e o comparador
`tools/aarch64_llvm_crosscheck.py` no pipeline publico do Oxide,
[execucao #38566956506](https://github.com/48348484488/oxide/actions/runs/38566956506).
**37 testes passaram**, com concordancia exata de endereco e classe de
instrucao nos **57/57** desvios/chamadas de quatro simbolos reais
de `libunity.so` (3 de UnitySendMessage, 32 de UnityInitialize,
5 de UnityShutdown e 17 de JNI_OnLoad).

A ferramenta `tools/aarch64_dispatch_bounds.py`, na
[execucao #38565737985](https://github.com/48348484488/oxide/actions/runs/38565737985),
identificou em `libloader.so` dois despachos com guarda local
`CMP/B.HI` e indice maximo 7. Nenhum desses resultados recuperou C++,
funcao de gameplay, posicao de jogador nem matriz de camera.

### ARM64: grafo e classificacao de saltos indiretos (sem execucao)

O modulo `tools/aarch64_cfg.py` transforma transferencias conhecidas em
**blocos e arestas candidatas**. `tools/aarch64_indirect_audit.py` compara
o resultado com um disassembly LLVM e reconhece o padrao exato
`ADR → LDRSW → ADD → BR`. O classificador **nao consulta tabelas de desvio
nem inventa alvos**.

No [workflow publico do Oxide #38562481574](https://github.com/48348484488/oxide/actions/runs/38562481574),
**18 testes passaram** e o `JNI_OnLoad` real de `libloader.so`
apresentou **117 instrucoes de controle conferidas com LLVM**,
**147 blocos**, **174 arestas**, **7 distribuidores indiretos por tabela**
e **1 chamada indireta**. Sao resultados de analise estatica do ELF,
nao de decompilacao autonoma nem de execucao do jogo.

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
intrafuncional e nenhuma em `start()`. Num ELF independente de
soma de vetor, `sum_array()` teve um desvio com saida antecipada
e outro que repete o laco, convergindo em `0x1020`. Oito testes locais
passaram, incluindo grafo linear de 3.000 nos, ciclos sem saida,
retorno condicional e fluxo indireto desconhecido.

Arquivo: `results/arm_control_regions_local_2026-10-12.json`.
Os testes de integracao estao em `tests/test_arm_control_regions.py`
e o workflow salva `arm_winner_regions_latest.json` e
`arm_play_regions_latest.json` quando conseguir executar.

**Limite:** analise de estrutura estatica, nao equivalencia C++
nem prova de que o programa encerra; GitHub Actions continua
sem validacao completa nesta revisao.

## IR estrutural inicial: if/else e lacos naturais (2026-10-13)

`tools/arm_structured_ir.py` combina os graficos de
`arm_loop_analysis.py` e os pos-dominadores de
`arm_control_regions.py` para gerar uma IR JSON independente
de nomes de funcoes, com nos `natural_loop`, `loop_branch`,
`if_else` (somente bracos simples, separados e com convergencia
demonstrada) e `exit_dispatch`. Condicoes sem prova, fluxos
indiretos desconhecidos e bifurcacoes complexas permanecem
`unstructured`, em vez de gerar C++ possivelmente incorreto.

Execucao: `python3 tools/arm_structured_ir.py jogo.elf
--function winner --output results/winner_structured.json`.

`tests/test_arm_structured_ir.py` valida grafos sinteticos,
aninhamento de lacos, caminhos sobrepostos e rejeicao de
evidencia alterada, alem de incluir um teste de integracao
que compila ARM32 do jogo da velha e de `array_sum` quando
Clang e llvm-objdump estiverem disponiveis.

Os **9 testes sinteticos** passaram no ambiente local, e ambos
os programas de referencia compilaram para ELF ARM32.
**A integracao da IR foi validada no GitHub Actions** no workflow
`ARM structured IR validation`, execucao
`38418077778` (conclusao `success`). Esse workflow compilou os
ELFs ARM32 e gerou relatorios de `winner`, `play` e
`sum_array`, publicados no artefato `edgeai-arm-structured-ir`.
O resultado rastreavel esta em
`results/arm_structured_ir_ci_2026-10-13.json`. O workflow legado
completo de engenharia reversa ainda tem incompatibilidades com
padroes de instrucoes LLVM usados nos validadores antigos. Esta etapa nao emite
codigo C++ executavel nem recupera condicoes de alto nivel.

## Efeitos ARM32 ligados a IR estruturada (2026-10-13)

`tools/arm_semantic_ir.py` adiciona instrucoes reconhecidas
(atribuicao, comparacao, aritmetica, shifts, desvios, leituras
e escritas em memoria) ao grafo estruturado. Cada efeito contem
o endereco ARM e os lacos/bracos condicionais associados.
Modos de enderecamento nao reconhecidos sao marcados
`unsupported`; enderecos de memoria **nao** significam que
a origem de um objeto tenha sido demonstrada.

Um teste local com uma copia de SHA Git identico ao modulo
publicado analisou as instrucoes ARM32 compiladas:
`winner()` 27/29 reconhecidas; `play()` 10/11;
`sum_array()` 10/11. O relatorio esta em
`results/arm_semantic_ir_local_2026-10-13.json`.
A suite automatizada adicional esta em
`tests/test_arm_semantic_ir.py` e foi incorporada ao
workflow `ARM structured IR validation`.

**Limites:** isso ainda nao realiza fluxo simbolico de
registradores ou geracao C++ equivalente. Na rodada de 13/10,
os jobs do GitHub falharam sem logs/etapas; nao ha aprovacao
integrada desta revisao. A versao anterior da IR estrutural
teve workflow aprovado em `38418077778`.

## Fluxo simbolico de registradores ARM32 (2026-10-13)

O modulo `tools/arm_register_flow_ir.py` conecta os efeitos
de instrucoes a arestas do CFG. Propaga origens de registradores,
constantes de 32 bits, somas/subtracoes e comparacoes `CMP`,
associando `BEQ`/`BNE` a expressao que alimenta os flags.
Na juncao de caminhos, conserva somente expressoes iguais;
escritas condicionais, chamadas e instrucoes desconhecidas
invalidam fatos nao comprovados. Loops usam ponto fixo
limitado, com teto de profundidade e de processamento.

**Validacao local:** 9 testes sinteticos passaram. ELF ARM32
compilado com a sequencia `ADD R1,R0,#1; CMP R1,#8;
BNE` confirmou a dependência simbolica `(R0 + 1) != 8`.
Tambem foram analisadas as funcoes reais `play` (11/11
instrucoes percorridas), `winner` (29/29) e
`sum_array` (11/11). O rastreio preservou a origem da
leitura de memoria no teste da casa em `play`.

A referencia reproduzivel esta em
`results/arm_register_flow_local_2026-10-13.json`.
O workflow independente da IR inclui agora
`tests/test_arm_register_flow_ir.py`, com teste de
compilacao ARM32 real. As execucoes desta revisao no
GitHub Actions terminaram sem etapas/logs; portanto a
suite **ainda nao esta aprovada no CI**.

**Limites:** condicoes simbolicas nao comprovam a
possibilidade de um caminho; nao ha rastreio completo de
memoria, semantica Thumb nem C++ gerado automaticamente.

## ARM32 flags: ADDS, SUBS, MOVS, LSRS e BHI (2026-10-13)

A IR de instrucoes `tools/arm_semantic_ir.py` agora reconhece
`ADDS`, `SUBS`, `MOVS`, `LSLS`, `LSRS` e `ASRS`.
`tools/arm_register_flow_ir.py` propaga o resultado de 32 bits,
deslocamentos, e a condicao `Z` produzida por essas instrucoes.
Consegue ligar comparacoes `CMP` com ramificacoes sem sinal
(`BHI`, `BLS`, `BCS`, `BCC`) e sinalizadas
(`BGE`, `BLT`, `BGT`, `BLE`) quando ambos os
operandos sao constantes comprovadas.

**Evidencia:** 23 testes locais passaram (9 de fluxo anteriores
+ 14 novos casos de flags). Um ELF ARM32 de referencia compilado
a partir de `examples/reverse/arm_flags_reference.S` verificou
tres guardas com 7/7 instrucoes reconhecidas cada: `SUBS/BEQ`,
`CMP/BHI` e `LSRS/BEQ`. Os desvios comprovados foram,
respectivamente, tomado, tomado e nao tomado. Os testes de
regressao do modulo estao em `tests/test_arm_flags_flow.py`.
O resultado local esta em
`results/arm_flags_validation_2026-10-13.json`.

**Limites:** o processamento de flags de `ADDS/SUBS/LSRS`
prova apenas a condicao zero para `BEQ/BNE`. Nao recupera
carry/overflow dessas operacoes; `BHI` e outros saltos
de magnitude so sao resolvidos a partir de `CMP` com
valores constantes. A rodada do GitHub Actions falhou
sem disponibilizar etapas, inclusive apos uma reexecucao,
logo a nova revisao ainda nao tem aprovacao completa no CI.

## Condicoes de lacos ARM32 recuperadas (2026-10-13)

`tools/arm_loop_predicates.py` vincula os lacos naturais da
IR ao desvio de retorno, ao produtor dos flags e a unica
atualizacao simples de um possivel contador. O relatorio
mostra acesso a memoria e arestas de saida antecipada,
preservando casos ambiguos como nao resolvidos.
A rotina integrada e `tools/arm_structured_ir.py`.

**ARM32 real testado localmente:**
- `winner()`: atualiza `r1 += 1`, compara `r1 != 8`
  e possui saida antecipada dentro do laco.
- `sum_array()`: usa `subs r1, r1, #1` e repete
  enquanto o resultado nao for zero.

O modulo publicado tem hash Git
`e11f6a5c3c648d602d4502f88873a92f0fc9854b`,
identico ao arquivo usado nos 3 testes locais aprovados.
O relatorio esta em
`results/arm_loop_predicates_local_2026-10-13.json`.
O conjunto novo de testes completos e
`tests/test_arm_loop_predicates.py`.

**Limites:** sao candidatos de contador, nao prova
de termino, quantidade de iteracoes ou C++ equivalente.
O workflow ARM estruturado foi atualizado, mas a execucao
`38432423641` nao passou e nao disponibilizou etapas de job
para diagnostico.

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
