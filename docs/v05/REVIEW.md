# Revisão interna da v0.5

Revisão executada pelo mesmo implementador, não revisão independente de outro agente.
Escopo: interfaces/exportadores, treino/avaliação, formato binário, runtime e controle
local de experimentos. Sem publicação externa ou modificação do ZIP de origem.

## Verificações e decisões

- O Transformer usa a mesma matemática em PyTorch e C++; janela causal foi testada
  contra alteração do futuro e passagem além da capacidade do ring.
- INT8 significa W8A32. Compactar o arquivo não remove masters/gradientes FP32 do treino.
- Os checkpoints são escolhidos somente na validação; todos os resultados de teste
  de todas as seeds ficam disponíveis. As famílias de arquivos são disjuntas.
- Split por arquivo não elimina similaridade de estilo/boilerplate. A exclusão de
  blocos copiados é exata; não se anuncia deduplicação semântica.
- NLL é somada por alvo; não se faz média não ponderada por documento para o agregado.
- O orçamento CPU não inclui avaliação/exportação. O Transformer vê mais lotes e
  pontos de validação; essa é uma comparação operacional, não uma igualdade de FLOPs.
- Nenhum caminho chama eval, shell para entrada do usuário, rede ou API de modelo.
  O executor usa argv e subprocess sem shell. Não instala dependências por conta própria.
- Retomada verifica identidade e hashes de arquivos completos. Não se anuncia retomada
  do otimizador depois de interrupção no meio de um treino.

## Falhas encontradas e corrigidas

1. A telemetria `loops_used` do novo backend recebia o número de bytes gerados.
   Teste antes da correção falhou; retorno agora é 1 bloco. Não altera os logits.
2. Banner interativo ainda exibia v0.4. Regressão de CLI falhou antes da correção.
3. A apresentação UTF-8 foi compartilhada entre backends e testa controles/sequências
   inválidas sem modificar o feedback de bytes brutos para o modelo.

Logs `red_*` documentam regressões detectadas, não testes finais que foram ocultados.
Testes atuais estão nos logs finais/controle research e no relatório de release.

## Limitações mantidas, não tratadas como implementadas

Não há quantização de ativações, mmap, MoE, kernel NEON, modelo pré-treinado geral,
avaliação em PC fraco físico ou sensores de energia legíveis. C++ e testes rodam no
Linux do laboratório; outros sistemas não foram certificados.
