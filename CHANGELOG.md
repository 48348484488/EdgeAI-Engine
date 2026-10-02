# v0.11

- Ranking de busca passa a priorizar definições e declarações sobre chamadas, comentários, strings e docstrings Python.
- Busca pode preservar até três ocorrências relevantes do mesmo arquivo antes do corte global.
- Projeção de código mascara comentários de linha, comentários de bloco e strings/docstrings para a pontuação sem alterar o trecho citado.
- TDD: teste RED confirmado em GitHub Actions antes da alteração de produção.
- Verificação final: 13/13 CTest e 108/108 testes Python.
- Corpus CPython reutilizado: top-1 16/27 → 24/27; top-5 18/27 → 27/27; ausentes 8/8 mantidos.
- Mediana da sessão no mesmo runner: 41,976 ms → 45,597 ms (~8,6% mais lenta).
- Sem treinamento neural novo; modelos/checkpoints existentes não foram alterados por esta mudança.

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
