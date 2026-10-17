# EdgeAI — execução do código original ARM64 e comparação por chamada

Data: 17/10/2026

## O que foi executado

O jogo externo [2048-cli](https://github.com/Frost-Phoenix/2048-cli), commit
`53f4da8249cbe9bce17e0daefbd7903f4a4684be` (MIT), foi
**compilado como ELF AArch64** e executado sob **QEMU ARM64 user mode**.
O executável original **sem símbolos de função** tem SHA-256:

`a3ca49d16ca6428291574ebd3f7c54153ef0913f8aa1eee4279408c3bf9d499b`

O mecanismo experimental `LD_PRELOAD` captura `__libc_start_main` antes do
loop interativo, chama os endereços extraídos do ELF conforme o **contrato ABI
assumido pelo tradutor**, e salva um hash após cada invocação. Isso executa
**instruções ARM64 reais do próprio ELF** sob emulação, e não um interpretador
inventado pela EdgeAI. A rotina de inicialização do aplicativo e o jogo como
processo completo não são reconstruídos por esse procedimento.

- [Execução original das 11 funções no GitHub Actions](https://github.com/48348484488/oxide/actions/runs/39042853626) — job **concluído com sucesso**
- Branch isolada `48348484488/oxide:edgeai-blind-2048-experiment`
- Código ARM64 real de teste:
  [`edgeai_probe/real_elf_aarch64_probe_v2.c`](https://github.com/48348484488/oxide/blob/edgeai-blind-2048-experiment/edgeai_probe/real_elf_aarch64_probe_v2.c)
- Contratos de ABI:
  [`edgeai_probe/abi_manifest_v2.json`](https://github.com/48348484488/oxide/blob/edgeai-blind-2048-experiment/edgeai_probe/abi_manifest_v2.json)
- [`tools/edgeai_qemu_casewise_compare.py`](../tools/edgeai_qemu_casewise_compare.py) — reproduz exatamente a entrada no C++ nativo
- [`tests/test_edgeai_qemu_casewise_compare.py`](../tests/test_edgeai_qemu_casewise_compare.py) — regressões e controle negativo
- [Resultados SHA-bound, por função](../results/2048_real_arm64_22000_casewise_2026-10-17.json)

## Métricas observadas

| Verificação | Resultado |
|---|---:|
| Entradas ELF reais, identificadas sem fonte | 11 |
| Invocações por entrada | 2.000 |
| **Comparações por chamada** | **22.000** |
| Prefixos FNV64 divergentes | **0** |
| Funções com comportamento divergente na amostra | **0** |
| Testes de regressão do comparador | **6 passaram**, nenhum falhou |

São verificados *inputs*, retorno de funções, as 16 palavras do tabuleiro e,
onde se aplica, coluna e pontuação. Também são comparadas as quatro funções
de movimento em diferentes direções. As entradas usam geração determinística
Xorshift32, posições de tabuleiro especiais e números pseudoaleatórios. Os
hashes são cumulativos, mas salvos **após cada chamada**, não somente uma vez
por função. O arquivo de entrada original contém **22.011 linhas**
(22.000 casos + 11 sumários).

### Controle negativo: a detecção de um erro real no tradutor

Altere propositalmente somente a saída C++ da função no endereço
`0x400dc4` para `return 0`, recompilando a biblioteca. A comparação
detectou **a primeira divergência no caso 2**: as 16 casas continham
`2048`. Os prefixos registrados foram:

- ELF ARM64 original: `5e9562ed97c30497`
- C++ adulterado: `930975f04977f706`

As outras dez funções permaneceram iguais na amostra. Isso demonstra que o
comparador **não aceita automaticamente qualquer código reconstruído**.
Ele informa a primeira entrada que reproduz a divergência, permitindo
executar somente esse caso com `QEMU -d cpu,exec`, GDB ou rastreamento
de memória no próximo ciclo.

## Reproduzir no PC

O artefato do GitHub contém `original_arm64_cases.txt`,
`original_machine_reference_v2.json` e o rastreio de instruções
`original_arm64_basic_blocks.txt`. O pacote completo de reprodução
da conversa reúne ainda o ELF original, a biblioteca C++ emitida,
manifesto, testes, controle negativo e hashes.

```bash
python3 tools/edgeai_qemu_casewise_compare.py \
  --machine-cases reference/original_arm64_cases.txt \
  --elf original/2048-arm64-stripped.elf \
  --manifest manifest/abi_manifest_v2.json \
  --library generated/recovered_candidates.so \
  --report casewise_result.json
```

Para executar os testes, extraia o bundle e defina
`EDGEAI_QEMU_V2_BUNDLE` para sua pasta raiz:

```bash
EDGEAI_QEMU_V2_BUNDLE="$PWD" python3 -m unittest \
  tests.test_edgeai_qemu_casewise_compare -v
```

## Limitações e próxima fase

**Este teste não adiciona novas funções ao decompilador.** Ele aumenta a
qualidade da validação independente para 11 funções já reconstruídas.

Hash FNV64 não é uma prova criptográfica de igualdade; colisões são
possíveis. A concordância em 22 mil invocações não comprova equivalência
universal, assinatura ABI original ou funcionamento integral do jogo.
As entradas amostradas também podem deixar ramos raros sem executar.

O próximo passo é executar **somente o primeiro caso divergente** com
rastreamento ARM64 de registradores `PC, SP, X0-X30, NZCV` e dos acessos
à memória, confrontando o estado com o interpretador de registradores da
EdgeAI. Isso permite diferenciar erro de semântica de instrução, assinatura
ABI incorreta e comportamento de biblioteca externa.
