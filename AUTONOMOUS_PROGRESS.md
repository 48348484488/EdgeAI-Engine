# AUTONOMOUS_PROGRESS.md

## Estado em 2026-10-29 (America/Recife)

- Último trabalho: corrigidos bloqueios reais de CI identificados nos logs da execução #40982007549 (21 erros, 3 falhas). O runner estava sem `llvm-objdump`/`llvm-objcopy`; três regressões determinísticas envolviam caminho de teste obsoleto, bytes de fixture incorretos e contrato de README; mensagem de proveniência clarificada.
- Commit de CI: [e8c419e](https://github.com/48348484488/EdgeAI-Engine/commit/e8c419e9a99651645c53db52542da666a1796870).
- Implementação adicional: `tools/edgeai_ui_rect_parity.py` compara retângulos de referência, desenho e área clicável, com escala e tolerâncias explícitas; não afirma igualdade visual nem funcional. Seis testes locais aprovados.
- Pipeline externo 2048: **sucesso comprovado** em [GitHub Actions #40987700562](https://github.com/48348484488/EdgeAI-Engine/actions/runs/40987700562). Corrigidos headers ARM64 (`libc6-dev-arm64-cross`), inicialização PyGhidra headless e incompatibilidade `unicode()`/Python 3. EdgeAI auditou estaticamente 26/26 funções elegíveis do ELF ARM64 (SHA-256 `bba6185a8c9be36af7bc14d72c7b29b5a7f683c827424b5203520a50725983a2`); Ghidra externo exportou 68 pseudocódigos incluindo stubs/runtime. **0 funções C++ nativas recuperadas neste pipeline**, sem teste diferencial nem execução do jogo reconstruído. [Artefatos](https://github.com/48348484488/EdgeAI-Engine/actions/runs/40987700562/artifacts/12947966471).
- Última cobertura histórica do 2048 V15: 19/23 funções. O pipeline independente de 26 funções é **auditoria estática**, não amplia essa cobertura funcional.
- CI geral: ainda falha nos testes Python de reconhecimento ARM32 com LLVM atual; não está travado. O runner já executa os testes, mas os padrões antigos de disassembly precisam de normalização/versionamento. A suíte C++ e o CI ARM64 foram aprovados no commit anterior.
- Last Island recriado: commit [efe9e2e](https://github.com/48348484488/last-Island-of-survival-lite/commit/efe9e2e09193bfb94705cecc8cd7b85a34535879) corrige área clicável de voltar, espaçamento de subcategorias e conservação de tempo da fila offline. Build e publicação do APK ARM64 [#40987477840](https://github.com/48348484488/last-Island-of-survival-lite/actions/runs/40987477840) aprovados; [release v0.25.0-2c762836](https://github.com/48348484488/last-Island-of-survival-lite/releases/tag/v0.25.0-2c762836). Execução em Android virtual e comparação visual ainda pendentes.
- Referência: `mobile_original_craft_layout.hpp` extraído do Unity LITE 7.3. Referências externas de gameplay de outras versões não substituem evidência dessa versão.
- Diferenças pendentes: tela original e APK reconstruído ainda não comparados quadro a quadro; produção em rede, inventário, física, animações, texturas e sons não estão validados como equivalentes.
- Próxima prioridade: normalizar saída de `llvm-objdump` e recuperar CI Python; avançar da auditoria estática das 26 funções para uma função C++ efetivamente reconstruída e comparada ao ARM64 original no QEMU. Em paralelo, instalar APK Last ARM64 no Android virtual e obter screenshots reais do mesmo estado do Unity LITE 7.3.

## Regras de continuidade

Consultar as execuções mais recentes antes de repetir uma análise. Guardar SHA dos binários, versão original, entrada/estado, prova de compilação, logs e artefatos por comparação. Não usar imagem gerada como captura de teste.
