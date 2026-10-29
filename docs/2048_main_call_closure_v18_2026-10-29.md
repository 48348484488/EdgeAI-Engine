# EdgeAI V18 — auditoria source-blind de dependências da rotina principal do 2048

**Data:** 29/10/2026. **Escopo:** ELF ARM64 stripped do 2048, SHA-256 `a3ca49d16ca6428291574ebd3f7c54153ef0913f8aa1eee4279408c3bf9d499b`.

A ferramenta `tools/edgeai_2048_call_closure.py` cruza o CFG V17 da rotina `0x401758–0x401988` com as declarações `extern "C"` presentes nos 19 arquivos C++ gerados pela V15. Ela **não lê o fonte original do jogo** e não presume que arquivos gerados já tenham sido validados.

## Resultado local reproduzido

| Medida | Resultado |
|---|---:|
| Chamadas ARM64 na rotina principal | 32 |
| Destinos distintos de chamada | 17 |
| Chamadas a funções com C++ gerado | 28 |
| Chamadas a imports PLT | 2 |
| Chamadas a funções internas sem C++ | 2 |
| Chamadas indiretas não resolvidas | 0 |
| Arquivos C++ candidatos disponíveis | 19 |
| Testes novos do auditor | 9/9 |
| Testes CFG V17 + auditor V18 | 16/16 |

As **duas dependências internas diretas ainda não geradas** são `0x401704` (inicialização, saída e registro de sinal observados no disassembly) e `0x4011cc` (controle de terminal observado no disassembly). As duas chamadas PLT são `getchar@plt` e `__stack_chk_fail@plt`. O próprio corpo de `main` (`0x401758`) ainda precisa ser traduzido e compilado; um callback de sinal em `0x4016ac` também exige análise independente. **Não** é correto concluir que restam apenas duas funções no jogo inteiro: o relatório conta somente chamadas diretas feitas por `main`.

## Reprodução

```bash
python3 tools/edgeai_2048_call_closure.py \
  --cfg results/2048_main_cfg_v17.json \
  --generated-dir /caminho/para/batch_v15 \
  --expected-sha256 a3ca49d16ca6428291574ebd3f7c54153ef0913f8aa1eee4279408c3bf9d499b \
  --output results/2048_main_call_closure_v18.json

python3 -m unittest discover -s tests -p 'test_edgeai_2048_call_closure.py'
```

O diretório `batch_v15` é obtido pelo pipeline de geração V15 ou pelo pacote V15 fixado anteriormente. O auditor rejeita SHA-256 divergente, entradas diretas sem destino e fontes C++ cujo símbolo exportado não corresponde ao nome do arquivo.

**Próxima implementação:** gerar o C++ da inicialização `0x401704` e do controle de terminal `0x4011cc`, depois traduzir o corpo de `main` preservando pilha, SIMD, estado do terminal e chamadas de biblioteca. Só aumentar a contagem de funções após testes diferenciais reais. O CI privado permanece um bloqueio separado e não foi corrigido nesta etapa.

**Limite:** auditoria estática de dependências, não prova de execução de jogo completo, nem equivalência universal.
