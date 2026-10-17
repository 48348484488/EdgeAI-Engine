## Atualização: 14 funções (16/10/2026)

A EdgeAI agora emite C++ para **14/23 funções nomeadas do jogo (60,87%)**:
**442 slots ARM64 traduzidos**, 14 candidatos de 27 e 13 rejeições declaradas.
A geração recebeu **somente o ELF AArch64 stripped**, revisão upstream
`53f4da8249cbe9bce17e0daefbd7903f4a4684be`,
SHA-256 `a3ca49d16ca6428291574ebd3f7c54153ef0913f8aa1eee4279408c3bf9d499b`.

A nova rotina reconstruída é a de instruções de interface
`0x401484` (nome `print_indicators` conferido somente **depois** da
reconstrução): **92 instruções**, 18 chamadas de impressão e 126 bytes
de saída nativa comparados com um programa C original independente,
**sem divergências**. SHA-256 de ambas as saídas:
`efe0f74688616d2beff9ec51022e0a68bb849c6c5269bdf4f9388f04a31be559`.

O novo [tradutor de impressão estática](../tools/aarch64_static_printf_sequence_lifter.py)
usa `.rodata`, `ADRP/ADD`, imports dinâmicos `__printf_chk@plt`,
registradores AAPCS64 preservados entre chamadas e formatos seguros,
inclusive `%*s`. Recusa branches, argumentos não constantes,
frames desbalanceados e chamadas não suportadas. O módulo foi integrado
ao [pipeline de múltiplas passagens](../tools/aarch64_multistage_batch.py)
**sem uma tabela de endereços conhecidos do 2048**.

Também reexecutei **1.200.088 casos anteriores** com a biblioteca de 14 funções,
sem diferenças, e **53 testes de regressão**, todos aprovados; corrigi a
referência de arquivo C usada por um teste no ZIP anterior. O programa de
referência da nova função é mantido em
[`tests/oracles/2048_indicators_oracle.c`](../tests/oracles/2048_indicators_oracle.c)
com licença MIT, isolado do processo de geração.
[Resultado completo em JSON](../results/blind_2048_fourteen_function_reconstruction_2026-10-16.json).

**Limitações:** ainda faltam **9 funções nomeadas**. As saídas de impressão
têm amostras determinísticas, não milhares de execuções distintas.
As assinaturas de chamada são hipóteses de ABI, e nem a lógica de terminal
interativa nem o executável inteiro foram reconstruídos. O percentual indica
**quantidade de funções**, não cobertura de programa nem identidade com
o código-fonte original. O Ghidra não foi usado nessa reconstrução.

---

## Atualização confirmada: 13 funções do 2048 (16/10/2026)

A ferramenta [`aarch64_printf_lifter.py`](../tools/aarch64_printf_lifter.py)
adicionou reconstrução **limitada e verificável** de rotinas ARM64 que chamam
`__printf_chk`: lê formatos e textos da seção `.rodata` no próprio ELF,
resolve o símbolo dinâmico no PLT e interpreta `ADRP+ADD`/argumentos
constantes. Rejeita especificadores não modelados, saltos, frames de pilha
incompatíveis e endereços fora da região. **Não recebe fonte original nem
tabela de símbolos do jogo**; nomes dos símbolos importados da libc
continuam disponíveis no ELF stripped.

A análise em lote [`aarch64_multistage_batch.py`](../tools/aarch64_multistage_batch.py)
passou de 11 para **13 arquivos C++ gerados e compilados**, dentre 27 entradas
candidatas. Isso corresponde a **13 das 23 funções nomeadas do jogo (56,52%)**,
com **350 instruções ARM64 traduzidas**. A biblioteca com as 13 foi ligada
sem erros.

As duas novas funções têm saída fixa, portanto sua validação não é contada
como milhares de casos:

| Endereço | Nome descoberto após geração | Instruções | Saída validada |
|---|---|---:|---|
| `0x4015f4` | `print_win` | 23 | 27 bytes iguais à referência |
| `0x401650` | `print_game_over` | 23 | 27 bytes iguais à referência |

O teste compilou as duas definições C originais com os macros MIT do jogo,
em programa independente **depois** de gerar o C++. Também recompilou
um único executável com todos os 13 candidatos e repetiu a comparação de
saída. Os **1.200.088 testes diferenciais das 11 funções anteriores** foram
reexecutados contra a nova biblioteca com zero divergências. **Dezenove
testes de regressão** passaram, incluindo mutação de string na seção
`.rodata`, rejeição de `%n` e endereços inválidos.

[Relatório JSON](../results/blind_2048_thirteen_function_reconstruction_2026-10-16.json)
e [testes desta expansão](../tests/test_aarch64_printf_lifter.py).
Para executar os testes de integração com o ELF real, definir
`EDGEAI_BLIND_2048_ELF` para o ELF stripped e instalar `llvm-objdump`
e `g++`.

**Ainda faltam 10 funções nomeadas** para a meta de reconstrução
funcional completa. Elas requerem operações de pilha, dados temporários,
importações, chamadas e I/O não cobertos por esses tradutores.
As assinaturas são hipóteses e a cobertura percentual é exclusivamente por
contagem de funções; o jogo como programa completo **não foi recompilado**.

---

# EdgeAI — teste cego de engenharia reversa do jogo externo 2048-cli

Última atualização: 16 de outubro de 2026.

## Proveniência e separação do código-fonte

- Jogo escolhido externamente: [Frost-Phoenix/2048-cli](https://github.com/Frost-Phoenix/2048-cli), licença MIT.
- Revisão exata do jogo: `53f4da8249cbe9bce17e0daefbd7903f4a4684be`.
- [Compilação pública ARM64 concluída no GitHub](https://github.com/48348484488/oxide/actions/runs/38969071956); apenas a ramificação isolada `edgeai-blind-2048-experiment`, sem alterações na `oxide/main`.
- SHA-256 do ELF ARM64 **sem símbolos**: `a3ca49d16ca6428291574ebd3f7c54153ef0913f8aa1eee4279408c3bf9d499b`.
- O programa que gera C++ lê apenas o ELF sem símbolos e sua desmontagem LLVM. Não consulta o arquivo com símbolos nem o código-fonte original, que são utilizados **somente depois** da geração, na validação.
- As assinaturas de funções são **hipóteses de ABI**: ponteiros para 16 palavras, score e/ou índice de coluna. O tradutor não recuperou os tipos originais nem nomes das funções.

## Resultado real em 16/10/2026

| Métrica | Resultado |
|---|---:|
| Instruções de 4 bytes na seção executável `.text` | 1.074 |
| Candidatos a entrada de função descobertos no ELF sem símbolos | 27 |
| Funções nomeadas do jogo conferidas *após* geração por oráculo | 23 |
| Entradas identificadas entre essas funções | 23/23 |
| **Funções C++ recompiladas e diferencialmente validadas** | **11/23** |
| Cobertura por contagem de funções | **47,83%** |
| Instruções ARM64 das 11 funções traduzidas | 304 |
| Comparações por comportamento em biblioteca C++ nativa | **1.200.088** |
| Divergências detectadas nas amostras | **0** |
| Testes de regressão adicionais do tradutor | **9 aprovados** |
| Candidatos ainda sem tradutor compatível | **16 de 27** |

### Funções — nomes conhecidos apenas na validação

| Endereço | Função original (oráculo posterior) | Instruções | Comparações |
|---|---|---:|---:|
| `0x4009e8` | `_slide_col` | 53 | 100.008 |
| `0x400abc` | `_rotate_board` | 40 | 100.007 |
| `0x400b5c` | `_empty_cells_left` | 17 | 100.005 |
| `0x400ba0` | `_can_slide_up` | 23 | 100.005 |
| `0x400d58` | `board_can_move` | 27 | 100.007 |
| `0x400dc4` | `board_win` | 18 | 100.005 |
| `0x400e0c` | `board_move_up` | 23 | 100.008 |
| `0x400e68` | `board_move_down` | 20 | 100.008 |
| `0x400eb8` | `board_move_left` | 20 | 100.008 |
| `0x400f08` | `board_move_right` | 20 | 100.008 |
| `0x400f58` | `_get_color` | 43 | 200.019 |

As comparações abrangem o valor de retorno, as **16 casas do tabuleiro** e a pontuação, quando aplicáveis. A ferramenta gerou uma biblioteca C++ x86-64 a partir das instruções ARM64 desmontadas; as referências C compiladas separadamente foram consultadas depois. As comparações não equivalem à execução do aplicativo original nem comprovam equivalência para todas as entradas.

## Avanço técnico desta rodada

Adicionados três módulos:

1. [`aarch64_multimem_leaf_lifter.py`](../tools/aarch64_multimem_leaf_lifter.py) — tradução conservadora de funções com **dois buffers, escrita de memória, shifts, UBFIZ, SBFIZ, CMN e CSETM**, todos sob contrato de limites.
2. [`aarch64_move_caller_lifter.py`](../tools/aarch64_move_caller_lifter.py) — conversão de funções que chamam outras funções traduzidas; verifica prólogo/epílogo `STP/LDP` pareados e o papel de cada argumento.
3. [`aarch64_multistage_batch.py`](../tools/aarch64_multistage_batch.py) — percorre todas as entradas candidatas e reconstrói dependências em múltiplas passagens, até não surgirem novos módulos compatíveis. **Os endereços não são fixados no código.** São atribuídos contratos de chamada com base na categoria dos traduzidores que aceitaram cada função.

Nenhum tradutor utiliza o oráculo C. Todas as instruções desconhecidas, ramos fora do intervalo ou chamadas sem contrato são recusados, registrados como `UNSUPPORTED`. A geração de C++ não é automaticamente marcada como comportamento validado.

## Como reproduzir

Obter `2048-arm64-stripped.elf` do [artefato ARM64](https://github.com/48348484488/oxide/actions/runs/38969071956) e conferir o hash. Instalar Python 3, `llvm-objdump` e `g++`:

```bash
python3 tools/aarch64_multistage_batch.py 2048-arm64-stripped.elf --output-dir resultados/2048
```

O comando gera `coverage.json`, 11 arquivos `candidate_*.cpp` e, após compilação bem-sucedida, `recovered_candidates.so`. O validador posterior deve usar o código original em um processo **separado**. Para os módulos de teste do tradutor:

```bash
python3 -m unittest discover -s tests -p 'test_aarch64_multistage_regressions.py' -v
```

Relatório com funções/limites: [`results/blind_2048_eleven_function_reconstruction_2026-10-16.json`](../results/blind_2048_eleven_function_reconstruction_2026-10-16.json).

## Próximas funções e limitações

**Ainda restam 12 das 23 funções** do jogo sem reconstrução C++ validada, entre elas rotinas com stack frames complexos, arrays locais, chamadas de libc, aleatoriedade e interface de terminal. A próxima expansão deve modelar `SUB/ADD SP`, cópias de registradores de 64 bits, temporários na stack, destinos indiretos e efeitos de libc sob contratos verificáveis.

Recuperar 11 funções **não é descompilar todo o jogo**: o executável C++ completo não foi reconstruído; os recursos de jogo, o terminal e as interações reais permanecem ausentes. A taxa de 47,83% representa apenas contagem de funções nomeadas, não cobertura de bytes, lógica, nem uma garantia de equivalência universal.

O repositório privado EdgeAI teve execuções de Actions que falharam antes de obter runner; a compilação original foi confirmada por workflow no repositório público, enquanto a validação diferencial foi executada no ambiente local.
