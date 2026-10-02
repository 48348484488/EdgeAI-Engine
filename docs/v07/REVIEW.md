# Revisão v0.7

Revisão local de implementação e evidência; não houve revisor humano ou agente
independente. O objetivo é testar hipóteses pequenas, não certificar IA geral.

## Contratos conferidos

- RESPONSE/EOS são IDs fora do conteúdo BPE. Texto literal não injeta esses IDs.
- O último token do prefixo prediz o primeiro token da resposta. Prompt e padding
  são ignorados pela perda; EOS é alvo aprendido. Testes verificam posições e gradientes.
- Runtime filtra somente BOS/RESPONSE, e não EOS. O teste de saída forçada distingue
  término por token de término por limite; o teste de modelo treinado é separado.
- Warmstart mantém embeddings/saída e demais matrizes existentes. Mesma arquitetura
  antes/depois, sem alegar que inicialização dos tokens especiais já era treinada.
- Partições de dados são separadas por conteúdo subjacente, não apenas por prompt.
  As respostas podem se repetir. O diagnóstico de novas faixas permanece estreito.
- Verificação nativa compara todos os logits, texto, número de tokens e EOS. Testes
  de roundtrip binário/limites incluem dados inválidos e contextos que dão rollover.
- O verificador de expressões tem gramática pequena, limites e não executa Python
  arbitrário. Cinco testes funcionais não são prova formal de equivalência universal.
- Calculadora e memória da engine não participam do ensaio de capacidade neural.
- Seed/checkpoint padrão vêm da validação. Melhor loss não significou melhor acerto
  de teste; esse resultado negativo não foi apagado pela troca de seed padrão.
- O diagnóstico legado foi acrescentado depois e está marcado como suplementar.
- Tamanho dos pesos/estado não foi apresentado como RAM total. Energia sem sensor
  permanece null. VM, Linux x86-64 e ausência de Windows/PC antigo estão explícitos.

## Correções de revisão

1. Teste de banner herdado fixava a versão antiga: passa a derivar versão de CMake.
2. Probe energético usava benchmark que só admite byte-vocab legado: mantida a
   rejeição e utilizado gerador compatível com EDGEAI7. Teste de regressão adicionado.
3. Aviso GCC de indentação em bounds-check BPE: braces/return separados, sem alterar
   a lógica. Rebuild final e pacote usam o código corrigido.

## Limites não resolvidos por esta versão

O modelo ainda erra aritmética, não transfere para strings maiores nem para a família
não ensinada, e manteve 0/28 no diagnóstico antigo. Não há evidência para comparar
com Claude/Opus ou escalar a arquitetura de forma indiscriminada. A nova tabela mede
aprendizado em um currículo sintético restrito; não é um benchmark público amplo.

Conferências finais e códigos de saída: results/v07/build-verification/status.json,
results/v07/release_verification.json e status dos dois perfis de metas.

Default de release: cópia congelada com hash registrado. Treinar novamente gera
seedN-after.edge; não muda silenciosamente o default que foi verificado nesta entrega.
README explicita o caminho para usar um checkpoint novo.
