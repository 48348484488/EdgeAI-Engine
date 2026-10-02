# EdgeAI Engine v0.7 — instruções, EOS e limites observados

Execução: 25/09/2026. Evidências: `results/v07/`.
O objetivo deste ciclo foi aprender respostas curtas e término de geração. **Não
há comparação com Claude, nem demonstração de assistente geral ou economia elétrica.**

## 1. Implementação entregue

Mantivemos a arquitetura Transformer pequena da v0.6, sem aumento de camadas.
O tokenizador BPE é o já treinado na partição correta do corpus CPython da v0.6.
Acrescentamos somente dois símbolos especiais: RESPONSE e EOS. Vocabulário: 515;
parâmetros: **71.827**; arquivo `.edge`: **154.400 bytes** em cada variante.

O novo formato EDGEAI7 embute esse contrato. O runtime C++ enquadra a entrada como
`BOS + prompt + RESPONSE` e encerra quando a própria rede emite EOS. O token EOS
não aparece no texto. BOS/RESPONSE não podem ser produzidos como conteúdo durante
a geração. Texto do usuário não se transforma em tokens de controle por conter
nomes como “EOS”. EDGEAI5/6 e os backends históricos foram preservados.

Treinamento supervisionado: perda apenas nos tokens da resposta e no EOS, com
entrada deslocada uma vez; prompt e preenchimento não contam como alvos. A saída
vazia seguida de EOS não conta como resposta correta. O limite de geração continua
existindo como proteção, mas atingir o limite não é um encerramento aprendido.

Isso é uma aplicação de SFT e completion-only loss, técnicas conhecidas, não uma
arquitetura inédita. Fonte metodológica: `docs/SOURCES.md`.

## 2. Dados congelados, sintéticos e limitados

`data/instructions_v07/` foi gerado por regras locais. Não houve API de modelo
professor, coleta de conversas pessoais ou corpus humano de instruções. Os novos
exemplos são dedicados sob CC0-1.0; o CPython do pré-treinamento conserva sua licença.
Manifesto, hashes, gerador e licença estão no pacote. Os dados de avaliação não
entraram no otimizador nem na seleção do checkpoint.

| Partição | Exemplos | O que separa |
|---|---:|---|
| Treino | 4.960 | Conteúdos de treino, quatro tarefas |
| Validação | 128 | Outros grupos de conteúdo, templates familiares |
| Teste ID | 54 | Novos conteúdos, templates familiares |
| Novos templates | 60 | Novos conteúdos e novas formas de instrução |
| Novas faixas | 64 | Strings maiores ou números fora da faixa ensinada |
| Família não ensinada | 16 | Inversão de strings, ausente do treino |

As tarefas ensinadas são cópia, maiúsculas, pequenas somas e expressões restritas
`x+k`, `x-k`, `x*k`. Strings de treino usam apenas `abcdef`, de 1 a 4 caracteres;
addendos 0..19 e coeficientes 0..29. Extrapolação usa strings de comprimento 6,
addendos 30..39 e coeficientes 40..59. As instruções são português/inglês, com poucas
formas e grafia simples. Isso **não** representa domínio amplo desses idiomas.

Grupos são o conteúdo da string (compartilhado entre cópia e maiúsculas), pares
não ordenados de addendos, ou coeficientes (compartilhados entre operadores).
Grupos e prompts exatos não atravessam as partições. Rótulos/respostas podem se
repetir entre partições. O código verifica as separações e reproduz os hashes.
Para comprimentos extrapolados, usamos um subconjunto lexicográfico de strings;
o diagnóstico é estreito e não uma amostra uniforme da linguagem.

## 3. Protocolo antes/depois

Três checkpoints independentes da v0.6, sementes 11/22/33, recebem 60 segundos
**adicionais** de CPU por treinamento. O pré-treinamento anterior não é gratuito
nem incluído nesse orçamento. O “antes” já contém os dois tokens recém-inicializados;
o “depois” tem exatamente a mesma arquitetura e vocabulário, agora ajustados.

Uma thread; batch 16 com amostragem equilibrada por tarefa; AdamW lr 0,001,
weight_decay 0,01; clipping de norma 1; comprimento máximo 128 sem truncar exemplos.
Parâmetros mestres, gradientes e otimizador são FP32; projeções simulam W8A32.
**Isso não é treinamento inteiro INT8.**

O orçamento contabiliza atualizações completas e amostragem. Inicialização,
validação, exportação, compilação e avaliação são registrados separadamente.
Um orçamento por tempo não garante o mesmo número de atualizações ou pesos
bit a bit ao repetir em outro host. A reprodutibilidade aqui é do protocolo e
dos artefatos distribuídos, com hashes; não uma promessa de métricas idênticas.
O último passo pode ultrapassar levemente o tempo. Avaliação de validação em
25/50/75/100% do orçamento; seleção pela menor NLL de resposta, não pelo teste.

| Seed | Atualizações | Passo escolhido | CPU treino (s) | NLL validação ↓ | Acertos depois | EOS depois |
|---|---:|---:|---:|---:|---:|---:|
| 11 | 4,815 | 4,815 | 60.006457 | 0.585036 | 44/194 | 194/194 |
| 22 | 4,796 | 2,394 | 60.003121 | 0.396803 | 32/194 | 193/194 |
| 33 | 5,292 | 5,292 | 60.006190 | 0.418448 | 42/194 | 194/194 |

Antes do ajuste: **0/194 acertos e 0/194 EOS em cada seed**.
`default.edge` é a seed 22, escolhida pela validação, embora tenha menos acertos
no teste que as outras duas. Isso revela que NLL de validação não é igual a acerto
funcional; não trocamos a regra depois de observar o teste. Todos os checkpoints
antes/depois e seus hashes permanecem disponíveis.

## 4. Capacidade sem calculadora, roteador ou memória externa

Usamos o backend neural C++ diretamente, geração greedy, limite de 32 tokens
incluindo eventual EOS. São **194 problemas distintos, repetidos nos três modelos**;
582 avaliações não significam 582 problemas diferentes. As mesmas entradas são
usadas antes/depois. Nada é corrigido por ferramenta antes de pontuar.

| Grupo | Acertos antes | Acertos depois, somados nas 3 seeds | Taxa depois |
|---|---:|---:|---:|
| Template familiar, conteúdo não visto | 0/162 | 80/162 | 49,38% |
| Template novo e conteúdo não visto | 0/180 | 38/180 | 21,11% |
| Faixas/comprimentos maiores | 0/192 | 0/192 | 0% |
| Família não ensinada | 0/48 | 0/48 | 0% |
| **Total** | **0/582** | **118/582** | **20,27%** |

117/582 saídas são textualmente idênticas à resposta. Uma expressão adicional é
funcionalmente correta em cinco valores de x (-5,-1,0,2,7); daí 118 acertos pela
métrica funcional restrita. Esse teste finito não prova equivalência para qualquer
programa. O interpretador aceita apenas uma expressão pequena com x, inteiros,
soma/subtração/multiplicação; não usa `eval`, `exec` ou shell.

Por tarefa, após ajuste: cópia 62/144, maiúsculas 49/144, adição 3/144,
expressão 4/102, inversão 0/48. O avanço concentra-se em transformações curtas,
não em aritmética geral ou programação. Não existe transferência demonstrada
para números maiores, sequências maiores ou tarefas não ensinadas.

**EOS ocorreu em 581/582 avaliações (99,83%), mas apenas 118 foram corretas.**
Parar de escrever não é saber responder. A mediana caiu de 32 tokens (antes,
limite) para 4 (depois), porém respostas mais curtas e erradas não demonstram
mesmo trabalho útil com menos energia.

Exemplos reais do modelo padrão, retirados do teste ID após avaliação:

```text
Copie exatamente: aaeb  -> aaeb
Copie exatamente: bbac  -> bbac
Maiusculas: edd         -> EDD
```

São exemplos ilustrativos escolhidos depois; as taxas acima incluem todas as
falhas e não são calculadas apenas nesses exemplos.

## 5. Transferência ao diagnóstico antigo: resultado negativo

Como auditoria suplementar, depois da avaliação principal reexecutamos os 28
prompts da v0.6, sem alterar as tarefas: 12 contas, 8 cópias com caracteres mais
variados e 8 expressões de funções. **Todos os modelos ficaram em 0/28, antes e
depois.** Os modelos ajustados emitiram EOS em 28/28, mas sem respostas corretas.

Não houve seleção ou novo ajuste com esses resultados. Esse ensaio foi
adicionado depois, portanto não é parte do protocolo principal pré-registrado.
Os prompts/critério de correção são os anteriores, mas o contrato novo de prompt
e o limite de 32 tokens (antes 48) mudaram: não é reprodução idêntica da v0.6.
`legacy_diagnostic.json` registra cada saída. A melhora no novo currículo **não
se transferiu para esse conjunto mais amplo**.

## 6. Runtime, memória e energia

Host real deste ciclo: Intel Xeon Platinum 8272CL @ 2,60 GHz, VM Linux x86-64,
cinco CPUs lógicas disponíveis; treinamento limitado a uma thread. Python 3.13.5,
PyTorch 2.10.0+cpu. Isto não é medição no PC fraco do usuário. Os tempos internos
por resposta também incluem carga/entrada e flutuação da VM; não são comparação
justa de velocidade entre tarefas corretas equivalentes.

Modelo: 154.400 B em disco; pesos numéricos residentes 152.168 B; estado numérico
24.576 B; working buffers incluindo estado 29.228 B. Estas contagens **não** são
a RAM total do processo (faltam strings, objetos, alocador, bibliotecas etc.).
Não somar novamente o estado aos working buffers.

O probe elétrico executou a geração e terminou com código 0. O host não expõe
contadores RAPL legíveis: `package_energy_joules=null`. Não converter tempo,
TDP, quantidade de tokens ou uso de CPU em joules. Não há comparação energética
com Claude/Opus.

## 7. Correção, reprodução e entrega

- 11 suítes CTest e 69 testes Python, incluindo legado, máscaras de gradiente,
  separação dos dados, tokens especiais, EOS real versus limite e formato binário.
- 36 comparações de todos os logits Python/C++ e 24 de geração/EOS, nos seis
  checkpoints antes/depois. Erro absoluto máximo **2.05039978e-05**;
  tolerâncias absoluta/relativa 6e-5. Casos incluem Unicode, todos os bytes,
  rollover de contexto e tokens especiais.
- A validação compara os hashes dos relatórios e artefatos, não aceita relatórios
  antigos apontando para pesos novos. Resultados de treino em cache são rotulados
  e só reutilizados se identidade/configuração/código/artefatos conferirem.
- `instructions` e `instructions-quick` executam 12 etapas sem confirmações.
  O perfil rápido tem 1 seed/2 s e serve ao fluxo; não entra nas taxas acima.
- Logs da configuração portátil, sanitizadores e extração/recompilação estão em
  `results/v07/build-verification/` e `results/v07/release_verification.json`.
  Os estados efetivamente executados são registrados nesses arquivos.

Falhas históricas `red_*` preservadas documentam regressões antes da correção:
expectativa do banner antigo em um teste e workload de energia que rejeitava BPE.
O guard do benchmark legado foi mantido; trocamos o probe para o gerador compatível.
Não são resultados de testes finais passando por cima de falhas.

Binários entregues: Linux x86-64, sem biblioteca neural externa para inferência.
Código e script Windows permanecem, mas Windows/ARM/PC antigo não foram testados.
PyTorch/Python só são necessários para treinamento e ferramentas de pesquisa.

## 8. Decisão para o próximo ciclo

A hipótese “SFT + EOS ensina algumas respostas e término” teve apoio restrito.
A hipótese “isso basta para generalizar” não. Não escalar para bilhões com base
nesses resultados. Próximas comparações devem manter um orçamento de CPU e testar
uma hipótese por vez: seleção por acerto de validação, diversidade do currículo,
ou capacidade estrutural (1 versus 2 blocos), com testes novos congelados antes
da seleção. O teste já observado deve ser tratado como diagnóstico conhecido,
não como um conjunto permanentemente cego para alterações futuras.

### Conferência final da entrega

Release, fallback sem SIMD especializado e Clang ASan+UBSan passaram as 11 suítes
CTest e os 69 testes Python. O código do ZIP provisório foi extraído, recompilado
e retestado. Os binários distribuídos produziram `aaeb` e `EDD` com neural=1.
O ZIP final acrescenta os registros desta verificação e hashes; fonte/modelos
permanecem os mesmos. SHA256SUMS.txt cobre cada arquivo entregue, exceto o próprio
manifesto. A integridade do ZIP final foi conferida separadamente.
