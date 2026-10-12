# EdgeAI Engine

**Objetivo: criar uma IA leve, offline e especializada em engenharia reversa.**
Queremos ajudar a entender binarios de jogos e programas (como bibliotecas `.so`),
localizar codigo e, no futuro, reconstruir funcoes equivalentes em C/C++.
O projeto tambem pesquisa uma engine de IA local para PCs fracos, sem GPU.

## Na pratica: o que funciona agora?

1. **Ler simbolos de funcoes ELF**: `python3 tools/elf_inspect.py libGame.so`.
   Se o arquivo tiver nomes preservados, o resultado JSON mostra os nomes,
   enderecos e tamanhos.
2. **Buscar desvios ARM32**: `python3 tools/arm_scan.py libGame.so --mode arm`.
   O resultado JSON mostra enderecos de instrucoes B/BL e seus destinos.
3. **Buscar desvios Thumb16**: `python3 tools/arm_scan.py libGame.so --mode thumb`.
   Mostra candidatos B e B.cond. Escolha o modo apenas quando souber qual
   conjunto de instrucoes o segmento utiliza.

Exemplo de saida ilustrativa (nao extraida de um jogo real):

```json
{
  "architecture": "ARM32",
  "mode": "arm",
  "branches": [
    {"address": "0x1000", "instruction": "BL", "target": "0x1008"}
  ]
}
```

**Limites atuais:** o scanner nao descobre automaticamente ARM versus Thumb,
nao identifica fronteiras de funcoes, nao recupera funcoes removidas dos
simbolos e nao gera C++. Ele examina candidatos sem executar o binario.
A analise completa de fluxo e reconstrucao em C/C++ sao metas futuras.

## E a inteligencia artificial?

O runtime C++17 tem ferramentas deterministicas e um backend neural pequeno,
mas **o modelo neural de desenvolvimento ainda nao produz respostas uteis
no teste de referencia (0/20)**. Resultados das ferramentas nao provam
qualidade neural. Nao afirmamos que a EdgeAI ja seja um descompilador ou
que rivalize com assistentes comerciais.

## Requisitos principais

- A engine principal roda localmente em CPU e foi projetada para baixo consumo.
- O scanner ELF experimental usa Python 3 sem pacotes externos.
- Arquivos binarios analisados nao sao executados.
- Testes: `python3 -m unittest discover -s tests -p 'test_arm_scan.py' -v`.

## Novo: mapa inicial do fluxo de execucao (CFG)

Informe um ponto de entrada confirmado de um binario ARM32 e o modo de instrucao:

```bash
python3 tools/arm_cfg.py libGame.so --entry 0x1000 --mode arm
python3 tools/arm_cfg.py libGame.so --entry 0x1001 --mode thumb
```

**Atencao:** para Thumb, informe o endereco de instrucao alinhado (sem o bit
de estado Thumb); se o simbolo tiver o bit zero definido, subtraia 1 antes
de usar `--entry`.

A saida JSON mostra instrucoes alcancadas e conexoes `taken`,
`fallthrough` e `call`. Exemplos: um salto B transfere o fluxo para
outro endereco; BL registra uma chamada e segue pela proxima instrucao.
Chamadas nao sao percorridas como parte do mesmo CFG.

Esse CFG e **parcial e experimental**: nao descobre funcoes sozinho,
nao suporta Thumb-2 completo, nem instrucao indireta com alvo desconhecido,
nem identifica codigo misturado com dados. O modo deve ser escolhido pelo
usuario. Os resultados sao candidatos, nao uma descompilacao.

Teste: `python3 -m unittest discover -s tests -p 'test_arm_cfg.py' -v`.

**Proximo passo:** aprimorar a decodificacao e validar CFGs em binarios ARM
reais com referencias independentes.

## Current status

The v0.16 low-resource profile is an opt-in runtime for weak PCs.

| Property | Contract |
|---|---:|
| Peak process RSS | at most 64 MiB on the canonical Linux CI workload |
| Model file | at most 16 MiB |
| CPU threads | 1 or 2 |
| Cold startup | at most 2 seconds on the canonical Linux CI runner |
| Network | fully offline |
| Runtime dependencies | C++ runtime only; no Python |

The focused binary includes routing, calculator and text tools, bounded local memory, and a transformer backend. It excludes Android/JNI, code search, training utilities, and unused neural backends.

## Build

Requirements: CMake 3.16+, a C++17 compiler, and Python 3 only for tests/evaluation.

```bash
cmake -S . -B build-low \
  -DCMAKE_BUILD_TYPE=Release \
  -DEDGEAI_LOW_RESOURCE=ON \
  -DEDGEAI_BUILD_TESTS=ON \
  -DEDGEAI_BUILD_BENCHMARK=OFF
cmake --build build-low -j2
ctest --test-dir build-low --output-on-failure
```

Generate an isolated development fixture and run a prompt:

```bash
./build-low/edgeai_low_resource_fixture build-low/tiny.edge
./build-low/edgeai_low_resource_cli \
  --model build-low/tiny.edge \
  --threads 1 \
  --prompt "2+2"
```

The CLI prints structured JSON containing `route`, `neural_used`, and `text`. Missing, corrupt, unsupported, or oversized models fail before backend construction.

## Verified baseline

The frozen v0.16 corpus contains 40 human-readable prompts: 20 deterministic/tool cases and 20 neural cases.

- tool accuracy: **20/20 (100%)** with the generated development fixture;
- neural human-review pass rate: **0/20 (0%)**;
- malformed/empty rate: **0/40**;
- local Windows verification: focused build and focused C++/Python tests passed.

The neural responses from the untrained development fixture were non-empty but not useful. This project does not claim parity with large language models. The baseline exists to prevent tool accuracy from hiding poor neural quality.

Linux GitHub Actions is the authoritative gate for actual peak RSS. Windows results are reported separately.

## Experimental reverse-engineering module

A new read-only ELF function inventory utility is available at
[`tools/elf_inspect.py`](tools/elf_inspect.py). It reports named function
symbols, addresses, sizes, and ELF metadata as JSON, without executing
the input binary or requiring a GPU.

```bash
python3 tools/elf_inspect.py /path/to/libGame.so --max-functions 100
python3 -m unittest discover -s tests -p test_elf_inspect.py -v
```

This is the first **static-inspection** building block, not a decompiler:
stripped functions, ARM/Thumb instruction decoding and C++ reconstruction
are not yet supported. See [scope and limitations](docs/elf-inspection.md).

## Repository layout

```text
include/edgeai/            public C++ interfaces
src/                       runtime implementation
examples/                  runnable CLIs
tests/                     C++ and Python verification
data/low_resource_v016/    frozen evaluation corpus
results/v016_low_resource/ committed baseline evidence
docs/                      design and operational documentation
.github/workflows/         active continuous-integration workflows
```

Historical research documents remain under `docs/history/`. Obsolete experiment workflows and generated trigger/manifest files are not part of the active repository surface.

## Documentation

- [Low-resource runtime](docs/low-resource-runtime.md)
- [v0.16 design](docs/superpowers/specs/2026-10-03-low-resource-runtime-design.md)
- [v0.16 implementation plan](docs/superpowers/plans/2026-10-03-low-resource-runtime.md)
- [Changelog](CHANGELOG.md)
- [Technical goals](METAS.md)

## License and scope

EdgeAI Engine is research software. Results are accepted only when accompanied by reproducible tests or retained evidence. Build success, runtime success, resource compliance, and useful neural quality are separate claims.

