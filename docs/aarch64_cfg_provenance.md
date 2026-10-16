# AArch64: rastreamento entre blocos (EdgeAI)

**Novo modulo:** `tools/aarch64_cfg_provenance.py`.

O analisador usa o grafo da funcao (CFG), o inventario de desvios indiretos
e a desmontagem LLVM para acompanhar uma base de tabela calculada por
`ADRP + ADD`, inclusive quando as instrucoes ficam em blocos diferentes.

## Executar

```bash
python3 tools/aarch64_cfg_provenance.py \
  results/arm64-cfg.json \
  results/arm64-indirect.json \
  results/arm64-llvm-disassembly.txt \
  --output results/arm64-cfg-provenance.json

python3 -m unittest discover -s tests -p 'test_aarch64_cfg_provenance.py' -v
```

Os tres arquivos devem descrever a **mesma funcao e o mesmo ELF**.
O CFG pode ser gerado com `tools/aarch64_cfg.py`, e o inventario com
`tools/aarch64_indirect_audit.py`. A desmontagem LLVM e uma entrada
separada. Este comando nao baixa nem executa o jogo.

## Resultado e garantias

- `STATIC_CFG_BASE_CANDIDATE`: todos os caminhos **explicitamente
  representados** desde a entrada da funcao levam a mesma origem
  `ADRP + ADD` para o registrador-base, na analise conservadora.
- `UNKNOWN_REACHING_BASE`: ao menos um caminho modelado altera/perde a
  origem, ou a desmontagem e insuficiente.
- `UNREACHABLE_UNDER_PARTIAL_CFG`: o local nao aparece alcançavel pelo
  grafo parcial a partir da entrada declarada.
- `NOT_RELATIVE_TABLE`: nao corresponde ao padrao de salto reconhecido.

O algoritmo rejeita instrucoes desconhecidas, clobbers de registradores
volateis em chamadas e enderecamento de memoria que atualiza o registrador
base. Tambem confere cobertura dos blocos, conjunto de arestas e alvos de
desvios diretos com LLVM.

**Limites:** continua sendo uma prova apenas *sob as arestas estaticas
representadas*. Desvios indiretos ainda nao resolvidos podem abrir caminhos
ausentes; entradas externas no meio da funcao nao sao descartadas. O modulo
nao le entradas de tabelas, nao verifica guardas de indice, nao reconstrói
C++ e nao comprova alcance em runtime. Nenhum dado de jogo/ESP e inferido.

## Evidencia

A bateria local da mudanca inclui 12 testes de casos sinteticos:
caminhos que convergem, uma rota com clobber, chamadas, instrucoes
desconhecidas, instrucoes faltantes, saltos adulterados, grafo incompleto e
escrita implicita de ponteiro. Nenhum ELF comercial foi executado por esses
testes. A validacao completa no GitHub Actions e independente e deve ser
verificada pelos resultados do workflow.
