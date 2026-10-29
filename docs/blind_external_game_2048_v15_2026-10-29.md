# EdgeAI V15 — 19ª função, estado global e prova ARM64/QEMU

**Data:** 29/10/2026. **Escopo:** jogo externo 2048, ELF AArch64 stripped fixado por SHA-256.

## Geração source-blind e testes locais

O pacote V15 gerou **19 arquivos C++** (752 instruções), incluindo o candidato `0x4012d0` (77 instruções), que usa estado persistente na `.bss`, `__printf_chk` e `__snprintf_chk`. A função foi identificada como `print_score` somente após a geração.

A reprodução local com `python3 tools/verify_2048_v15.py` (do pacote V15) compilou a biblioteca com 19 funções, comparou **259 sequências / 1.643 chamadas / 112.634 bytes** com um oráculo C compilado após a geração e encontrou **zero divergências**. Além disso, **79 testes** do diretório de análise e **8 testes** do novo lifter passaram nesta execução. Isso por si só não seria prova de execução ARM64.

## Prova nova: executável ARM64 original

A [execução pública #40817479109](https://github.com/48348484488/last-Island-of-survival-lite/actions/runs/40817479109) foi **aprovada** em 29/10/2026. O workflow baixou o ELF ARM64 original, verificou seu SHA-256, compilou um shim AArch64 e invocou diretamente a rotina original sob `qemu-aarch64`, preservando o estado global entre chamadas.

Foram **20 sequências / 179 chamadas / 11.914 bytes de stdout**, com **20 hashes SHA-256 idênticos** aos resultados previamente fixados do C++ gerado do ELF. Não houve divergências. Os arquivos brutos e o relatório foram publicados como artifact `edgeai-v15-original-arm64-score-parity` na execução.

- ELF SHA-256: `a3ca49d16ca6428291574ebd3f7c54153ef0913f8aa1eee4279408c3bf9d499b`
- C++ gerado SHA-256: `b43bba39aeafbb9375be3f852e16e801b15ed59c32d069b25874386eb66337c5`
- [Shim ARM64](https://github.com/48348484488/last-Island-of-survival-lite/blob/edgeai-blind-2048-experiment/edgeai_probe/v15_original_score_probe.c)
- [Casos fixados](../benchmarks/2048_v15/score_cases.tsv)
- [Verificador independente](../tools/verify_2048_v15_qemu_parity.py)

O primeiro teste [#40817418577](https://github.com/48348484488/last-Island-of-survival-lite/actions/runs/40817418577) falhou porque o ELF baixado não tinha permissão de execução. O [commit 2825f43](https://github.com/48348484488/last-Island-of-survival-lite/commit/2825f4360650006351a863665e3855aa95c88626) adicionou `chmod +x`, e o novo teste passou.

## Limites e pendências

**Cobertura observada em testes:** 19/23 funções nomeadas do 2048 (82,61%), com a nova função também comparada diretamente à execução ARM64 original. Isso não demonstra equivalência universal, reconstrução integral do executável, nem recuperação do código-fonte textual original.

**Ainda faltam quatro funções nomeadas** e o encadeamento do jogo completo. O novo lifter e o pacote V15 estão disponíveis como pacote de reprodução local, mas **a integração integral do gerador V15 ao repositório privado ainda está pendente**. O GitHub Actions privado do EdgeAI-Engine continua falhando antes de executar steps, sem causa confirmada.
