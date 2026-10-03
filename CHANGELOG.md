## Pesquisa pós-v0.12 — v0.13–v0.15
- v0.13 ampliou apenas o currículo de treino mantendo os testes selados; melhorou interpolação, mas não resolveu `test_range`/`test_family`.
- v0.14 comparou BPE com tokenização byte pura; byte puro não eliminou os cliffs de generalização.
- v0.15 deslocou explicitamente a fronteira de treino e avaliou um holdout novo definido antes do treino. Em `addition`, o neural permaneceu em 0/96 no novo range; 2 blocos mostrou algum ganho em `expression` e `copy`.
- O runtime híbrido passou a rotear operações estruturadas para ferramentas determinísticas, mantendo os benchmarks neural-only separados.
- Sistema híbrido: 128/128 no `test_range` v0.15, 128/128 em paráfrases e 16/16 no family holdout de reversão; todos esses acertos foram tool-routed, não neurais.
- Fronteira adversarial do Router: 128 true positives + 128 true negatives, 0 false positives e 0 false negatives no corpus sintético balanceado.
- Novas formas naturais bilíngues de subtração, multiplicação e divisão: 96/96 corretas via `Calculator`, 0 casos neurais.
- Provenance de rota agora é exposta no CLI (`route=...`) e registrada nos benchmarks do sistema.
- Portabilidade Windows x64 adicionada ao CI: MSVC Release compila todos os targets, 15/15 CTest passam e o smoke híbrido do Calculator passa; `/utf-8` é aplicado no MSVC para literais determinísticos.
- Linux ARM64 nativo adicionado ao CI: runner `aarch64`, build Release, 15/15 CTest e smoke híbrido passam sem emulação x86.
- Android NDK `arm64-v8a` adicionado ao CI: Release cross-compila `libedgeai.so`, `edgeai_chat`, `edgeai_generate` e `edgeai_make_demo`; ELF AArch64 verificado, `libc++_shared.so` empacotado e smoke ADB fornecido. O smoke preparado cobre Calculator e geração/carregamento de `demo.edge` com rota neural. Execução física continua pendente.
- APK Android ARM64 mínimo adicionado: Activity Java + JNI sobre o `Engine`, backend neural demo em memória e build Gradle reproduzível. O APK final contém apenas `arm64-v8a` com `libc++_shared.so`, `libedgeai.so` e `libedgeai_android_jni.so`; CI `37105947328` passou. Instalação física continua pendente.
- Limite preservado: resultados de ferramentas medem capacidade do sistema híbrido e não devem ser apresentados como generalização do Transformer.

## v0.12 — 2026-10-02
- Transformer Python e runtime C++ agora suportam múltiplos blocos (1..8).
- Novo formato `EDGEAI8`; `EDGEAI5/6/7` continuam compatíveis e carregam como um bloco.
- Cache KV independente por bloco, reset completo e contabilização de memória multi-bloco.
- Exportação Python EDGEAI8 e paridade Python/C++ em kernels scalar/auto.
- Experimento principal de 60 s/seed: 1 bloco 147/582 exatos (149 `correct`) vs. 2 blocos random-identity 138/582.
- Ablação equal-update confirmou que a diferença não vinha apenas do menor número de optimizer updates de 2 blocos.
- Probe de dinâmica encontrou drift relativo muito maior no miolo aleatório do bloco novo (~48–55% vs. ~11–12% no bloco herdado após 128 updates).
- Inicialização copy-inner (`Q/K/V/up` copiados, `project/down` zerados) elevou o 2-blocos equal-update para 145/582.
- Com LR interno do bloco novo em 0,25×, o candidato chegou a **163/582** no teste original.
- Holdout pós-hoc em faixas não usadas, com modelos congelados: 2 blocos 60/384 vs. 1 bloco 15/384, vencendo em 3/3 seeds.
- Warm-up isolado e seleção de checkpoint por geração foram testados e ajudaram parcialmente, mas ficaram menos estáveis que copy-inner + LR 0,25×.
- 1 bloco permanece o padrão de runtime; copy-inner + LR interno 0,25× é o candidato neural experimental preferido.
- Limites preservados: tarefas sintéticas estreitas, sem alegação de inteligência geral; energia/RSS de pico não medidos.

## v0.11
- Code search ranking now prioritizes common definition forms over comments, strings and calls.
- Multiple relevant occurrences from the same file can be returned.
- CPython benchmark: top-1 16/27 -> 24/27; top-5 18/27 -> 26/27; negatives remain 8/8.
- Neural model/checkpoint files unchanged from v0.10.
# v0.10

- Cache por conteúdo e postings em RAM, com limites explícitos.
- Engine reutiliza índices; CLI --batch com respostas independentes e atualização em cada consulta.
- Comparação diferencial com fonte v0.9 preservada e CPython licenciado já incluído.
- Testes de alterações mesmo tamanho/mtime, primeira consulta, overflow, limites e remoções.
- Perfil indexed de nove etapas; modelos inalterados.

# v0.9

Read-only native source search with file/line evidence; explicit chat route; optional loopback llama-server client and comparison harness; bounded no-training goals. Based on v0.7.1; all prior model weights unchanged. No claim of executing a real external model.

# Changelog

## v0.7 — 2026-09-25

- EDGEAI7: RESPONSE/EOS, enquadramento de prompt e término nativo C++.
- Compatibilidade com tokenizadores/modelos anteriores preservada.
- SFT por resposta com expansão fiel dos checkpoints de v0.6.
- Currículo sintético reproduzível, 3 seeds antes/depois e quatro testes separados.
- Auditoria suplementar dos 28 prompts antigos: transferência não demonstrada.
- Trace explícito de tokens, paridade de logits/texto/EOS e testes de regressão.
- Executor instructions / instructions-quick com 12 etapas, hashes e falhas explícitas.
- Seed padrão escolhida por validação, não pelo melhor resultado de teste.

Histórico anterior: docs/v06/ARCHIVED_CHANGELOG.md e results/v03..v06.
