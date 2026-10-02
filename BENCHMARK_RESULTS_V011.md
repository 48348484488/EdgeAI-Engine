# EdgeAI Engine v0.11 — ranking de definicoes

Base: v0.10. Sem novo treinamento e sem alteracao dos modelos neurais.

Mudanca delimitada em CodeSearch: definicoes recebem prioridade sobre comentarios, strings e chamadas; varias ocorrencias relevantes do mesmo arquivo podem ser retornadas.

## Corpus CPython preservado da v0.10

- 27 consultas positivas por identificador e 8 negativas.
- v0.10 registrada: top-1 16/27; top-5 18/27; negativas 8/8.
- v0.11: top-1 24/27; top-5 26/27; negativas 8/8.
- Mediana v0.11 em 9 sessoes de 35 consultas: 29.067 ms neste ambiente.
- Referencia registrada da v0.10: 25.035 ms em 5 repeticoes no benchmark original. As execucoes nao sao pareadas e caches do SO nao foram limpos.

Isso mede recuperacao lexical de codigo, nao inteligencia neural ou compreensao semantica geral.
