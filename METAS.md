# Metas — EdgeAI branch v0.12+ pesquisa v0.15

| Meta | Estado |
|---|---|
| Preservar compatibilidade legada | EDGEAI5/6/7 continuam carregando como 1 bloco; auditoria v0.12 preserva os modelos/checkpoints legados |
| Transformer multi-bloco | Implementado em Python/C++; 1..8 blocos, EDGEAI8 e KV independente por bloco |
| Paridade Python/C++ | Validada para 1/2 blocos, incluindo wrap do KV |
| Benchmark neural controlado | 3 seeds, CPU/steps controlados, geração nativa; 1 bloco continua default |
| Investigar profundidade | Equal-updates, dinâmica, copy-inner, LR interno e seleção por geração executados |
| Generalização fora da faixa | v0.13–v0.15 medidos; currículo maior desloca parte da fronteira, mas não produz soma algorítmica |
| Separar neural de ferramentas | Benchmarks neural-only permanecem separados dos resultados do sistema híbrido |
| Sistema híbrido | Router + Calculator + texto determinístico + memória + busca de código |
| Robustez do Router | Corpus adversarial: 128 TP, 128 TN, 0 FP, 0 FN nas formas testadas |
| Aritmética natural via ferramenta | 96/96 em subtração/multiplicação/divisão bilíngues, todos via Calculator |
| Busca de código | v0.11: 24/27 top-1, 26/27 top-5, 8/8 ausentes no benchmark CPython |
| Linux x86-64 | Validado no CI final: 15/15 CTest + 168 testes Python |
| Windows x64 | Validado no GitHub Actions: MSVC Release + 15/15 CTest + smoke híbrido |
| UTF-8 no MSVC | Build usa /utf-8; teste com code points multibyte passa |
| Linux ARM64 nativo | Validado em runner aarch64: Release + 15/15 CTest + smoke híbrido |
| Android arm64-v8a NDK | Cross-build Release validado; ELF AArch64 e pacote ADB com libc++_shared.so; smoke físico preparado para Calculator + geração/carregamento de `.edge` + rota neural; execução física ainda pendente |
| PC fraco físico | Pendente; Windows CI não mede desempenho da máquina-alvo |
| Energia real | Pendente onde não houver sensor confiável; não inferir joules |
| LLM externo real | Pendente; não contabilizar fixtures como modelo externo |

## Próximas metas

1. **Android/ARM mobile real:** cross-build NDK `arm64-v8a` já passou; falta executar o smoke ADB em dispositivo físico e medir tempo/RSS antes de afirmar desempenho mobile.
2. **Hardware fraco físico:** medir tempo, RSS e comportamento do runtime em uma máquina alvo real; separar isso de resultados de CI.
3. **Capacidade neural por CPU:** melhorar geração livre/generalização sem simplesmente dobrar blocos, KV e latência.
4. **Router fora dos templates atuais:** ampliar corpus adversarial com linguagem mais livre, mantendo precision/recall separados da qualidade da resposta neural.
5. **Sistema híbrido:** continuar adicionando ferramentas apenas quando forem verificáveis e baratas; nunca reportar seus acertos como inteligência do Transformer.
6. **Release/integracao:** manter `main` estável e só integrar a branch depois da verificação final completa e revisão dos relatórios.

## Regra de medição

Resultados do **modelo neural**, das **ferramentas determinísticas** e do **sistema híbrido** devem continuar separados. Todo ganho novo precisa de teste, benchmark reproduzível ou evidência de CI; itens não medidos permanecem marcados como pendentes.
