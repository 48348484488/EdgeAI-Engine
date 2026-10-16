# EdgeAI — teste cego com jogo público 2048-cli (16/10/2026)

## Fonte, compilação e isolamento

- Jogo externo: [Frost-Phoenix/2048-cli](https://github.com/Frost-Phoenix/2048-cli), licença MIT
- Revision fixada: `53f4da8249cbe9bce17e0daefbd7903f4a4684be`
- Executável: ELF Linux AArch64 GCC -O1, stripped para o algoritmo de recuperação
- [Compilação isolada aprovada no GitHub Actions público](https://github.com/48348484488/oxide/actions/runs/38969071956) — ramificação `edgeai-blind-2048-experiment`, sem alterar `oxide/main`
- SHA-256 do ELF stripped: `a3ca49d16ca6428291574ebd3f7c54153ef0913f8aa1eee4279408c3bf9d499b`
- SHA-256 do ELF com símbolos (oráculo): `fdbd492e32f697c04f4943124ced022981ea08882ec4b5a5f5b572d874712dd0`
- O job de compilação exporta exclusivamente ELFs e metadados. A reconstrução trabalha no ELF **sem símbolos**. O original e os símbolos foram consultados **após** a geração para validação.
- O [workflow anterior na EdgeAI privada](https://github.com/48348484488/EdgeAI-Engine/actions/runs/38967403930) continuou falhando antes de receber runner; não confundir com o teste real executado no repositório público.

## Resultados medidos

| Medida | Evidência |
|---|---|
| Slots de instrução na seção `.text` | 1.074 |
| Entradas candidatas descobertas sem símbolos | 27 |
| Entradas de funções do jogo (oráculo consultado depois) | 23 |
| Entradas do jogo localizadas | 23/23 (100% recall para esse universo nomeado) |
| Funções reconstruídas em C++ e compiladas | **3/23 (13,04%)** |
| Instruções ARM64 das três funções traduzidas | 58 |
| Tabuleiros por função | 100.005 |
| Comparações contra C original compilado à parte | **300.015** |
| Divergências observadas | **0** |

Funções reconstruídas por endereço do ELF stripped: `0x400b5c` (17 instruções), `0x400ba0` (23 instruções), `0x400dc4` (18 instruções). Apenas depois da reconstrução, o ELF com símbolos revelou seus nomes: `_empty_cells_left`, `_can_slide_up`, `board_win`.

O tradutor [`tools/aarch64_leaf_lifter.py`](../tools/aarch64_leaf_lifter.py) preserva registradores e saltos como C++ de baixo nível. Usa LLVM para decodificar instruções e rejeita operações e saltos não suportados. **A assinatura é assumida**: `int32_t f(const uint32_t* board)`, 16 posições. Os testes cobrem 100.005 tabuleiros por função com retorno idêntico ao C original, não equivalência matemática sobre todos os possíveis valores.

## Como reproduzir

1. Obter `2048-arm64-stripped.elf` do artefato `edgeai-external-2048-arm64-binary-only` da [execução verificada](https://github.com/48348484488/oxide/actions/runs/38969071956), verificar seu SHA-256. O fonte original **não** é necessário para a geração.
2. Executar `python3 tools/aarch64_stripped_discovery.py 2048-arm64-stripped.elf --output candidates.json`.
3. Executar `python3 tools/aarch64_leaf_lifter.py 2048-arm64-stripped.elf --entry 0x400b5c --cpp f1.cpp --report f1.json` (repetir os outros dois endereços).
4. Compilar cada arquivo com `g++ -std=c++17 -O2 -fPIC -shared`.
5. Apenas então comparar os resultados com as implementações originais do [repositório externo](https://github.com/Frost-Phoenix/2048-cli/blob/53f4da8249cbe9bce17e0daefbd7903f4a4684be/src/board.c).

Testes internos: `tests/test_aarch64_stripped_discovery.py` e `tests/test_aarch64_leaf_lifter.py`. Resultado auditável: [`results/blind_2048_three_leaf_functions_2026-10-16.json`](../results/blind_2048_three_leaf_functions_2026-10-16.json).

## O que permanece faltando

O jogo **não foi inteiramente descompilado**: 20 das 23 funções do jogo não têm tradução C++ validada. O tradutor atual suporta apenas folhas sem escrita de memória, sem chamadas entre funções e sem stack frames complexos. Ainda são necessários análise de dependência interprocedural, escrita em memória, modelos de heap/stack, tipos/assinaturas, chamadas de biblioteca e validação do comportamento do processo de jogo. Ghidra não foi utilizado para gerar as três funções.

A meta é progredir de 3/23 para cobertura crescente, **sem inventar resultados de testes não executados**.
