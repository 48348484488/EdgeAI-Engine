# EdgeAI Engine

**EdgeAI Engine** é um motor experimental de IA local em C++ para pesquisar quanta capacidade útil pode rodar localmente com pouca CPU, RAM e energia.

O projeto combina um **modelo neural próprio e pequeno** com ferramentas determinísticas, memória local e busca de código. O foco é medir ganhos reais — não fingir que o modelo atual já é comparável a ChatGPT ou Claude.

**Versão verificada nesta branch: v0.12.0**  
**`main` permanece em v0.11 até a integração desta branch.**

## O que já funciona

| Recurso | Estado |
|---|---|
| Busca local de funções, classes e símbolos | ✅ |
| Ranking que prioriza definições sobre comentários/strings/chamadas | ✅ v0.11 |
| Índice de código reutilizado em RAM e atualização de arquivos | ✅ |
| Memória local e calculadora determinística | ✅ |
| Roteamento entre ferramentas e modelo neural | ✅ |
| Modelos próprios `.edge` em CPU | ✅ Experimental |
| Transformer nativo com 1..8 blocos | ✅ v0.12 |
| Formato multi-bloco `EDGEAI8` | ✅ v0.12 |
| Build/test Windows x64 com MSVC | ✅ CI: 15/15 CTest + smoke |
| Build/test Linux ARM64 nativo | ✅ aarch64: 15/15 CTest + smoke |
| Conversa/raciocínio geral no nível de grandes LLMs | ❌ |

A busca de código suporta C/C++, Python, Pawn, JavaScript/TypeScript, Rust, Go e outras extensões listadas em `src/CodeSearch.cpp`.

## Dados reais

### Busca de código v0.11

| Medida | Resultado |
|---|---:|
| Definição correta em 1º lugar | **24/27 (88,9%)** |
| Definição correta no Top 5 | **26/27 (96,3%)** |
| Nomes inexistentes corretamente vazios | **8/8** |
| 35 consultas na mesma sessão | **27,659 ms** |

### Transformer v0.12 — 1 bloco vs. 2 blocos

Três seeds, 60 s de CPU por arquitetura/seed e avaliação final por geração C++ nativa nos mesmos 194 casos por seed.

| Medida | 1 bloco | 2 blocos |
|---|---:|---:|
| Parâmetros | 71.827 | 93.699 |
| Arquivo `.edge` | 154.400 B | 178.976 B |
| Estado KV | 24.576 B | 49.152 B |
| Working memory numérica | 29.420 B | 56.300 B |
| Mediana de steps em 60 s | 11.269 | 6.897 |
| Mediana validation NLL | **0,4101** | 0,4352 |
| Geração nativa exata | **147/582 (25,26%)** | 138/582 (23,71%) |
| Mediana de tempo interno por caso | **0,650 ms** | 0,779 ms |

O ensaio curto teacher-forced de 12 s havia favorecido 2 blocos, mas a avaliação principal de 60 s com geração livre não reproduziu um ganho consistente: 2 blocos venceu apenas 1 das 3 seeds. Por isso, **1 bloco continua sendo o padrão**, enquanto o suporte multi-bloco permanece disponível para pesquisa.

### Profundidade: diagnóstico e melhor candidato

A ablação **equal-updates** deu ao modelo de 2 blocos exatamente o mesmo stream de minibatches e o mesmo número de optimizer updates do baseline de 1 bloco. Isso não resolveu a diferença: o baseline ficou em **147/582 exatos (149 `correct`)** e o 2-blocos random-identity em **138/582**. Portanto, menos updates no orçamento fixo de CPU não era a explicação principal.

O probe de dinâmica mostrou a causa mais provável: após apenas 128 updates, o bloco herdado havia mudado cerca de **11–12%** da própria norma, enquanto o miolo aleatório do novo bloco havia mudado cerca de **48–55%**. A partir disso, testamos uma inicialização que copia `Q/K/V/up` do bloco treinado para o bloco novo, mantendo `project/down` zerados para preservar exatamente a função inicial.

| Variante de 2 blocos | Exato/correct no teste original | Observação |
|---|---:|---|
| random-identity + equal updates | 138/582 | baseline de ablação |
| copy-inner + LR normal | 145/582 | +7 sobre random-identity |
| **copy-inner + LR interno 0,25×** | **163/582** | melhor agregado |

O baseline de 1 bloco tem **147/582 exatos** e **149/582 `correct`**. O candidato de 2 blocos com copy-inner + LR interno 0,25× chegou a **163/582** em ambas as métricas, mas no teste original venceu claramente apenas a seed 22; por isso o resultado agregado sozinho não é suficiente para promovê-lo como padrão.

Para uma replicação adicional, congelamos os modelos e construímos depois um holdout de **128 entradas novas por seed**, sem qualquer retreino: strings de tamanho 5, somas com operandos 20–29 e coeficientes 30–39, faixas que não aparecem no dataset v0.7 congelado. Nesse holdout pós-hoc, 1 bloco fez **15/384** exatos e o candidato fez **60/384**, vencendo em **3/3 seeds** (7→10, 4→41 e 4→9). É um sinal forte de generalização dentro dessas tarefas sintéticas, mas o holdout foi criado após observarmos os testes originais e não é um benchmark pré-registrado.

O custo continua real: 2 blocos usa **93.699 parâmetros**, dobra o estado KV e, no holdout executado no mesmo runner, ficou cerca de **18–21% mais lento** internamente que 1 bloco. Por isso, **1 bloco continua sendo o padrão de runtime**, enquanto copy-inner + LR interno 0,25× é o candidato neural experimental preferido para a próxima rodada de pesquisa.

Evidências: `results/v012_equal_steps/`, `results/v012/block_dynamics.json`, `results/v012_copy_init/`, `results/v012_copy_init_low_lr/` e `results/v012_fresh_holdout/`.

### Currículo v0.13 — mais dados, mesmos testes selados

Foi criado um currículo maior sem alterar os quatro arquivos de teste: `test_id`, `test_template`, `test_range` e `test_family` permanecem **byte por byte idênticos** ao benchmark anterior. O treino cresceu de **4.960 para 5.620 exemplos**, ampliando apenas o domínio permitido de treino.

No mesmo orçamento de 60 s de CPU por seed/arquitetura, o total correto subiu para **178/582 com 1 bloco** e **180/582 com 2 blocos**. O ganho, porém, veio quase todo de `test_id` e `test_template`: em `test_range`, 1 bloco fez **0/192** e 2 blocos apenas **2/192**; em `test_family`, ambos continuaram em **0/48**.

Isso mostra que aumentar exemplos próximos ao limite melhora interpolação, mas **não resolve a extrapolação algorítmica**. Os erros continuam estruturais, como somas fora do intervalo aprendido, coeficientes novos e cópia de strings mais longas. Evidência: `results/v013/` e `data/instructions_v013/manifest.json`.

Paridade Python/C++: 4/4 casos passaram, com maior erro absoluto de **3,5763e-7**.

### v0.14/v0.15 — onde a generalização realmente quebra

A v0.14 trocou o BPE por tokenização byte pura mantendo o mesmo currículo. Isso **não resolveu a extrapolação**: no comparativo agregado, BPE ficou em **358 acertos** contra **341** do byte puro; `test_family` continuou em zero e `test_range` permaneceu praticamente zerado. A curva pós-hoc mostrou cliffs nítidos perto das fronteiras de treino: somas deixam de funcionar quando os operandos saem da faixa aprendida, expressões caem depois dos coeficientes vistos e strings maiores que o comprimento treinado degradam rapidamente.

A v0.15 testou diretamente essa hipótese. O treino foi ampliado para strings de 5–6 caracteres, operandos até 39 e coeficientes até 49. O antigo `test_range` foi aposentado para essa rodada e um novo holdout foi definido **antes do treino**: strings de tamanho 7, somas com operandos 40–49 e coeficientes 50–59.

No novo range, 1 bloco fez **1/384** correto e 2 blocos fez **41/384**. O ganho do modelo de 2 blocos veio de `expression` (**25/96**) e `copy` (**14/96**), com apenas **2/96** em `uppercase`. Em **addition**, ambos ficaram em **0/96**. Ao mesmo tempo, o currículo maior reduziu o desempenho nos splits compartilhados sob o mesmo orçamento de 60 s: em `test_id`, 1 bloco caiu de 142 para 76 acertos agregados e 2 blocos de 142 para 108.

A conclusão é que o Transformer pequeno consegue alguma extrapolação de padrões/copiar tokens, mas **não demonstrou um algoritmo de soma**. Por isso a capacidade do sistema é tratada separadamente da capacidade neural: o benchmark neural-only continua sem atalhos, enquanto o runtime completo agora reconhece formas naturais como `Add: 40 + 41`, `Some: 40 + 41`, `What is the sum of 42 and 47?` e `Quanto vale a soma de 42 e 47?` e as envia para a `Calculator` determinística. Texto não matemático continua indo para o backend neural.

Evidências: `results/v014/`, `results/v015/`, `data/instructions_v015/manifest.json` e testes nativos do roteador.


### Sistema híbrido v0.15 — ferramentas separadas do neural

O mesmo `test_range` selado da v0.15 foi executado pelo runtime completo, passando primeiro pelo `Router`. O resultado foi **128/128**, mas com uma distinção importante: **128 casos foram resolvidos por ferramentas determinísticas e 0 pelo backend neural**. Isso é evidência de capacidade do sistema híbrido, não de generalização neural.

Para evitar que o resultado dependesse apenas das frases exatas do benchmark, foi criado um segundo corpus com **128 paráfrases únicas** ausentes do `test_range`: `Calculate ...`, `What is ...?`, `Repeat exactly ...`, `Repita sem alterar ...`, `Convert to uppercase ...`, `Return only x ...` e equivalentes em português. O roteador também fez **128/128**, novamente com **128 tool cases e 0 neural cases**.

Portanto, a arquitetura atual tem duas medições que não devem ser misturadas: o Transformer pequeno continua limitado fora da distribuição, enquanto o **EdgeAI completo** resolve operações estruturadas conhecidas de forma barata e exata por roteamento determinístico. Além disso, o family holdout de reversão foi executado separadamente: **16/16** em `test_family`, com **16 tool cases e 0 neural cases**. A implementação de `reverse` trabalha por code point UTF-8, evitando inverter bytes de caracteres multibyte. Evidências: `results/v015/hybrid_system.json`, `results/v015/router_paraphrases.json` e `results/v015/hybrid_family.json`.

Também foi executado um teste adversarial balanceado de fronteira do Router: **128 comandos que deveriam usar ferramenta** e **128 frases semanticamente parecidas que deveriam permanecer no backend neural**. Resultado: **128 true positives, 128 true negatives, 0 false positives e 0 false negatives**, equivalente a **precision 1,00 e recall 1,00** nesse corpus. Esse número mede apenas a fronteira de roteamento das formas testadas; não é evidência de compreensão aberta. Evidência: `results/v015/router_boundary.json`.

A calculadora também ganhou formas naturais bilíngues para operações binárias seguras. Um lote separado com **96 comandos** — 32 subtrações (`Subtract ... from ...` / `Subtraia ... de ...`), 32 multiplicações (`Multiply ... by ...` / `Multiplique ... por ...`) e 32 divisões (`Divide ... by ...` / `Divida ... por ...`) — terminou em **96/96 corretos**, todos com `route=calculator` e **0 casos neurais**. Evidência: `results/v015/router_arithmetic.json`.

## Verificação v0.12

A verificação final da branch executa Release, suíte Python, paridade Python/C++, build sem SIMD, ASan+UBSan e auditoria dos modelos legados. O resultado reproduzível fica em `results/v012/verification.json`.

- Modelos/checkpoints legados esperados: **142**
- Modelos/checkpoints experimentais v0.12 preservados no Git: **24**

## Como funciona

```text
Pergunta
   ↓
Router
   ├── cálculo     → Calculator
   ├── memória     → LocalMemory
   ├── código      → CodeIndex
   └── outros      → modelo neural
```

A estratégia é não gastar rede neural em tarefas que uma ferramenta determinística pode resolver de forma mais barata e confiável.

## Compilar

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j2
ctest --test-dir build --output-on-failure
```

O código é C++17. Linux x86-64 foi validado. **Windows x64** também está validado em GitHub Actions com MSVC Release, **15/15 CTest** e smoke do runtime híbrido. **Linux ARM64 nativo** também foi validado em runner `aarch64`, com build Release, **15/15 CTest** e o mesmo smoke híbrido. O projeto agora também faz cross-build Android NDK para **`arm64-v8a` / API 24**, gerando `libedgeai.so`, `edgeai_chat` e `edgeai_generate` como ELF AArch64. Esses resultados validam compilação/ABI; **execução física Android e hardware fraco real ainda precisam de teste prático.**

### Portabilidade Windows

O CI Windows compila todos os targets em **MSVC Release**, executa **15/15 testes CTest** e valida o caminho híbrido com `Subtract 17 from 42 → 25` via `route=calculator`. Durante a portabilidade, três testes com initializer lists foram tornados portáveis e o build MSVC passou a usar `/utf-8` para tornar determinísticos os literais UTF-8 do código e dos testes. A suíte Linux final também permaneceu verde: **15/15 CTest e 168 testes Python**.

### Portabilidade ARM64

O workflow ARM usa um runner GitHub-hosted **nativo `aarch64`** (`ubuntu-24.04-arm`), confirma a arquitetura com `uname -m`, compila Release, executa **15/15 CTest** e valida o mesmo smoke do runtime híbrido. Isso demonstra que o runtime C++ não depende de x86 para funcionar no conjunto testado.

### Android ARM64

O workflow Android usa o **Android NDK**, `arm64-v8a`, API 24 e `c++_shared`. O build Release passou e os binários foram verificados como **ELF 64-bit AArch64**; `edgeai_chat` usa `/system/bin/linker64`. O artefato inclui `libedgeai.so`, `libc++_shared.so`, `edgeai_chat`, `edgeai_generate`, `edgeai_make_demo` e scripts ADB para Linux/macOS e PowerShell. O run reproduzível `37105570269` gerou o artefato `edgeai-android-arm64-v8a` (2.003.826 bytes, SHA-256 `46f6082a9f4589b3a833729bcea187ee5f754f0af39304a476fca089b982f786`). O smoke físico preparado executa uma rota determinística (`Calculator`) e depois gera/carrega um `demo.edge` para exigir `route=neural`. Isso valida **compilação e empacotamento Android**; a execução em aparelho físico ainda precisa ser feita.

Também existe um APK mínimo de smoke com Activity Java + JNI. O build reproduzível `37105947328` passou e gerou `app-debug.apk` com **2.256.337 bytes**, SHA-256 `cb1a5c47c36937216fdb10531363ccc9312f540eefa8c27e0c13529c6eac9c1d`. O APK contém apenas `arm64-v8a` e empacota `libc++_shared.so`, `libedgeai.so` e `libedgeai_android_jni.so`. A tela permite enviar prompts ao `Engine`; o backend neural de smoke usa um modelo ternário demo em memória. O APK ainda precisa ser instalado e executado num aparelho físico para validar runtime Android real.

## Limites atuais

O EdgeAI **não é um substituto para Claude, ChatGPT ou outros LLMs grandes**. Ainda não há evidência de inteligência geral comparável, correção autônoma confiável de bugs, compreensão semântica completa de repositórios ou menor consumo de energia que grandes modelos.

O benchmark neural usa tarefas sintéticas. Energia e pico de RSS não foram medidos nesta rodada. Quando algo não foi medido, o projeto não trata como resultado.

## Próximos focos

- melhorar capacidade por unidade de CPU em vez de apenas aumentar profundidade;
- instalar/executar o APK e o smoke ADB em Android ARM64 físico e medir tempo/RSS; manter Windows x64, Linux ARM64, cross-build NDK e APK cobertos pelo CI;
- testar mudanças de dados/treino que melhorem geração livre sem dobrar o cache KV;
- continuar combinando modelos pequenos com ferramentas e memória.

## Mais detalhes

- [BENCHMARK_RESULTS.md](BENCHMARK_RESULTS.md) — resultados e metodologia atuais
- [docs/v012/BLOCKS_EXPERIMENT.md](docs/v012/BLOCKS_EXPERIMENT.md) — experimento 1×2 blocos
- [CHANGELOG.md](CHANGELOG.md) — histórico
- [METAS.md](METAS.md) — metas técnicas

---

**EdgeAI Engine é um projeto de pesquisa experimental.** Cada avanço deve vir acompanhado de teste, benchmark ou evidência reproduzível.
