# EdgeAI Engine v0.11 — ranking de definições e múltiplas ocorrências

Base: v0.10. **Sem novo treinamento, sem LLM externo, sem alegação de inteligência geral.**

## Mudança

A busca lexical agora mantém múltiplas ocorrências relevantes por arquivo e classifica linhas para priorizar definições sobre comentários, strings e chamadas. O conteúdo citado continua sendo conferido contra o arquivo real.

## Benchmark CPython preservado

Mesmo corpus e 35 consultas da v0.10 (27 definições top-level + 8 símbolos ausentes), 5 execuções.

| Métrica | v0.10 | v0.11 |
|---|---:|---:|
| Definição correta top-1 | 16/27 | **24/27** |
| Definição correta top-5 | 18/27 | **27/27** |
| Ausentes retornam vazio | 8/8 | **8/8** |
| Mediana da sessão (35 consultas) | 25.035 ms | **27.683 ms** |

A v0.11 melhorou recuperação nesse corpus, com ~10,6% de aumento de latência sobre a mediana publicada da v0.10. Isso continua sendo busca lexical/heurística, não compreensão semântica nem benchmark neural.

Validação final adicional no GitHub Actions do HEAD integrado (recompilando a v0.10 a partir do commit `d2735c6` no mesmo runner): v0.10 = 16/27 top-1, 18/27 top-5, 8/8 ausentes, 36.930 ms; v0.11 = **24/27 top-1, 27/27 top-5, 8/8 ausentes, 40.084 ms**. Os tempos variam por runner; a comparação válida é dentro da mesma execução.

## Validação

Teste RED observado na v0.10: a busca retornava apenas uma ocorrência por arquivo. Após a mudança, definição, chamada e demais ocorrências relevantes podem coexistir, com a definição priorizada.

Validação local final: 13/13 CTest e 108/108 testes Python. O teste de code search também passou com Clang ASan+UBSan. Os 142 arquivos .edge/.pt foram comparados por SHA-256 contra a v0.10 e permaneceram idênticos.

---

## Relatório histórico v0.10

# EdgeAI Engine v0.10 — busca reutilizável com conferência de conteúdo

Base efetiva: ZIP v0.9. **Sem novo treinamento, sem LLM externo real, sem medição de energia.**

## Entrega

CodeIndex em RAM, postings por termo/linha e refresh incremental. Engine mantém o índice
entre perguntas; CLI --batch processa várias consultas no mesmo processo. A cada consulta,
fontes permitidas são relidas e comparadas byte a byte. Arquivos iguais reutilizam a indexação;
arquivos alterados são reindexados; adições/remoções entram na consulta seguinte.
Não confiamos apenas em mtime/tamanho. **Ainda existe leitura de arquivos em cada consulta.**
O cache não é persistido no disco e desaparece ao encerrar o processo.

## Comparação com a implementação anterior

A fonte original v0.9 foi preservada em benchmarks/v09_baseline. Foi acrescentado somente um
wrapper de entrada em lote, que reconstrói o índice por pergunta como a engine antiga.
Os dois executáveis foram compilados em Release e processaram a MESMA sequência de 35 consultas,
em um processo por sessão. Cinco repetições por variante, ordem intercalada embaralhada.
Tempos incluem startup, carregar fontes, conferir conteúdo, pesquisar, serializar e finalizar.

Corpus: **18 módulos CPython**, 492,696 bytes, 13,699 linhas.
Snapshot e licenças já estavam no projeto em data/cpython_snapshot. Nenhum arquivo baixado.
São consultas por identificadores, derivadas automaticamente de definições top-level por AST;
8 nomes ausentes completam o conjunto. Não há execução de código Python encontrado.
Não é teste cego humano nem compreensão semântica de código. Fontes e binários têm hashes no JSON.

| Mediana | v0.9 | v0.10 |
|---|---:|---:|
| Sessão com 35 consultas | 348.985 ms | 25.035 ms |
| Processo novo, apenas a primeira consulta | 12.191 ms | 17.965 ms |
| RSS máximo do processo (execuções separadas) | 3348 KiB | 5656 KiB |

A sessão foi **13.94× mais rápida** nessa medição. A primeira consulta foi
**mais lenta**, e o índice aumentou RAM. RSS foi medido em três execuções separadas por variante
com GNU time, mesma sequência de consultas e sem modelo neural carregado. Não misturar o RSS
com memória de treinamento. Caches do sistema operacional não foram esvaziados; não generalizar
os valores para disco frio, outras pastas, rede, PCs fracos ou modelos neurais.

Ao final, 18 arquivos foram reutilizados e 0 reindexados;
ainda assim, 492,696 bytes foram relidos nessa consulta.
Existiam 62,671 entradas termo/linha. Isso NÃO é índice de embeddings.

## Correção e qualidade de recuperação

Todos os resultados (paths, textos, escores, linhas e exclusões) coincidiram com a v0.9 nos
**35 casos diferenciais**. Cada trecho foi conferido contra o arquivo de origem.

- Definição esperada em primeiro lugar: **16/27**.
- Definição esperada nos cinco primeiros resultados: **18/27**.
- Nomes ausentes com resultado vazio: **8/8**.

Esses números são os MESMOS da referência v0.9: esta versão acelera a consulta, não melhora a
heurística de ordenação. Comentários, docstrings e chamadas ainda podem vencer a definição.
O fixture sintético anterior também foi reexecutado: 14/14 positivos top1, 4/4 ausentes.
Não comparar percentuais do fixture pequeno com o corpus CPython como se fossem o mesmo teste.

## Testes e preservação

- Baseline antes de editar: 12 suítes CTest e 102 testes Python.
- Final: **13 suítes CTest, 108 testes Python**.
- CTest em Release, compilação sem SIMD especializado e Clang ASan+UBSan: 13/13 em cada.
- Novos contratos cobrem reutilização, mesma data/tamanho com conteúdo diferente, adição,
  remoção, mudança de linhas, symlinks, arquivo que vira binário, limite do índice,
  raiz removida, lotes e entrada longa. Erros não retornam a resposta anterior.
- Perfil indexed: **9/9 etapas** executadas; não instala modelos nem treina.
- Paridade neural preservada: 36 casos de logits e 24 casos de geração, conforme parity.json.
- **142 arquivos .edge/.pt idênticos por SHA-256 à v0.9**. Nenhum novo aprendizado alegado.
- A primeira consulta em --batch inclui indexação inicial e conferência adicional do conteúdo; ambas são contabilizadas no tempo.
- Logs red-* documentam falhas anteriores às correções; não representam a suíte final.

A revisão também encontrou um caso de overflow de linha terminando parcialmente em CR:
o CLI podia remover o CR do buffer truncado e aceitar uma consulta longa. Um teste reproduziu
a falha e passou após manter a informação de overflow. Corrigido ainda nesta rodada. Outro teste reproduziu edição enquanto o CLI esperava a primeira consulta; agora até a primeira pergunta em lote faz refresh verificado, sem servir o snapshot da abertura.

## Limites e segurança

8 MiB de texto aceito e 500.000 entradas de índice por padrão; além dos limites anteriores
de arquivos, tamanho por arquivo, linhas e profundidade. Se um arquivo ultrapassa orçamento,
ele é omitido por inteiro e a resposta marca parcial. Esses limites não são garantia de RSS.
O estado transitório durante refresh pode guardar fonte antiga e nova simultaneamente.

CodeIndex::search usa o snapshot atual; a API manual deve chamar refresh para atualizar.
Engine e CLI em lote já fazem isso. Ler uma árvore não é transação: edições concorrentes podem
produzir uma mistura temporal de versões. Não usar uma árvore hostil com substituição de paths
como fronteira de segurança. Não é sandbox ou detector completo de segredos. Sem upload automático.

Host: model name	: AMD EPYC 9V74 80-Core Processor; Linux-6.18.44-x86_64-with-glibc2.41.
VM moderna, não o computador fraco real. Energia: sensor indisponível; joules=null.
Windows/ARM e LLM externo não executados; tentativas de download nesta rodada falharam DNS.
Binários distribuídos: Linux x86-64. Não houve comparação com Claude, nem evidência de economia
em joules. Não foram comparados ripgrep, linguagens diferentes ou repositórios gigantes.

## Reproduzir

```bash
python tools/run_goals.py --profile indexed
python benchmarks/code_session_v010.py --build build --repeats 5
```

O primeiro comando configura, compila, testa, mede, verifica paridade e empacotamento temporário.
Resultado central: results/v010/code_session.json, com respostas brutas e tempos por execução.
O JSON externo de verificação final liga o ZIP entregue a seu hash; o empacotador faz verificação
antes da publicação. Verificar o ZIP não autentica a autoria; os hashes detectam alterações.
