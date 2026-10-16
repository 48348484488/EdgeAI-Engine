# Marco: jogo completo de teste ARM32 (16/10/2026)

## Objetivo

Usar o jogo da velha compilado (`examples/reverse/tictactoe.c`) como
projeto pequeno, com três funções (`winner`, `play`, `start`).
Mensurar reconstrução funcional de ponta a ponta antes de tentar
projetos maiores. **Não é um descompilador geral.**

## O que foi feito

- `tools/recover_start_arm.py` desmonta o ARM32 com LLVM, reconhece
  o padrão estrito de chamadas de `start`, recupera cinco pares
  de argumentos `(posição, jogador)`, verifica o destino `play` e
  emite C++ sem ler o C de origem para essa função.
- `tests/test_recover_start_arm.py` inclui testes positivos e
  negativos com ELF ARM32 gerado pelo Clang (rejeitando chamadas
  alteradas, instruções diferentes e fim de função inválido).
- `tools/validate_whole_tictactoe.py` integra o recuperador de
  `winner`, o gerador de `play` e o novo recuperador de `start`.
  Compila os três candidatos para ARM32 e também para a CPU local,
  compara a saída e as nove casas do tabuleiro com o jogo original.
- `tests/whole_game_differential_harness.cpp` compara **262.144**
  tabuleiros de 4 símbolos e **16.384** entradas pseudoaleatórias.

## Resultado medido neste ambiente

A recuperação de `start` foi executada com sucesso sobre o ELF ARM32:
`play(0,1)`, `play(4,2)`, `play(1,1)`, `play(8,2)`,
`return play(2,1)`. Três testes locais do extrator passaram.

Uma versão montada localmente com `start` emitido a partir do binário
e implementações C++ **manualmente construídas** para `play` e
`winner` foi compilada e executada:

```json
{"passed":true,"tested_cases":278528,"mismatches":0}
```

Esse resultado local comprova a coerência do teste comportamental e
da função `start` recuperada. **Ele não comprova que as três funções
foram decompiladas automaticamente.** Na validação integrada do
repositório, `winner` é recuperado por fingerprint ELF e `play`
depende do código C de exemplo para inferir regras; por isso ela é
declarada *source-assisted*, mesmo que passe.

## CI / bloqueio

O workflow
[whole-game-recovery.yml](../.github/workflows/whole-game-recovery.yml)
foi criado e disparado pelo commit. A execução inicial
[#38965316337](https://github.com/48348484488/EdgeAI-Engine/actions/runs/38965316337)
terminou com **falha**, e a consulta de jobs retornou **nenhuma etapa
ou log utilizável**. Portanto o resultado integrado da execução
automática não está confirmado. Não registrar 3/3 funções como
decompiladas independentemente.

## Próximos critérios de sucesso

1. Conseguir CI com logs e validar a integração das três funções.
2. Remover a leitura de `tictactoe.c` no gerador de regras de `play`,
   provando a obtenção da regra diretamente dos bytes ARM32.
3. Repetir com diferentes compilações, otimizadores, programas pequenos
   e ELF sem símbolos.
4. Exigir para cada função: evidência no binário, C++ gerado, compilação,
   testes diferenciais e registro das instruções não compreendidas.
5. Medir cobertura real de funções em bibliotecas maiores. **Não
   chamar inventário estático de descompilação.**

A comparação exaustiva dos estados testados não demonstra equivalência
formal para toda entrada possível, não preserva necessariamente bytes
originais nem substitui testes ARM nativos.
