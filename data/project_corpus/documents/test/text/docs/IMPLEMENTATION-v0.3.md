# Plano executado — v0.3

Meta: backend nativo híbrido verificável, kernels comparáveis e resultados reproduzíveis.

- [x] Isolar cópia de trabalho da v0.2 e preservar fonte original.
- [x] Reproduzir regressão de estado e validações; registrar falhas anteriores em results/.
- [x] Corrigir estado/readout legado e testar sempre, inclusive Release.
- [x] Implementar kernels e equivalência contra referência independente; linhas não alinhadas.
- [x] Implementar estado delta/atenção limitada; validar reset, causalidade e limites.
- [x] Implementar formato EDGEAI3 e proteção de leitura; conservar EDGEAI2.
- [x] Implementar referência treinável/exportador e verificar logits Python/C++.
- [x] Executar piloto gates fixos; preservar experimento e resultados.
- [x] Escrever teste de gates por token, observar falha, implementar e repetir comparação.
- [x] Treinar modelo educativo e medir desempenho nativo sem equiparar bytes a inteligência.
- [x] Executar seis suítes em Release, fallback e ASan+UBSan; reportar energia ausente.
- [x] Registrar resultados positivos e negativos e limites de compatibilidade.

Próximo trabalho ainda não executado está em ROADMAP.md, não marcado como concluído aqui.
