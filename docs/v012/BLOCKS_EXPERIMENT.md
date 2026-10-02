# Experimento estrutural: 1 bloco vs. 2 blocos

Este experimento testa se um segundo bloco Transformer adiciona capacidade útil ao EdgeAI quando o orçamento de CPU permanece igual.

## Protocolo

- Base: os mesmos checkpoints congelados `seed11`, `seed22` e `seed33` da v0.6, expandidos para o tokenizer de instruções.
- Dados: o mesmo conjunto sintético congelado `data/instructions_v07`.
- Otimizador: AdamW, `lr=0.001`, `weight_decay=0.01`, batch 16, uma thread.
- Orçamento: **12 s de CPU de otimização por arquitetura/seed**.
- Seleção: menor NLL de validação entre 25/50/75/100% do orçamento.
- Avaliação final: todos os **194 casos de teste** por NLL de resposta e acurácia com *teacher forcing*.
- O segundo bloco começa como residual identidade. Antes do treino, 1 bloco e 2 blocos tiveram **diferença máxima de logits = 0.0** nos probes de paridade.

`teacher forcing` mede previsão dos tokens corretos quando o prefixo correto é fornecido. **Não é a mesma coisa que acerto em geração livre.**

## Resultado agregado — 3 seeds

| Métrica | 1 bloco | 2 blocos |
|---|---:|---:|
| Parâmetros | 71.827 | 93.699 |
| Mediana de passos em 12 s CPU | 2.231 | 1.355 |
| Mediana NLL de validação | 0,4760 | **0,3625** |
| Mediana NLL nos 194 testes | 2,8149 | **2,4919** |
| Acurácia de tokens nos testes | 57,27% | **60,20%** |
| Linhas inteiras corretas com teacher forcing | 106/582 (18,21%) | **122/582 (20,96%)** |
| CPU total de treino | 36,007 s | 36,014 s |

O modelo de 2 blocos tem **30,45% mais parâmetros** e, no mesmo tempo de CPU, executou cerca de **39,26% menos passos**. Mesmo assim:

- NLL mediano de validação caiu **23,86%**;
- NLL mediano de teste caiu **11,47%**;
- acurácia de tokens subiu **2,93 pontos percentuais**;
- linhas completas corretas com teacher forcing subiram **2,75 pontos percentuais**.

O NLL de teste do modelo de 2 blocos foi menor em **3/3 seeds**. A acurácia de tokens também foi maior em **3/3 seeds**.

## Onde melhorou — e onde não resolveu

| Grupo | 1 bloco | 2 blocos |
|---|---:|---:|
| Teste ID — linhas exatas | 43,83% | **50,62%** |
| Novos templates — linhas exatas | 19,44% | **22,22%** |
| Faixa extrapolada — linhas exatas | **0%** | **0%** |
| Tarefa nova — linhas exatas | **0%** | **0%** |
| Faixa extrapolada — tokens | 40,35% | **42,20%** |
| Tarefa nova — tokens | 32,35% | **34,31%** |

Portanto, dois blocos demonstraram **mais capacidade sob este protocolo**, mas não resolveram extrapolação nem transferência para uma tarefa nova.

## Decisão

O resultado justifica continuar investigando 2 blocos. Ele **não justifica ainda substituir o runtime padrão** porque:

1. o runtime C++ atual exporta/executa o formato de um bloco;
2. a avaliação final deste ensaio é teacher-forced, não um benchmark completo de geração livre;
3. Windows/ARM, energia e PC fraco real não foram medidos;
4. extrapolação e tarefa nova continuam com 0 linhas completas corretas.

Próxima etapa técnica: implementar suporte nativo opcional a múltiplos blocos, preservar compatibilidade com modelos antigos e então repetir geração nativa, memória e latência antes de promover um modelo de 2 blocos como padrão.

## Reproduzir

```bash
python benchmarks/blocks_v012.py --cpu-seconds 12 --seeds 11 22 33 --out results/v012/blocks.json
```

Resultados brutos: `results/v012/blocks.json`.
