# v0.10 — busca reutilizável, com atualização verificada

Base: pacote v0.9, preservado sem alteração. Autorização: seguir metas técnicas sem novas confirmações.
Escopo: cache em RAM para a sessão, índice invertido por arquivo, refresh por comparação integral de conteúdo, CLI em lote, evidência e pacote verificável. Sem treinamento, download obrigatório ou arquivos do usuário enviados pela rede.

## Contrato
- Resultados, ranking e linhas equivalentes à busca v0.9 para snapshots iguais.
- Cada consulta via engine/CLI relê fontes permitidas sob os mesmos limites. Só conteúdo byte a byte idêntico reutiliza a indexação. Não confiar em tamanho/mtime.
- Inclusões, remoções, mudanças e exclusões são aplicadas na consulta seguinte. Um snapshot durante edições concorrentes não constitui transação do sistema de arquivos.
- Cache somente em RAM; sem persistência de código privado no disco. Limite explícito de entradas do índice. Se exceder, recusar o arquivo inteiro e marcar parcial.
- Distinguir bytes relidos, arquivos reutilizados/reindexados, linhas candidatas e revisão. Não alegar economia de I/O nem energia.
- Sem busca semântica, AST geral, treinamento novo ou equivalência a assistentes avançados.

## Etapas verificáveis
1. Baseline v0.9 compilada e testada; testes novos falham antes da implementação.
2. CodeIndex com refresh verificável e postings; cache na Engine; CLI --batch.
3. Testes de alteração com mesmo tamanho/mtime, remoção, adição, limites, symlinks, ranking e lote.
4. Comparação com fonte v0.9 preservada em processo equivalente; fontes CPython existentes e casos ausentes.
5. Suíte inteira; build portátil; empacotamento, extração e smoke final. Preservar hashes de modelos.

## Decisões
Referência neural externa permanece pendente: curl nesta rodada falhou DNS para GitHub e Hugging Face. Não substituir teste de modelo por servidor simulado.
