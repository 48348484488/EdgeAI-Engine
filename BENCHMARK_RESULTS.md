# EdgeAI Engine v0.11 — ranking estrutural de busca de codigo

Base efetiva: v0.10. **Sem novo treinamento, sem LLM externo real e sem alteracao dos modelos neurais.**

## Mudanca

A busca local continua lexical e deterministica, mas agora o ranking diferencia melhor definicoes de usos. Linhas com formas de definicao comuns (`def`, `class`, `function`, `fn`, `func`, `stock`, `public`, `forward`) recebem prioridade; comentarios e ocorrencias dentro de strings sao penalizados. Ocorrencias com corpo em C/C++-like recebem sinal estrutural adicional. A busca tambem deixa de descartar todas as ocorrencias secundarias de um arquivo: multiplos trechos relevantes do mesmo arquivo podem aparecer no top-N.

Isso **nao e parser completo**, AST multi-linguagem ou compreensao semantica. Macros, sintaxes incomuns, aliases e construcoes ambiguas ainda podem ser ordenadas incorretamente.

## Benchmark controlado v0.10 x v0.11

Mesmo snapshot CPython distribuido no projeto: 18 modulos, 27 consultas positivas derivadas de definicoes top-level por AST e 8 nomes ausentes. Cinco sessoes por versao no mesmo host, um processo por sessao. Evidencia de cada hit foi conferida contra o arquivo fonte.

| Metrica | v0.10 | v0.11 |
|---|---:|---:|
| Definicao esperada top-1 | 16/27 | **24/27** |
| Definicao esperada top-5 | 18/27 | **26/27** |
| Nomes ausentes vazios | 8/8 | **8/8** |
| Mediana da sessao (35 consultas) | 26.104 ms | **27.659 ms** |

Neste host, a sessao v0.11 ficou cerca de 5.95% mais lenta que v0.10, enquanto top-1 subiu de 59.26% para 88.89%. Isso mede apenas esse corpus e esse host; nao generalizar para outros repositorios ou PCs fracos.

## Teste de regressao novo

O teste de busca agora inclui um arquivo Python em que comentario, string e chamada aparecem antes da definicao real. Antes da implementacao, o teste falhou porque a chamada anterior venceu a definicao. Depois da mudanca, a definicao real fica em primeiro lugar e mais de uma ocorrencia util do mesmo arquivo e preservada.

## Verificacao

- Release CTest: **13/13**.
- Python: **108/108**.
- Build portavel com `EDGEAI_DISABLE_SIMD=ON`: **13/13 CTest**.
- ASan + UBSan: **13/13 CTest**.
- **142 arquivos `.edge/.pt` identicos por SHA-256 a v0.10**.
- Nenhum treinamento novo e nenhuma alegacao de ganho de inteligencia neural.

## Limites

O benchmark e de recuperacao lexical de codigo, nao de programacao autonoma. Nao houve comparacao com Claude/Opus, medicao de energia, Windows/ARM ou teste no PC fraco real. A v0.11 melhora a qualidade de navegacao em codigo; nao demonstra melhora do pequeno Transformer do EdgeAI.
