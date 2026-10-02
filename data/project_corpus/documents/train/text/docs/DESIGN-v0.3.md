# Desenho implementado — v0.3

Objetivo: melhorar e verificar a engine CPU, sem prometer capacidade geral que não foi medida.
Preservar a engine v0.2 e backend legado; nova arquitetura em arquivos separados, fábrica por magic.

Fluxo: byte → embedding FP32 → layernorm → projeções ternárias Q/K/V → memória delta e
atenção local limitada → mistura com gates de entrada → projeção → readout FFN compartilhado
em profundidade treinada → logits FP32. Estado de memória nunca recebe recirculação do readout.

Alternativas avaliadas: recorrência simples antiga; estado delta/atenção com gates globais;
estado delta/atenção com gates dependentes da entrada. Mantém-se baseline FP32 e Transformer.
Gates de entrada melhoraram FP32 mas não resolveram o modelo ternário.

API/contratos: IModelBackend preservado; `HybridBackend::step(uint8_t)` e `reset()`;
`load_backend` distingue EDGEAI2/3; `Kernel` seleciona Auto/Scalar/Lookup/Avx2.
Formato e equações em FORMAT.md. Estados limitados; buffers são reutilizados.
Não são recursos desta etapa: mmap, vários especialistas, GPU, NEON, INT8 de ativações,
saída por confiança calibrada, estado ilimitado ou modelo capaz de conversar em nível avançado.

Aceitação: falhas v0.2 reproduzidas antes da correção; testes mesmo em Release;
paridade de logits e gradientes; testes SIMD/fallback/sanitizers; qualidade independente
com múltiplas sementes; medição energética marcada indisponível quando sem sensores.
