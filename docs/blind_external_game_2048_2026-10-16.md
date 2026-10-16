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
