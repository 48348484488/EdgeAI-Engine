
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
