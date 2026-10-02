# EdgeAI Engine v0.9 — resultados e limites

## Entrega
Código baseado no ZIP v0.7.1 recuperado. Consulta lexical C++ com arquivo e linha,
rota no chat, workbench `.edge`/referência e perfil `useful` de dez etapas.
**Sem novo treinamento. Sem modelo externo real executado.**

## Busca de código
Fixture sintética própria em `data/code_demo`, com fontes C++, Python, JavaScript
 e Pawn. Perguntas pedem símbolos presentes literalmente. Os hashes estão em
`docs/v09/fixture_hashes.json`, verificados antes da avaliação. Não é benchmark
externo cego nem compreensão semântica. Estes materiais não são um jogo executável.

- Casos positivos: **14/14** no primeiro resultado,
  exigindo o arquivo e a linha esperados.
- Casos negativos: **4/4** retornaram vazio.
- Todos os trechos retornados conferiram com as linhas originais dos arquivos.
- Três execuções por caso: **54 invocações**, não 54 perguntas independentes.
- Mediana de ponta a ponta do fixture: **2.653 ms**,
  incluindo iniciar o executável, ler fontes e pesquisar. Não mede geração neural.
- Não houve comparação com grep/ripgrep, portanto não afirmar vantagem sobre eles.

Probe no próprio projeto: `greedy_token` em `src/TransformerBackend.cpp:45`.
Foram inspecionados 187 arquivos / 613730 bytes de fonte,
com exclusões declaradas. Pico de RSS em **um processo separado**: **3336 KiB**
(`/usr/bin/time -v`). Não extrapolar para pastas/modelos maiores. Texto em memória,
RSS do processo e tamanho dos pesos são medidas diferentes.

## Modelo neural próprio
Os **142 arquivos `.edge`/`.pt`** da base são idênticos por SHA-256.
O diagnóstico fixo deste ciclo teve **2/12 respostas exatas**,
sem ferramentas, usando o `default.edge` antigo. Nenhuma melhoria de inteligência
é atribuída a esta versão. São 12 prompts sintéticos conhecidos, critérios estritos
por bytes; não comparar a taxa com avaliações diferentes de versões anteriores.
Saídas completas em `native_diagnostic.json`.

## Referência externa
`local_reference.py` usa `/v1/models` e `/v1/chat/completions` conforme documentação
oficial do llama-server. Ponte opcional Python padrão, separada da engine C++.
Somente loopback, sem proxies/redirecionamento/fallback, sem executar tool calls.

**Nove testes usam servidor HTTP fixture, não uma rede neural.** Conferem payloads,
Unicode, modelos, limites, erros, JSON, redirects e recusa de endpoints remotos.
Nenhum GGUF nem llama-server foi baixado/instalado. Tentativas de DNS no runtime
falharam para GitHub/Hugging Face. O web tool leu documentação, o que não substitui
execução de modelo. Resultado externo: **indisponível/não executado, sem pontuação**.
O harness registra falhas separadas de respostas erradas e nunca as converte em zero.

Uma comparação futura terá orçamentos de pré-treinamento e tokenizadores diferentes;
igualar max_tokens não iguala trabalho. Latência nativa inclui novo processo/carga;
servidor externo já estaria iniciado. Essas diferenças constam do próprio relatório.

## Correção e verificação
- Baseline antes da edição: 11 suítes CTest e 83 testes Python.
- Final: **12 suítes CTest / 102 testes Python**, em Release e caminho sem SIMD.
- Clang ASan+UBSan: **12/12 suítes CTest**. Não afirmar testes Python sanitizados.
- Paridade preservada: **36 casos de logits** e
  **24 de geração/EOS**; erro máximo 2.05039978e-05, tolerâncias6e-5.
- Perfil `useful`: **10/10 etapas**, sem treinar e sem instalar nada.
- Testes RED e timeout histórico estão preservados; as suítes finais foram repetidas.
- Conferência do ZIP extraído/recompilado e dos binários: relatório JSON externo
  `EdgeAI-Engine-v0.9-VERIFICACAO.json`, vinculado ao hash do pacote final.

## Ambiente e limites
CPU: INTEL(R) XEON(R) PLATINUM 8573C; Linux-6.18.44-x86_64-with-glibc2.41; Python3.13.5.
Host virtual moderno, não o PC fraco do usuário. A busca nativa usa uma thread;
processos de compilação podem ter compartilhado o host. Binários Linux x86-64.
Windows, ARM e PC antigo não executados nesta rodada. Não há .exe Windows incluído.

Energia disponível: **False**; joules de pacote:
**None**. Não inferir energia de tempo, RSS ou TDP.
Não houve comparação com Claude/Opus e não há evidência de superação geral.

## Decisão
Entregar busca útil primeiro, manter o núcleo experimental intacto e a referência
claramente externa/opcional. Próximo bloqueio da comparação é executar um servidor
real com modelo identificado; próximo teste de busca é outro repositório e perguntas
revistas, não aumentar a pontuação de um fixture até parecer inteligência geral.
