# EdgeAI — validação offline independente do GitHub Actions (23/10/2026)

## Problema observado

As execuções do [EdgeAI CI](https://github.com/48348484488/EdgeAI-Engine/actions/runs/39669371508) e do [Low-Resource CI](https://github.com/48348484488/EdgeAI-Engine/actions/runs/39669371447) encerraram com falha poucos segundos após serem criadas. A API do GitHub retornou **zero etapas executadas** e os logs não estavam disponíveis. Não há evidência de erro no C++ do benchmark nessas execuções. O status do GitHub Actions privado **continua sem resolução**; uma restrição de conta, runner, uso ou faturamento é possível, mas não foi confirmada.

## O que foi executado, sem runner GitHub

O [script offline](../tools/edgeai_offline_ci.py) recebe apenas os pacotes V7 e V12, valida os SHA-256 do ZIP e do ELF, rejeita caminhos perigosos na extração, e opera numa pasta temporária nova:

1. V7: roda os **63 testes reais** de reconstrução ARM64.
2. Regenera **16 candidatos C++** a partir do ELF AArch64 sem símbolos, compila a biblioteca e compara **byte a byte** os 16 códigos emitidos com os candidatos V7.
3. V12: executa seus **20 testes** de semântica e limites do verificador de estados.
4. Reproduz **50 rastreamentos QEMU já capturados** de 5 funções e compara PC, registradores, NZCV, memória, pontuação e retornos: **35.147 verificações**, nenhuma divergência.
5. Salva relatório JSON com os hashes de origem, coberturas reais e ressalvas.

Os testes do próprio executor estão em [test_edgeai_offline_ci.py](../tests/test_edgeai_offline_ci.py): **6/6 aprovados** (ZIP traversal, symlink, orçamento de extração, SHA alterado, arquivo ausente, verificação não desativada por `python -O`).

As evidências desta execução estão no [relatório JSON](../results/edgeai_offline_ci_repro_2026-10-23.json). Os arquivos completos V7 e V12 são distribuídos separadamente na conversa como artefatos e protegidos pelos hashes fixos no script.

## Como reproduzir

Requer Python 3.10+, `llvm-objdump`, `g++` e `gcc` instalados. Não requer GPU, jogo aberto, API externa ou chave GitHub.

```bash
python3 tools/edgeai_offline_ci.py \
  --v7 EdgeAI_2048_16_funcoes_V7_verificado.zip \
  --v12 EdgeAI_ARM64_Verificador_Unificado_5_Funcoes.zip \
  --report edgeai_offline_ci_report.json \
  --logs edgeai_offline_ci_logs

python3 -m unittest tests.test_edgeai_offline_ci -v
```

SHA-256 dos arquivos compactados:

- V7: `861d924bca40342a160aa60029aa6d5ddc2841ca087e7ab566790b799667d811`
- V12: `a1e21ab10bbd30127ac3f23a0b6b193a36b1f052cdf0bc03083609ae6db7230e`
- ELF original ARM64: `a3ca49d16ca6428291574ebd3f7c54153ef0913f8aa1eee4279408c3bf9d499b`

## Limites

Esta etapa **não descompilou funções adicionais**. O benchmark V7 permanece em **16/23 funções**, 529 instruções traduzidas. O V12 reproduz dados genuínos de QEMU capturados em execuções anteriores; não executa QEMU novamente nesta etapa. O conjunto de 50 casos e 35.147 comparações não demonstra equivalência universal do processador ou do jogo. O GitHub Actions privado ainda está bloqueado antes das etapas.

A vantagem é ter um comando reproduzível capaz de **verificar e rejeitar regressões** independentemente da disponibilidade dos runners remotos.
