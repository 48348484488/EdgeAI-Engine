# EdgeAI Engine v0.9 — consulta local de código

Base: **v0.7.1 recuperada**. Esta entrega não recupera o código/modelos ausentes da
v0.8 e não repete os números de seu relatório como experimento novo.

## O que funciona agora

Consulta lexical em C++17 que retorna arquivo relativo, linha da ocorrência e trecho
real, sem rede neural, internet ou GPU. Suporta fontes C/C++, Python, Pawn (.pwn/.inc),
JavaScript/TypeScript, Rust, Go e extensões listadas em `src/CodeSearch.cpp`.
Não é resolução semântica de símbolos, AST, compilador, corretor de bugs nem LLM.
Usa nomes/palavras presentes no código e uma heurística simples de ordenação.

Os modelos `.edge` e checkpoints da base permanecem byte a byte idênticos. Não houve
treinamento neste ciclo. O modelo próprio continua experimental e muito limitado.

## Usar no Linux x86-64

Do diretório extraído (binários incluídos):

```bash
chmod +x bin/linux-x86_64/*
./bin/linux-x86_64/edgeai_code_search . "Onde fica a função greedy_token?" --limit 3
./bin/linux-x86_64/edgeai_code_search data/code_demo CarregarConta --json
./bin/linux-x86_64/edgeai_chat --code-root . --memory :memory:
```

No chat, digite `buscar codigo: greedy_token` ou `/code greedy_token`.
A pasta é escolhida explicitamente por `--code-root`; não há varredura automática do
computador. O chat pode receber o modelo por caminho como nas versões anteriores:

```bash
./bin/linux-x86_64/edgeai_chat models/instructions_v07/default.edge --code-root . --memory :memory:
```

Resultados mostram `neural=0` para a consulta de código. Não existe chance calibrada
de acerto: o score de ordenação lexical não é confiança de uma resposta.

## Compilar

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j2
ctest --test-dir build --output-on-failure
```

Windows: fonte C++17 e `build_windows.bat` preservados, com CMake + compilador C++.
**Não foi compilado/executado no Windows neste ciclo, e não há .exe incluído.**
O binário Linux foi compilado numa VM moderna; um PC antigo pode exigir recompilar
na distribuição dele. Não há garantia de compatibilidade universal de CPU/glibc.
`-DEDGEAI_DISABLE_SIMD=ON` foi testado para o caminho portável dos kernels.

## Escopo, limites e privacidade da busca

Cada consulta reconstrói um snapshot limitado e somente leitura. Não cria índice em
disco nem altera fontes. Usa no máximo 2.000 arquivos, 256 KiB por arquivo, 8 MiB de
texto no total, 100.000 linhas e profundidade 20. Linhas acima de 4.096 bytes fazem
o arquivo ser ignorado. Esses limites são de entrada, **não garantias de RSS**.
Há custos de strings, containers, processo e bibliotecas além do tamanho do texto.

Não segue links simbólicos dentro da árvore. Ignora arquivos/pastas ocultos,
`node_modules`, `vendor`, `build`, `dist`, `target`, `bin`, `models`, `results`, `data`,
`third_party`, entre outros; extensões não reconhecidas, binários e UTF-8 inválido
também não entram. Uma pasta como `data/code_demo` pode ser escolhida diretamente
como raiz. Não implementa todas as regras de `.gitignore`.

Alguns nomes comuns de credenciais são excluídos, mas **não é detector de segredos**.
Nada da busca é enviado automaticamente ao modelo externo. Não use uma árvore que
outro processo hostil possa modificar ao mesmo tempo como fronteira de segurança;
não é um sandbox contra trocas concorrentes de caminhos.

`partial=true` informa limite/erro de leitura. Exclusões normais são contadas à parte,
mesmo com `partial=false`. Resultado vazio significa apenas: nenhum trecho nos
arquivos inspecionados. Não prova que a função inexiste ou que a implementação é segura.
A saída inclui a melhor linha por arquivo; múltiplos arquivos podem ter ocorrências.

## Workbench opcional: Python padrão, sem PyTorch

```bash
python tools/workbench.py search . greedy_token
python tools/workbench.py ask "Copie exatamente: aaeb" --backend edge
python tools/workbench.py compare --out results/minha-comparacao.json
```

`compare` sem servidor executa somente o modelo próprio e marca a referência como
`not_requested`, com acurácia `null`. Os 12 prompts são um pequeno diagnóstico
sintético conhecido, não benchmark independente de inteligência geral.

## Referência externa opcional (llama.cpp)

O cliente usa o endpoint documentado `/v1/chat/completions` de um `llama-server`
rodando no mesmo computador. **O executável llama-server e o modelo GGUF não estão
incluídos.** Esta integração foi testada com um servidor HTTP de contrato, não com
um modelo externo real nesta sessão: downloads do runtime falharam por DNS.

Após obter por conta própria um llama-server e um GGUF compatível, um comando CPU
é (os argumentos estão documentados pelo projeto; não foi executado aqui):

```bash
llama-server -m /caminho/modelo.gguf --host 127.0.0.1 --port 8080 -ngl 0 -c 2048 -t 2
python tools/workbench.py ask "Explique uma função simples." --backend reference
python tools/workbench.py compare --reference-url http://127.0.0.1:8080/v1 --out results/comparacao-local.json
```

Escolha `--reference-model ID` quando o servidor expuser mais de um modelo.
O cliente aceita somente endereços loopback, ignora proxies, não segue redirecionamentos,
não baixa nada, não executa tool calls e não faz fallback para serviços externos.
Respostas HTTP têm limite de 2 MiB e timeout de socket. Falhas não são contabilizadas
como respostas erradas de modelo; ficam indisponíveis e o CLI retorna código 2.

Essa ponte é uma ferramenta Python separada; não é um novo IModelBackend HTTP em C++.
A inferência `.edge` e a busca nativa não dependem dela. Os custos de pré-treinamento,
parâmetros e tokenizadores diferem: comparar aplicações não prova superioridade de
arquitetura. A latência nativa inclui carregar um processo/modelo por pergunta; a
referência usa servidor já iniciado. O relatório declara essa diferença.

## Ciclo verificável, sem treinamento longo

```bash
python tools/run_goals.py --profile useful
```

Dez etapas: compilação, testes C++/Python, busca, diagnóstico neural, contrato HTTP,
paridade Python/C++, tentativa de energia e pacote temporário validado. Esse perfil
usa PyTorch instalado apenas para revalidar a paridade dos modelos antigos. Não
instala dependências automaticamente nem exige um modelo externo.

Recuperação de artefatos preservada:

```bash
python tools/release_bundle.py pack --source . --output ../EdgeAI-backup.zip
python tools/release_bundle.py verify ../EdgeAI-backup.zip
```

Resultados, falhas históricas esperadas de testes RED e limitações:
`BENCHMARK_RESULTS.md`, `METAS.md`, `results/v09/`, `docs/v09/REVIEW.md`.
