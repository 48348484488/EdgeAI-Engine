# EdgeAI Engine

**Uma IA leve para ajudar na engenharia reversa de programas e jogos.**

O objetivo é analisar arquivos compilados, entender como o código funciona e, futuramente, ajudar a reconstruir funções equivalentes em C/C++. O projeto foi pensado para funcionar **localmente, sem GPU e com baixo consumo de recursos**.

> **Estado atual:** projeto experimental. Já existem ferramentas de análise de binários e um motor de IA compacto, mas **a reconstrução automática em C/C++ ainda não está pronta**.

## O que já faz?

| Recurso | Resultado atual |
|---|---|
| Analisar arquivos ELF (`.so` e executáveis) | Identifica metadados e funções que ainda tenham símbolos |
| Analisar instruções ARM32, Thumb16 e chamadas Thumb-2 | Localiza saltos e chamadas diretas `BL`/`BLX` em casos suportados |
| Mapear o fluxo do código (CFG) | Segue caminhos a partir de um endereço informado; análise parcial |
| Encontrar candidatos a funções | Segue chamadas diretas ARM `BL`, Thumb-2 `BL` e `BLX`, incluindo mudança de modo Thumb → ARM; ainda não confirma limites de funções |
| IA local em C++17 | Runtime de baixo consumo com ferramentas e modelo neural experimental |

**Exemplo prático:** ao fornecer uma biblioteca de jogo como `libGame.so`, as ferramentas podem listar funções nomeadas, endereços, saltos e caminhos de execução. Elas **não executam o jogo, não descobrem todas as funções sozinhas e ainda não geram seu código-fonte**.

## Como testar

Requisito para os analisadores: **Python 3**, sem pacotes externos.

```bash
# 1. Listar funções com símbolos preservados
python3 tools/elf_inspect.py libGame.so

# 2. Procurar saltos ARM32 em segmentos executáveis
python3 tools/arm_scan.py libGame.so --mode arm

# 3. Mapear o fluxo a partir de um endereço conhecido
python3 tools/arm_cfg.py libGame.so --entry 0x1000 --mode arm

# 4. Descobrir candidatos a funções e chamadas diretas ARM32
python3 tools/arm_functions.py libGame.so --entry 0x1000 --mode arm
```

Para código Thumb, use `--mode thumb` e informe o endereço alinhado, sem o bit que identifica o estado Thumb. Essas ferramentas usam decodificação parcial; **não escolha ARM ou Thumb ao acaso**.

Para testar as ferramentas:

```bash
python3 -m unittest discover -s tests -p 'test_elf_inspect.py' -v
python3 -m unittest discover -s tests -p 'test_arm_scan.py' -v
python3 -m unittest discover -s tests -p 'test_arm_cfg.py' -v
python3 -m unittest discover -s tests -p 'test_arm_functions.py' -v
python3 -m unittest discover -s tests -p 'test_thumb_calls.py' -v
```

## Teste com um jogo compilado

Incluímos um **jogo da velha pequeno em C**, compilado como executável ARM32 real.
Ele tem as rotinas `start`, `play` e `winner`. O teste compara as chamadas
que a EdgeAI encontra com o desassemblador LLVM Objdump:

```bash
python3 tools/validate_tictactoe_arm.py
```

Requer Clang, LLD e LLVM Objdump. O código de exemplo está em
[`examples/reverse/tictactoe.c`](examples/reverse/tictactoe.c).

O teste mede chamadas **diretas BL**, não reconstrói a lógica completa do
jogo. Uma transferência para `winner` por salto de cauda não conta
automaticamente como função descoberta.

## Validação com binários ARM reais

A verificação agora tem uma etapa própria: compilar três programas ARM/Thumb
pequenos com Clang e comparar chamadas diretas encontradas pela EdgeAI
com o LLVM Objdump. Ela mede acertos, falsos positivos e falsos negativos.

```bash
python3 tools/validate_arm_reference.py
```

Requer `clang`, `lld` e `llvm-objdump`. O resultado fica em JSON.
O workflow [Reverse engineering ARM reference](.github/workflows/reverse-arm-reference.yml)
também preserva o relatório como artefato de CI.

**Importante:** três programas pequenos comprovam apenas os casos testados,
não a precisão em jogos completos. Os números devem ser obtidos da execução;
não são estimados no README.

## Saltos de cauda e esboço de fluxo

Quando já conhecemos dois endereços de entrada, a ferramenta pode apontar um salto direto entre eles como **possível transferência de cauda**. Ela também gera um esboço comentado do fluxo, **não um código C++ funcional**:

```bash
python3 tools/arm_flow_outline.py jogo-arm.elf --entry 0x1080 --entry 0x1000 --mode arm
```

Os endereços acima são específicos do jogo da velha usado na validação; para outros executáveis, utilize as entradas corretas. Não há inferência automática de tipos, variáveis ou condições.

## Anotação inicial das instruções ARM

O analisador experimental agora reconhece algumas operações ARM32, como `MOV`, `CMP`, `ADD`, `SUB`, `B`, `BL` e `BX`, incluindo códigos de condição. As demais instruções ficam marcadas como **não suportadas**, sem inventar lógica:

```bash
python3 tools/arm_semantics.py jogo-arm.elf --entry 0x1080
```

Isso **não reconstrói variáveis nem produz C++**. Ainda falta analisar transferência de valores entre registradores, memória e ramificações. Os endereços de entrada dependem do executável.

## Rastreamento inicial de valores ARM32

A ferramenta `arm_constants.py` acompanha constantes em sequências lineares
de `MOV`, `ADD`, `SUB` e `CMP`. Por exemplo, após `MOV R0, #5` e
`ADD R0, R0, #3`, ela registra `R0 = 8`.

```bash
python3 tools/arm_constants.py jogo-arm.elf --entry 0x1080
```

Ela interrompe a análise diante de instruções não suportadas, condições ou
transferências de controle. **Não rastreia memória, junções de fluxo nem
reconstrói funções C++**.

## Constantes entre blocos ARM

O novo `arm_dataflow.py` percorre os caminhos do CFG para instruções ARM32 suportadas, acompanha constantes, avalia comparações `EQ`/`NE` e junta estados mantendo somente valores iguais entre todos os caminhos encontrados.

```bash
python3 tools/arm_dataflow.py jogo-arm.elf --entry 0x1000
```

A implementação **não é um descompilador**: interrompe caminhos em instruções desconhecidas, não modela memória nem efeitos completos de chamadas. As entradas e o conjunto ARM devem ser conhecidos.

## Qual é o próximo objetivo?

Ampliar o decodificador ARM/Thumb-2, reconhecer os limites reais das funções e validar os mapas de chamadas em binários ARM reais. A ferramenta `arm_functions.py` gera **candidatos** a partir de chamadas diretas ARM32 `BL` e Thumb-2 `BL`/`BLX` imediato, mas não cobre instruções Thumb-2 em geral, chamadas indiretas, mudanças dinâmicas de modo nem limites completos das funções. Depois, avançar para pseudocódigo e reconstrução verificável em C/C++.

## E a IA?

A EdgeAI possui um runtime local escrito em **C++17**, com ferramentas determinísticas e um pequeno backend neural. O perfil experimental v0.16 mira até **64 MiB de RAM** em uma carga de teste Linux, modelo de até **16 MiB** e **1 a 2 threads**. São metas de um perfil específico, não garantias para qualquer computador.

Na avaliação registrada, as ferramentas determinísticas acertaram **20/20** tarefas, enquanto o modelo neural de desenvolvimento obteve **0/20** respostas consideradas úteis. Portanto, **a IA ainda não realiza engenharia reversa autonomamente**.

Para compilar o runtime:

```bash
cmake -S . -B build-low -DCMAKE_BUILD_TYPE=Release -DEDGEAI_LOW_RESOURCE=ON -DEDGEAI_BUILD_TESTS=ON -DEDGEAI_BUILD_BENCHMARK=OFF
cmake --build build-low -j2
ctest --test-dir build-low --output-on-failure
```

## Documentação

- [Limites do analisador ELF](docs/elf-inspection.md)
- [Runtime de baixo consumo](docs/low-resource-runtime.md)
- [Metas técnicas](METAS.md)
- [Histórico de alterações](CHANGELOG.md)

**Resumo:** a EdgeAI está construindo os fundamentos para automatizar a engenharia reversa em PCs fracos. As ferramentas atuais produzem análises estáticas iniciais; a compreensão automática e a reconstrução completa ainda são objetivos em desenvolvimento.
