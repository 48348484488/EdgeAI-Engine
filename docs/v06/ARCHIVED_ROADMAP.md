# EdgeAI — direção após v0.6

## Já medido

- Backend híbrido e Transformer preservados; formato EDGEAI6 integra BPE nativo.
- Corpus externo à engine, tokenizador treinado só na partição de treino.
- BPE melhorou bits/byte e tempo da avaliação sobre texto idêntico neste ensaio.
- Arquivo BPE maior; não há economia energética demonstrada.
- Nenhum modelo neural concluiu as 28 tarefas práticas sob os critérios fixados.
- Calculadora resolve seus próprios casos; não confundir com inteligência neural.

## Próxima etapa técnica

1. Implementar token EOS e treinamento supervisionado, com testes de parada e
   dados rotulados/famílias separados antes de treinar. A ausência de EOS e a
   geração fixa de 48 tokens são limitações explícitas do diagnóstico atual.
2. Comparar modelos antes/depois desse treinamento, mesma capacidade e orçamento,
   avaliando acerto e custo por tarefa concluída. Não escolher checkpoint pelo teste.
3. Só então estudar escala moderada, vocabulário/embedding quantizado e dados
   diversificados, mantendo CPU, memória e qualidade como métricas separadas.

## Critérios de publicação

Código e dados com hashes; comandos reproduzíveis; testes de erro e paridade;
medições próprias identificando hardware; comparação em tarefas iguais; falhas
incluídas. Resultado de laboratório não é superioridade sobre modelos comerciais.
Sem API externa, postagem, cobrança ou instalação automática escondida.
