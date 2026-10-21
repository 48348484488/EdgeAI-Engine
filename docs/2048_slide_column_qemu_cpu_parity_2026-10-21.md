# EdgeAI — paridade do estado da CPU ARM64 na movimentação de coluna

Data: 21/10/2026. Continuação do teste cego com o jogo externo [2048-cli](https://github.com/Frost-Phoenix/2048-cli), revisão MIT `53f4da8249cbe9bce17e0daefbd7903f4a4684be`.

## Teste real executado

O ELF Linux AArch64 **original e sem símbolos** (SHA-256 `a3ca49d16ca6428291574ebd3f7c54153ef0913f8aa1eee4279408c3bf9d499b`) foi carregado pelo **QEMU ARM64**, não por uma simulação inventada pela EdgeAI. Uma biblioteca AArch64 de sondagem, compilada separadamente e injetada via `LD_PRELOAD`, chamou o endereço `0x4009e8` com tabuleiro de 16 palavras, coluna e ponteiro para pontuação, gravando resultados e estados `PC, X0-X30, PSTATE` sob `-singlestep -d cpu,in_asm`.

- [Workflow GitHub Actions aprovado](https://github.com/48348484488/oxide/actions/runs/39663881109)
- [Código do probe original](https://github.com/48348484488/oxide/blob/edgeai-blind-2048-experiment/edgeai_probe/arm64_targeted_slide_column_trace.c)
- [Workflow reproduzível com hash fixo](https://github.com/48348484488/oxide/blob/edgeai-blind-2048-experiment/.github/workflows/edgeai-slide-column-cpu-trace.yml)
- [Manifesto resumido e números auditados](../results/2048_slide_column_real_qemu_cpu_parity_2026-10-21.json)

A EdgeAI decodificou as **53 instruções** de `0x4009e8` até `0x400abc` com `llvm-objdump`; um interpretador pequeno e restritivo registrou a evolução de registradores, desvios e flags sem consultar o original C nem a tabela de símbolos de jogo. Erros de instrução, acesso fora dos limites e desvio para endereço desconhecido causam rejeição, não aproximação.

## Resultados medidos

| Comparação | Aprovadas |
|---|---:|
| PC nas dez execuções | 641 |
| Registradores definidos X0-X30 | 7.196 |
| Flags NZCV | 571 |
| Memória final do tabuleiro (16 palavras × 10 casos) | 160 |
| Pontuação final | 10 |
| Retorno da função | 10 |
| **Total** | **8.588** |

**Nenhuma divergência** nas dez entradas testadas. O C++ anteriormente reconstruído foi invocado com essas mesmas entradas e também coincidiu nos 16 elementos do tabuleiro, pontuação e retorno. Separadamente, **3.000 tabuleiros adicionais** foram comparados entre o interpretador das instruções ELF e o C++ já gerado, sem diferenças; **8 regressões passaram**.

Controle negativo: converter `B.EQ` em `B.NE` em `0x400a90` produziu divergência verificável já no caso 1. Isso mostra que a verificação não declara sucesso para qualquer resultado.

## Reproduzir

O pacote completo desta execução, disponibilizado nesta conversa, contém o ELF sem símbolos, o módulo Python `edgeai_qemu_slide_cpu_parity.py`, a base `edgeai_qemu_rotate_cpu_parity.py`, as dez trilhas brutas do QEMU, os resultados de entrada/saída originais, a biblioteca C++ da EdgeAI e os oito testes.

```bash
python3 generate_verified_slide_report.py
python3 -m unittest -v test_edgeai_qemu_slide_cpu_parity.py
sha256sum -c SHA256SUMS
```

Dependência local: Python 3 e `llvm-objdump`. Para gerar novamente rastros da **execução original real**, rode o workflow GitHub Actions apontado acima. O ZIP auditado tem SHA-256 `0358c571f831db23d7bd1711f8f60a327b8e71a585d73b4bcc7c595d2003b02a`.

## Limites e próximo avanço

Não foi recuperada uma nova função: esta rodada elevou a confiança na função C++ já existente, mas a contagem de funções descompiladas **permanece igual**. Testar dez entradas não demonstra equivalência matemática em todas as possibilidades de 32 bits. Também não recupera protótipos, tipos ou nomes de fonte originais. A etapa mais valiosa a seguir é repetir as verificações sob outras opções de compilação, ampliar casos e generalizar o observador para funções com **pilha, chamadas externas e memória dinâmica**, em vez de depender de uma lista de endereços do jogo.
