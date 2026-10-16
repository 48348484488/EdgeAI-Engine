# EdgeAI — recuperação cega de funções de um jogo externo (16/10/2026)

## Origem, proveniência e fonte oculto

- Jogo: [2048-cli](https://github.com/Frost-Phoenix/2048-cli), por Frost-Phoenix, licença MIT; revisão exata `53f4da8249cbe9bce17e0daefbd7903f4a4684be`.
- [Compilação ARM64 real em runner público](https://github.com/48348484488/oxide/actions/runs/38969071956); ramificação de teste `edgeai-blind-2048-experiment`, sem alterar a `main` do Oxide.
- O runner exportou **apenas o ELF AArch64 com símbolos, o ELF sem símbolos e metadados**. O gerador de C++ recebeu **somente o ELF sem símbolos**; o ELF com símbolos e o fonte C foram usados só após a geração, na fase de validação.
- ELF stripped SHA-256: `a3ca49d16ca6428291574ebd3f7c54153ef0913f8aa1eee4279408c3bf9d499b`.
- ELF com símbolos SHA-256: `fdbd492e32f697c04f4943124ced022981ea08882ec4b5a5f5b572d874712dd0`.
- A [pipeline antiga na EdgeAI privada](https://github.com/48348484488/EdgeAI-Engine/actions/runs/38967403930) parava antes de obter runner. O teste real foi executado **localmente**, usando o ELF produzido pelo runner público.
- Ghidra não participou da geração destas funções.

## Resultados verificáveis

| Métrica | Resultado |
|---|---|
| Instruções na seção executável ARM64 | 1.074 |
| Entradas candidatas descobertas sem símbolos | 27 |
| Funções nomeadas do jogo, avaliadas com oráculo após geração | 23 |
| Pontos de entrada do jogo localizados | 23/23 |
| **Funções C++ geradas, compiladas e validadas** | **6/23 (26,09%)** |
| Instruções traduzidas por esses seis candidatos | **168** |
| Comparações diferenciais contra implementação C original | **700.048** |
| Divergências detectadas nas amostras | **0** |
| Testes de regressão adicionais executados localmente | **24 passaram** |

### Funções recuperadas (os nomes só foram conhecidos depois, pelo oráculo)

| Endereço ARM64 | Nome descoberto após geração | Categoria do tradutor | Instruções | Verificações |
|---|---|---|---:|---:|
| `0x400abc` | `_rotate_board` | Escrita/rotação de tabuleiro | 40 | 100.007 |
| `0x400b5c` | `_empty_cells_left` | Leitura de tabuleiro | 17 | 100.005 |
| `0x400ba0` | `_can_slide_up` | Leitura de tabuleiro | 23 | 100.005 |
| `0x400d58` | `board_can_move` | Chamadas entre funções | 27 | 100.007 |
| `0x400dc4` | `board_win` | Leitura de tabuleiro | 18 | 100.005 |
| `0x400f58` | `_get_color` | Escalar; `CSEL`/`CSET` | 43 | 200.019 |

Os retornos, e também os **16 elementos do tabuleiro** no caso das funções que recebem ponteiros, foram comparados com referências C compiladas em separado. Todos os testes foram feitos em biblioteca nativa Linux x86-64 usando o C++ *traduzido* de ARM64, e não executando o jogo ARM64. **O código decompilado não é a origem C original**: é uma representação equivalente de baixo nível, com registradores e saltos explícitos.

## Ferramentas e reprodução

1. `tools/aarch64_stripped_discovery.py`: encontra entradas candidatas sem símbolos.
2. `tools/aarch64_leaf_lifter.py`: traduz funções de leitura de tabuleiro.
3. `tools/aarch64_mutating_lifter.py`: traduz escrita de palavras e endereçamento pré-indexado, com checagens de acesso.
4. `tools/aarch64_scalar_lifter.py`: traduz funções escalares com comparações e seleção condicional.
5. `tools/aarch64_linked_lifter.py`: resolve chamadas `BL` para funções já traduzidas; só aceita um formato de prólogo/epílogo de pilha reconhecido.
6. `tools/aarch64_blind_batch_lift.py`: percorre **todas as 27 entradas**, faz duas passagens (funções folha, depois funções que chamam outras) e registra as rejeições.

Para reproduzir a etapa de geração, obtenha `2048-arm64-stripped.elf` do [artefato da execução pública](https://github.com/48348484488/oxide/actions/runs/38969071956), confira o SHA-256 e execute:

```bash
python3 tools/aarch64_blind_batch_lift.py 2048-arm64-stripped.elf --output-dir results/2048-candidates
g++ -std=c++17 -O2 -fPIC -shared results/2048-candidates/candidate_*.cpp -o results/2048-recovered.so
python3 -m unittest discover -s tests -p 'test_aarch64_game_progression.py' -v
```

Esta geração não requer o código-fonte do jogo. A validação diferencial necessita das referências C originais, obtidas e compiladas **separadamente após a geração**. Dados da verificação: [`results/blind_2048_six_function_reconstruction_2026-10-16.json`](../results/blind_2048_six_function_reconstruction_2026-10-16.json). A primeira iteração de três funções permanece documentada em [seu relatório histórico](../results/blind_2048_three_leaf_functions_2026-10-16.json).

## Limitações e sequência técnica

Restam **17 das 23 funções** do jogo sem reconstrução C++ validada. O método não recupera nomes nem tipos originais, pressupõe assinaturas conhecidas e **não suporta ainda** a maioria dos frames de pilha, ponteiros locais, chamadas de biblioteca e escrita complexa. A função de chamadas cruzadas depende de um formato restrito de prólogo ARM64 e de módulos gerados previamente. A cobertura de 26,09% é por **quantidade de funções nomeadas**, não por bytes, instruções nem lógica do jogo.

**Próxima expansão prioritária:** abstrair stack frames `STP`/`LDP`, memória local e chamada entre funções para destravar `board_move_*`, `_slide_col` e outras rotinas. Nenhum dos seis casos valida funcionamento completo do processo de jogo; não declarar o jogo descompilado até reconstruir, compilar e comparar a execução do conjunto.
