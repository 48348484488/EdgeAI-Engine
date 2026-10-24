# EdgeAI V14 — 18 funções do jogo externo 2048 reconstruídas

**Data:** 24/10/2026. **Método:** análise do ELF AArch64 sem símbolos, geração de C++ limitada por contratos de ABI, compilação nativa e validação diferencial posterior.

## Resultado

O benchmark usa somente o executável `2048-arm64-stripped.elf` original, SHA-256 `a3ca49d16ca6428291574ebd3f7c54153ef0913f8aa1eee4279408c3bf9d499b`. Jogo: [Frost-Phoenix/2048-cli](https://github.com/Frost-Phoenix/2048-cli), MIT, commit `53f4da8249cbe9bce17e0daefbd7903f4a4684be`.

- **27 entradas candidatas** detectadas; **18 funções C++ geradas e compiladas**, **9 entradas ainda não suportadas**.
- **675 instruções ARM64** traduzidas, incluindo **146 novas**.
- **18/23 funções nomeadas pós-validação (78,26%)**, sem alegar reconstrução integral.
- **78/78 testes automatizados**, incluindo casos negativos e a alteração proposital de um desvio, corretamente detectada.
- **1.200.088 comparações diferenciais anteriores** repetidas contra a biblioteca ampliada, com zero divergências.

| Entrada | Nome descoberto após gerar C++ | Instruções | Testes diferenciais | Bytes de saída conferidos |
|---|---|---:|---:|---:|
| `0x401004` | `_print_cell` | 114 | 1.116 | 172.955 |
| `0x401404` | `print_board` | 32 | 261 | 648.324 |

As novas rotinas foram recuperadas sem acesso aos nomes nem ao código-fonte do jogo durante a geração. A primeira analisa condições, preservação de registros, chamada de uma função escalar já recuperada, endereço `ADRP+ADD`, `__printf_chk@plt` e strings da `.rodata`. A segunda percorre um buffer de **64 bytes** e chama a primeira por uma aresta `BL` identificada no ELF, com limites explícitos para leituras.

Os arquivos C das duas rotinas originais foram usados **somente depois** de gerar o C++, para validar sua saída. São testes sobre entradas amostradas, e não uma prova de equivalência universal. As novas rotinas ainda não passaram por validação de estados de CPU com QEMU; esse é o próximo estágio.

**Limites:** valores de célula ≥10.000 foram excluídos, pois o original deixa variáveis locais de formatação sem inicialização para esse caso. A ABI é declarada, não inferida de forma universal. Cinco funções nomeadas continuam ausentes: `setBufferedInput`, `print_score`, `signal_callback_handler`, `setup` e `main`. O jogo completo ainda não foi recompilado a partir das funções traduzidas.

## Reprodução

O pacote V14 inclui o binário sem símbolos, tradutores em `analysis/`, geração `batch_v14/`, oráculos apenas pós-geração, testes e relatório. Depois de extrair, com `g++`, `gcc`, Python 3 e `llvm-objdump`:

```bash
python3 tools/verify_2048_v14.py --full
```

O comando verifica o hash do ELF, regenera as 18 funções do zero, compila a biblioteca, compara todos os arquivos de C++ gerados com o pacote, executa os 78 testes e confere novamente as 1.377 novas saídas e os 1.200.088 casos antigos.

Os tradutores recusam instruções fora do subconjunto aceito, contratos de chamada ausentes e leituras fora do buffer. Não usam nomes de função nem código-fonte original para gerar C++.

[Resultado completo em JSON](../results/blind_2048_eighteen_function_reconstruction_2026-10-24.json).

## Próximo estágio

Executar **as duas novas rotinas diretamente no ELF ARM64 original sob QEMU** e comparar os bytes produzidos com o C++ reconstruído. Depois, evoluir gradualmente para `print_score` com dados globais, `setBufferedInput` com `termios` e a rotina principal. O objetivo não é apenas reproduzir um jogo conhecido, mas generalizar a recuperação sem recorrer a regras codificadas para seus nomes.
