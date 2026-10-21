# EdgeAI — etapa V12: verificador ARM64 reutilizável

**Data:** 21/10/2026. **Estado:** implementação e reprodução local concluídas; **não** equivale à descompilação integral do jogo.

## O que foi concluído

Foi desenvolvido um único motor Python, independente de nomes do jogo, para interpretar instruções de um ELF AArch64 sem símbolos, operar sobre regiões de memória explicitamente declaradas e comparar os estados resultantes com registros reais do QEMU. A nova versão unifica o que antes exigia verificadores específicos para rotação e movimentação de coluna.

O subconjunto inclui operações de registradores, NZCV, branches, acessos `LDR/STR` com atualização de ponteiro, `STP/LDP` com verificação de restauração de `SP` e chamadas `BL` somente com callback de API explicitamente autorizado. Instrucões não suportadas e violações de memória, ABI, integridade ou orçamento produzem erro, não uma aproximação silenciosa.

## Dados verificados

| Medida | Resultado |
|---|---:|
| Entradas distintas de função | **5** |
| Entradas de teste obtidas em execuções QEMU anteriores | **50** |
| Comparações de PC | 3.748 |
| Comparações de registradores | 27.111 |
| Comparações de NZCV | 3.438 |
| Palavras finais de memória | 800 |
| Pontuações finais | 10 |
| Valores de retorno | 40 |
| **Total de verificações** | **35.147** |
| **Divergências** | **0** |
| **Testes automatizados** | **20/20** |

As cinco entradas são `0x4009e8`, `0x400abc`, `0x400b5c`, `0x400ba0` e `0x400dc4`. Não são cinco novas funções decompiladas: eram funções previamente recuperadas, agora verificadas por **um mesmo motor**. O código-fonte original não foi usado na geração; os contratos ABI são hipóteses explícitas.

**Integridade:** SHA-256 do ELF de 67.688 bytes: `a3ca49d16ca6428291574ebd3f7c54153ef0913f8aa1eee4279408c3bf9d499b`. Os 100 registros de evidência foram fixados individualmente no manifesto. O testador foi extraído e reexecutado em uma pasta temporária limpa, com os mesmos resultados.

## Reprodução

Foi criado o arquivo de distribuição `EdgeAI_ARM64_Verificador_Unificado_5_Funcoes.zip`, anexado à conversa do ChatGPT. Ele contém o módulo fonte `tools/edgeai_arm64_trace_vm.py` (SHA-256 `cff5cd0059f17f2683ee2861ddc8e90cfa8b0e977cd58ad469d72203939c9b10`), os testes, os dados da CPU, o ELF e o manifesto. Para reproduzir, na pasta extraída, com Python 3 e llvm-objdump:

```bash
python3 tools/edgeai_arm64_trace_vm.py --manifest replay_manifest.json --elf original/2048-arm64-stripped.elf --qemu-root qemu --report result.json
python3 -m unittest discover -s tests -p 'test*.py' -v
```

O [relatório JSON](../results/2048_unified_aarch64_real_qemu_5_functions_2026-10-21.json) registra os mesmos resultados.

## Procedência das capturas QEMU

- [Rotação no QEMU #39662231398](https://github.com/48348484488/oxide/actions/runs/39662231398)
- [Movimentação de coluna no QEMU #39663881109](https://github.com/48348484488/oxide/actions/runs/39663881109)
- [Duas funções de leitura no QEMU #39045208136](https://github.com/48348484488/oxide/actions/runs/39045208136)
- [Detecção de vitória no QEMU #39045208145](https://github.com/48348484488/oxide/actions/runs/39045208145)

**Nota de precisão:** essas capturas foram obtidas anteriormente; esta etapa reproduziu a interpretação e a comparação localmente. O módulo Python completo e seus dados estão no ZIP da conversa, enquanto este commit registra a documentação e os resultados no GitHub. Não há alegação de suporte a CPU ARM64 completa, chamadas arbitrárias de libc nem reconstrução do aplicativo original.
