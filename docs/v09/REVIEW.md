# Revisão e limitações

Revisão feita pelo implementador, não por agente/revisor independente.
- Baseline v0.7.1 recompilado antes das mudanças: 11 CTest / 83 Python.
- Modelos: comparação por hash com o ZIP original, 142 arquivos (.edge/.pt) intactos.
- Busca: inicialmente nomes de arquivos com newline eram aceitos; um teste real
  reproduziu citações textuais ambíguas. Corrigido para ignorar controles no caminho.
  RED em red-control-path.log, GREEN nas suítes finais.
- Fontes e consulta têm limites; JSON escapa corretamente; fonte UTF-8 é validada.
- HTTP aceita loopback apenas, não usa proxies nem segue redirect. Fixture é teste
  de transporte, não execução de llama.cpp/modelo. Nenhum resultado de qualidade
  externo foi inventado ou agregado à pontuação do modelo nativo.
- A fonte pode mudar durante leitura: a API não é sandbox contra TOCTOU hostil.
- Não há detector completo de segredos, AST, semântica de símbolos ou .gitignore.
- Limites de tamanho de texto não são limite rígido de RSS do processo.
- Não há persistent KV compartilhado no harness nativo; comparação futura declara
  startup por pergunta no `.edge` e servidor externo já iniciado.
- No Windows o código é disponibilizado, mas não houve execução comprovada.
- Compilação/teste em VM não demonstra bateria/energia nem compatibilidade universal.
- Houve um timeout da chamada agregada durante as verificações. As suítes incompletas
  foram repetidas por completo; apenas logs finais completos sustentam a entrega.
