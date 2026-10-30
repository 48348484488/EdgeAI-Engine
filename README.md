# EdgeAI Engine

**Engenharia reversa experimental de programas e jogos compilados.**

Ferramentas locais para analisar binários ARM e reconstruir funções em C++ nos casos suportados. Projeto voltado a PCs modestos, sem exigir GPU.

## Recursos

- Análise de arquivos ELF (executáveis e `.so`).
- Inspeção de instruções ARM32, Thumb e ARM64.
- Mapeamento de funções, chamadas e fluxo de controle (CFG).
- Reconstrução parcial de funções em C++.
- Validação por testes diferenciais e execução ARM via QEMU.
- Runtime experimental leve em C++17.

## Progresso

**Em desenvolvimento.** No teste com o jogo 2048 para ARM64 (V15), a EdgeAI reconstruiu **19 de 23 funções nomeadas (82,61%)**. Resultados selecionados foram comparados com implementações de referência e com o binário original no QEMU.

[Ver resultados e limitações da V15](docs/blind_external_game_2048_v15_2026-10-29.md)

> **Limite atual:** ainda não descompila jogos inteiros de forma autônoma nem recupera o código-fonte original. O componente neural também é experimental.

## Uso rápido

**Requisito:** Python 3. Os analisadores básicos não precisam de bibliotecas externas.

```bash
git clone https://github.com/48348484488/EdgeAI-Engine.git
cd EdgeAI-Engine

# Inspecionar um arquivo ELF
python3 tools/elf_inspect.py arquivo.so

# Analisar saltos ARM32
python3 tools/arm_scan.py arquivo.so --mode arm
```

Para executar os testes básicos:

```bash
python3 -m unittest discover -s tests -p 'test_elf_inspect.py'
```

## Documentação

- [Metas técnicas](METAS.md)
- [Histórico de alterações](CHANGELOG.md)
- [Runtime de baixo consumo](docs/low-resource-runtime.md)
- [Relatório do teste 2048 V15](docs/blind_external_game_2048_v15_2026-10-29.md)

## Limites e execução em CPU

O perfil **EDGEAI_LOW_RESOURCE** usa limites de referência de **64 MiB** de memória
para o processo e **16 MiB** para o modelo em testes de baixo consumo, com execução
**CPU-only**. São limites de configuração/benchmark, não garantia de desempenho
para qualquer APK. Consulte [os testes](docs/low-resource-runtime.md).

Os números de **tool accuracy** são medidos por tarefa e conjunto de testes;
o componente **neural** é experimental e **does not claim parity** com o jogo
original sem comparação dinâmica de entradas, estados e saídas.
