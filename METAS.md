# Metas — EdgeAI v0.11

| Meta | Estado |
|---|---|
| Preservar v0.9 e modelos | 142 arquivos .edge/.pt idênticos por SHA-256 |
| Reutilizar busca em sessão | Implementado em C++: postings em RAM e refresh por conteúdo |
| Não confiar só em data/tamanho | Testado com edição do mesmo tamanho e mtime restaurado |
| Não devolver índice antigo após mudanças | Adição, remoção, raiz removida, mudança de linhas e primeira consulta testadas |
| Melhorar ranking sem trocar o corpus | 24/27 top1 e 27/27 top5 no corpus CPython; v0.10 era 16/27 e 18/27 |
| Medir custos | Sessão, consulta inicial e RSS separados; cold start e RAM pioram |
| Preservar negativos | 8/8 nomes ausentes continuam com resultado vazio |
| Conferir execução | 13 suítes CTest, 108 testes Python; perfil indexed com 9 etapas |
| Empacotar entrega | ZIP com manifesto SHA-256, extração e recompilação verificadas externamente |
| Executar modelo externo | Pendente: download falhou DNS; não contabilizar fixture como LLM |
| Treino/qualidade neural/energia | Nenhum treino; sem nova qualidade neural ou medição em joules |
| Windows/PC fraco real | Não executados; binários Linux x86-64 |

## Próximas metas, não executadas
1. Criar um conjunto realmente novo e revisado de busca de código para medir generalização do ranking sem reutilizar o corpus CPython da v0.10/v0.11.
2. Executar a ponte externa somente com llama-server/GGUF reais, versão, licença e hashes; reportar qualidade e custo separados.
3. Medir na máquina-alvo antes de prometer compatibilidade/energia. Iniciar Windows com build + teste real.
4. Pesquisa neural: um versus dois blocos, currículo e orçamento controlados; não é consequência automática de acelerar busca.

`python tools/run_goals.py --profile indexed` executa e encerra uma rodada local, sem instalação, downloads, treino ou trabalho em segundo plano após terminar.
