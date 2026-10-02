# EdgeAI v0.5 — próximo ciclo com critérios de saída

## Intenção
Investigar capacidade por tamanho/tempo em CPU sem GPU, preservando o projeto
existente. Execução técnica autônoma autorizada pelo usuário. Nenhuma publicação,
serviço pago, alteração de repositório externo ou treino em segundo plano no chat.

## Decisões
A fonte é o ZIP v0.4 recuperado da Library (SHA256 registrado no manifesto), não
números de outras mensagens. Precisão mista já existe: não repetir o mesmo estudo.
A v0.5 adiciona um Transformer compacto nativo para comparação justa (também INT8),
um corpus congelado de arquivos reais do projeto, avaliação por byte e um executor
de metas retomável. Não implementar MoE, nova arquitetura recorrente ou aumentar
para milhões de pesos antes de demonstrar valor nos testes menores.

## Critérios
1. Preservar testes/formatos EDGEAI2/3/4 e produzir build C++17 CPU-only.
2. Um bloco Transformer causal, RoPE, janela circular limitada, FP32/INT8/ternário
por projeção, 256 bytes, norma sem parâmetros; teste Python/C++ completo.
3. Congelar corpus de código/documentação da v0.4 por arquivo, sem usar testes como
alvos de treino. Duplicatas exatas de documentos removidas, hashes e split explícitos.
4. Pré-definir 5 variantes: hybrid_fp32, hybrid_int8, hybrid_mixed,
transformer_fp32, transformer_int8. D=64, hybrid H=128 K=32, transformer H=96;
janela=64, profundidade=1, sequência=64, batch=8, 400 passos, seeds=11/22/33.
Mesmo otimizador AdamW lr=.002 wd=.01, clip=1 e mesmos blocos por seed.
Todos partem do zero; comparações de quantização preservam masters iniciais por
arquitetura. Cabeça INT8 nos modelos compactos; embeddings FP32.
5. Selecionar checkpoint somente em validação (passos 100/200/300/400).
Teste reservado com blocos de até 64 previsões, reset entre blocos/arquivos.
Reportar NLL e bits/byte e top1, inclusive baseline bigrama suavizado.
Não chamar acerto de byte de inteligência geral. Medir qualidade nativamente.
6. Medir tempo CPU/parede, pesos no arquivo, memória do processo quando disponível;
joules=null sem sensor, não estimar por tempo. Não misturar medições antigas.
7. Entregar ZIP integral com script de metas, pesos, resultados brutos e limitações.

## Riscos explicitados
Corpus autocontido e pequeno, produzido ao desenvolver este projeto, não é corpus
humano independente nem benchmark geral. Splits por arquivo podem partilhar estilo,
identificadores/boilerplate; medir sobreposição de janelas exatas e excluir blocos
teste/val copiados do treino na métrica principal. Não garante ausência de near-dup.
RoPE não inventado; backend é uma implementação de referência de um bloco.
Seleção de checkpoint e inicialização importam; três seeds não são CI estatístico.
Plataformas não executadas não podem ser descritas como certificadas.
