# AUTONOMOUS_PROGRESS.md

## Estado em 2026-10-29 (America/Recife)

- Último trabalho: corrigidos bloqueios reais de CI identificados nos logs da execução #40982007549 (21 erros, 3 falhas). O runner estava sem `llvm-objdump`/`llvm-objcopy`; três regressões determinísticas envolviam caminho de teste obsoleto, bytes de fixture incorretos e contrato de README; mensagem de proveniência clarificada.
- Commit de CI: [e8c419e](https://github.com/48348484488/EdgeAI-Engine/commit/e8c419e9a99651645c53db52542da666a1796870).
- Implementação adicional: `tools/edgeai_ui_rect_parity.py` compara retângulos de referência, desenho e área clicável, com escala e tolerâncias explícitas; não afirma igualdade visual nem funcional. Seis testes locais aprovados.
- Pipeline externo 2048: compilação ARM64 falhou por falta de headers glibc do cross compiler. Adicionado `libc6-dev-arm64-cross` ao workflow. A comparação QEMU e a recuperação integral ainda não estão concluídas.
- Última cobertura histórica do 2048: 19/23 funções; não houve nova validação de funções nesta execução.
- Last Island recriado: commit [efe9e2e](https://github.com/48348484488/last-Island-of-survival-lite/commit/efe9e2e09193bfb94705cecc8cd7b85a34535879) corrige área clicável de voltar, espaçamento de subcategorias e conservação de tempo da fila offline. O build Android desse commit ainda deve ser verificado antes de declarar APK novo funcional.
- Referência: `mobile_original_craft_layout.hpp` extraído do Unity LITE 7.3. Referências externas de gameplay de outras versões não substituem evidência dessa versão.
- Diferenças pendentes: tela original e APK reconstruído ainda não comparados quadro a quadro; produção em rede, inventário, física, animações, texturas e sons não estão validados como equivalentes.
- Próxima prioridade: inspecionar CI após correções; se verde, integrar geometria medida do jogo à ferramenta e testar APK ARM64 em ambiente virtual, capturando frames reais e comparando ao mesmo estado do original.

## Regras de continuidade

Consultar as execuções mais recentes antes de repetir uma análise. Guardar SHA dos binários, versão original, entrada/estado, prova de compilação, logs e artefatos por comparação. Não usar imagem gerada como captura de teste.
