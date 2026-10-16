# EdgeAI: teste cego com jogo externo (16/10/2026)

## Jogo selecionado

- Repositório externo: https://github.com/Frost-Phoenix/2048-cli
- Commit fixado: `53f4da8249cbe9bce17e0daefbd7903f4a4684be`
- Licença declarada: MIT
- Linguagem: C
- Escopo preliminar: **22 definições candidatas de funções** encontradas por análise mecânica de sintaxe em `src/main.c`, `src/board.c` e `src/draw.c`, sem leitura semântica. O ELF compilado poderá ter outra contagem.
- Meta: jogo desconhecido previamente pela EdgeAI, entre 20 e 50 funções.

## Isolamento contra vazamento do fonte

O workflow `.github/workflows/blind-external-game.yml` tem dois jobs separados:

1. `compile-source-isolated`: checkout apenas do projeto externo no commit fixo, compilação cruzada ARM64 `-O1 -fno-inline -g0 -no-pie` e `strip --strip-all`. Exporta **apenas dois ELFs ARM64 + metadados SHA-256**, sem o fonte.
2. `analyze-binary-only`: checkout apenas da EdgeAI, valida hashes e ausência do projeto original. Aplica o analisador da própria EdgeAI ao ELF com símbolos e exporta pseudocódigo usando o backend externo Ghidra 12.1.3 ao ELF **sem símbolos**.

O Ghidra é uma **referência independente**, não um decompilador desenvolvido pela EdgeAI. A etapa compara métricas de auditoria estática e disponibilidade de pseudocódigo, não equivalência comportamental.

Não se usa o código-fonte do jogo como entrada do descompilador. Ele permanece acessível publicamente aos pesquisadores para validação independente futura.

## Estado real em 16/10/2026

O código do pipeline, o exportador Ghidra, o sumarizador `tools/blind_game_report.py` e os testes de consistência foram publicados.

**O teste externo AINDA NÃO FOI EXECUTADO:** a execução
[#38967403930](https://github.com/48348484488/EdgeAI-Engine/actions/runs/38967403930)
terminou em falha no job `compile-source-isolated` **antes de registrar qualquer etapa**, e o job de análise foi ignorado. As demais execuções recentes da EdgeAI registram falhas semelhantes. Os registros não permitem atribuir a causa com certeza; ela pode estar associada à disponibilidade/autorização dos executores do GitHub Actions. Não existe ELF ou resultado de decompilação desta execução.

Não declarar sucesso, porcentagem recuperada ou recompilação sem artefatos verificáveis do trabalho.

## Critério para avanço

1. Conseguir execução efetiva do job de compilação e obter hash ELF e contagem real de funções.
2. Rodar EdgeAI apenas com ELF e obter status de todas as funções, sem imputar semântica inexistente.
3. Comparar com decompilação Ghidra de ELF stripped, sem atribuir seus resultados à EdgeAI.
4. Implementar/emparelhar o gerador nativo de C/C++ da EdgeAI e tentar a recompilação de funções recuperadas.
5. Comparar diferenças por casos de teste independentes e registrar **falhas, cobertura real e nenhuma falsa aprovação**.

Meta longa: reconstrução funcional completa do jogo com **fonte oculto do processo de reconstrução**, testada contra o executável original. Essa meta não foi atingida.
