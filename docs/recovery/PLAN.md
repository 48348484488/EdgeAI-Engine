# v0.7.1 — recuperação e entrega verificável

Base imutável: EdgeAI-Engine-v0.7.zip. Este ciclo não recupera o código ausente
nem revalida o treinamento descrito no relatório v0.8.

## Escopo fechado
1. Conferir CRC e SHA-256 da base e extrair em diretório separado.
2. Recompilar C++ e executar os testes existentes antes de modificar.
3. Adicionar empacotador Python padrão: ZIP temporário, manifesto SHA-256 por
   arquivo, verificação completa antes de publicar por substituição atômica,
   e extração em diretório novo sem sobrescrever conteúdo existente.
4. Testar integridade, arquivos alterados, caminhos perigosos, links simbólicos,
   exclusão de caches/builds, preservação de executáveis e falha de publicação.
5. Reexecutar testes, publicar pacote, extrair em outro diretório, recompilar,
   verificar modelo e repetir testes. Produzir relatório desta rodada.

## Limites
Sem treino novo, rede, dependências novas, uso de API, alterações nos pesos ou
promessa de melhor qualidade/energia. A verificação por hash detecta corrupção,
mas não autentica um distribuidor malicioso capaz de trocar pacote e manifesto.
Os resultados antigos permanecem históricos. Windows não é alvo testado.

## Registro
- Base: CRC conferido. SHA-256 de9d28113c2363a800de5e70e78339ff6bd14e4bec26c7ac23107e80d80a926b.
- Baseline nesta execução: 11/11 CTest e 69/69 unittest passaram.
- Decisão: versão 0.7.1, não 0.8, porque os modelos/código de 0.8 não estão presentes.
