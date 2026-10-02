# Metas do EdgeAI — v0.6

## Entregas verificadas neste ciclo

| Meta | Critério | Estado / evidência |
|---|---|---|
| Preservar v0.5 | Extração isolada, baseline antes de modificar | Concluída; logs baseline em results/v06 |
| Tokenização nativa reversível | Todos os bytes, acentos/emojis, merges inválidos, BOS | Concluída; ByteBPE Python/C++, testes e paridade |
| Vocabulário variável | EDGEAI6 com tokenizador embutido, formatos anteriores mantidos | Concluída; testes de exportação, carregamento e logits |
| Corpus externo à engine | Proveniência, licença, hashes, splits por módulo e quase duplicatas | Concluída; 18 módulos CPython, data/cpython_snapshot |
| Treinar só com partição correta | BPE reproduzível usando apenas os 12 módulos de treino | Concluída; tokenizer_reproduction.json |
| Comparar com orçamento de CPU | Dois sistemas, três seeds, 20 s CPU, checkpoint por validação | Concluída; training.json, 6 checkpoints |
| Conferir inferência | Todos os logits dos 6 modelos, mesmas sequências e NLL | Concluída; native.json, 30 rodadas nativas |
| Avaliar capacidade útil | 28 tarefas por modelo, respostas e critérios explícitos | Executada; 0/28 em cada modelo, capability.json |
| Separar ferramenta e aprendizado | Calculadora medida à parte | Executada; 12/12, não é habilidade neural |
| Executor sem confirmações | Dois perfis, falhas explícitas, hashes/cache verificados | Concluída; independent e independent-quick, 12/12 cada |
| Portabilidade e erros de memória | Release, fallback sem SIMD e ASan+UBSan | Concluída; 10 suítes CTest e 57 testes Python |
| Empacotamento reproduzível | Extrair ZIP, recompilar, retestar e conferir binários | Concluída; extração/recompilação, release_verification.json |
| Energia medida | Joules de sensor legível | Não alcançada: contadores indisponíveis; energy.json contém null |
| PC fraco / Windows | Execução no hardware/plataforma real | Não executada; host é uma VM EPYC, binários Linux x86-64 |
| Superar assistentes avançados | Comparação pública e tarefas diversas, qualidade/energia | Não demonstrada; não afirmar inteligência geral pelo próximo token |

## Decisão

BPE foi melhor em previsão e tempo da avaliação nativa neste corpus, mas o arquivo
ficou maior. Manter ambas as configurações. O gargalo principal agora é habilidade
útil e comportamento de resposta, não acrescentar outra arquitetura por aparência.

## Próximas metas, ainda não executadas

1. **Fim de resposta e instruções.** Implementar EOS explícito e aprendizado
   supervisionado de respostas completas. Comparar o mesmo modelo antes/depois,
   com tarefas de teste não vistas, famílias/templates e faixas numéricas separadas.
   Registrar a origem/licença dos dados e marcar dados sintéticos como sintéticos.
   Critério: ganhos em acerto funcional e término correto, não só queda de loss.
2. **Capacidade sob orçamento.** Comparar duas escalas controladas, aumentando
   parâmetros apenas após obter acerto útil. Mesmo orçamento CPU, todas as seeds,
   separação de tempo de treino e de ponta a ponta. Preservar o baseline menor.
3. **Generalização entre fontes.** Adicionar fontes licenciadas distintas, sem
   misturar famílias/projetos no treino e no teste. Congelar antes de treinar;
   repetir deduplicação e relatar qualidade por domínio/idioma separadamente.
4. **Medição no destino.** Usar o executor no PC fraco real; registrar CPU, RAM,
   sistema, startup/prefill/geração e joules quando houver sensor. Não extrapolar
   o host virtual nem converter TDP em consumo real.

Essas quatro metas estão registradas, não marcadas como feitas. A engine não fica
trabalhando em segundo plano após a execução. O comando local termina ao concluir
seu perfil: `python tools/run_goals.py --profile independent`.
