# EdgeAI v0.13 — generalização selada

A v0.13 investiga a principal limitação observada na v0.12: boa melhora em casos conhecidos, mas quase nenhuma extrapolação para entradas fora do suporte de treino.

Todos os experimentos abaixo mantêm os splits `valid`, `test_id`, `test_template`, `test_range` e `test_family` da v0.12 byte-a-byte iguais. Nenhuma linha desses testes entra no treino ou na seleção de checkpoint.

## 1. Currículo numérico ampliado

O treino passou de 4.960 para 5.620 linhas, acrescentando apenas:
- somas com suporte até 29;
- expressões com coeficientes até 39.

Os testes selados continuam usando strings de comprimento 6, somas 30–39, coeficientes 40–59 e a família `reverse` totalmente inédita.

| Arquitetura | v0.12 total | v0.13 total | test_range v0.13 |
|---|---:|---:|---:|
| 1 bloco | 149/582 correct | 178/582 | 0/192 |
| 2 blocos | 138/582 correct | 180/582 | 2/192 |

O currículo melhorou bastante o domínio conhecido, mas praticamente não criou extrapolação. `test_family` permaneceu 0 em todas as seeds.

## 2. Ponte de comprimento: 512 grupos de strings com 5 caracteres

Foram acrescentados 512 grupos determinísticos de strings de comprimento 5 para copy/uppercase (2.048 linhas de treino). Strings de comprimento 6 continuaram exclusivas do teste selado.

Resultado agregado:

| Arquitetura | Total | test_range |
|---|---:|---:|
| 1 bloco | 109/582 | 0/192 |
| 2 blocos random-identity | 151/582 | 20/192 |

Nos 2 blocos, o ganho de range ficou concentrado principalmente em copy:
- seed 11: 9/16 copy;
- seed 22: 7/16 copy + 2/16 uppercase + 1/16 expression;
- seed 33: apenas 1/16 expression.

Isso demonstra que a arquitetura de 2 blocos consegue adquirir alguma extrapolação de comprimento sem ver strings de comprimento 6, mas o efeito é instável e a ponte forte prejudica o desempenho agregado em várias seeds.

## 3. Copy-inner + LR interno 0,25×

Aplicamos ao mesmo currículo de comprimento o estabilizador que havia sido o melhor candidato da v0.12.

| Variante 2-blocos | Total | test_range |
|---|---:|---:|
| random-identity | 151/582 | 20/192 |
| copy-inner + 0,25× LR | 129/582 | 4/192 |

O estabilizador não transferiu para este currículo. Ele deve ser tratado como dependente do regime de treino, não como configuração universal.

## Conclusão atual

- Mais dados próximos da distribuição melhoram IID/template, mas não bastam para extrapolação.
- Uma ponte de comprimento consegue produzir sinal real de extrapolação em 2 blocos.
- A ponte de 512 grupos é forte demais para o equilíbrio atual do treino.
- 1 bloco continua sem sinal de extrapolação de comprimento.
- Nenhum resultado justifica mudar o runtime padrão da v0.12.
- O próximo experimento é reduzir a ponte para **128 grupos**, mantendo random-identity e os mesmos testes selados.

Evidências:
- `results/v013/`
- `results/v013_length/`
- `results/v013_length_stabilized/`
- `data/instructions_v013/`
- `data/instructions_v013_length/`
