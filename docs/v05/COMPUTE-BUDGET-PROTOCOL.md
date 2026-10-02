# Follow-up explícito: custo de aprendizado

Este experimento foi definido DEPOIS do ensaio de 400 atualizações, antes de suas
próprias execuções. Não é parte pré-registrada do ensaio principal.
O híbrido teve NLL menor por atualização, mas custou ~5.4x o tempo de treino do
Transformer INT8. Comparar só atualizações esconde o objetivo de treino rápido.

Novos ensaios: Hybrid INT8 e Transformer INT8, mesmas dimensões/dados/otimizador do
ensaio principal, seeds 11/22/33, inicialização nova. Cada execução tem orçamento de
12 segundos de tempo de CPU medido por process_time, ou 5000 passos, o que vier
primeiro. O orçamento inclui sampling, forward, backward e atualização, não leitura,
avaliação, exportação ou warmup da primeira biblioteca. Sem GPU, 1 thread.
Não são FLOPs idênticos, energia idêntica ou exposição idêntica a dados. Número de
passos pode variar por máquina; publicar todos. Checkpoint por validação a cada 100
passos e ao terminar. Teste reservado só no fim. Rodar sem outros treinos simultâneos.

Nenhum novo hiperparâmetro será escolhido pelos resultados desse teste.
