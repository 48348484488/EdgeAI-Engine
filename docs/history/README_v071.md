# EdgeAI Engine v0.7.1 — entrega recuperável

Esta é uma atualização de **empacotamento e recuperação sobre a v0.7**.
Não é a v0.8 desaparecida, não inclui seus modelos e não reivindica seus resultados.
Não houve treinamento novo, mudança na arquitetura ou aumento de inteligência.
Os modelos anteriores estão preservados byte a byte; o runtime continua C++17.
O banner do núcleo continua v0.7: v0.7.1 identifica esta correção de distribuição.

## O que foi acrescentado

`tools/release_bundle.py` usa apenas a biblioteca padrão de Python 3.10+.
Cria um ZIP temporário, inclui um manifesto SHA-256 por arquivo, verifica a cópia
inteira e só depois publica o arquivo final. Por padrão não sobrescreve backups.
Com `--replace`, uma falha antes da publicação conserva o pacote anterior.
Se o processo for morto, pode restar um `.partial`; isso não é um pacote concluído.
A ferramenta exclui builds, caches e controle de versão, não os modelos e os dados.

```bash
# Salvar uma cópia após terminar as alterações; saída fora da pasta de origem.
python tools/release_bundle.py pack --source . --output ../EdgeAI-backup.zip

# Conferir inventário, CRC, tamanhos, permissões e hashes do ZIP.
python tools/release_bundle.py verify ../EdgeAI-backup.zip

# Recuperar em uma pasta que ainda não existe (não sobrescreve arquivos).
python tools/release_bundle.py unpack ../EdgeAI-backup.zip ../EdgeAI-restaurada
```

Use `--replace` apenas quando desejar substituir explicitamente um ZIP existente.
Um hash interno detecta corrupção; não é uma assinatura de autoria. Durante o
snapshot, não altere os arquivos de origem. Não há upload ou cópia em nuvem
implícita, treinamento automático, download de modelos ou serviço em segundo plano.

`RECUPERACAO.md` descreve esta entrega. `BENCHMARK_RESULTS.md` e `results/v07/`
são resultados históricos da base, não treinos repetidos neste ciclo.
`results/recovery/` contém os testes efetivamente refeitos neste ciclo.
O manifesto `_BUNDLE_MANIFEST.json` substitui o antigo SHA256SUMS da distribuição;
a lista antiga permanece somente em `docs/history/v0.7-SHA256SUMS.txt`.

## Usar o modelo preservado

## Usar no Linux x86-64

Na pasta extraída, usando os binários incluídos:

```bash
chmod +x bin/linux-x86_64/*
./bin/linux-x86_64/edgeai_chat models/instructions_v07/default.edge
```

Digite `sair` para fechar. Experimente instruções curtas nos formatos treinados:
`Copie exatamente: aaeb`, `Maiusculas: edd`.
Esses dois exemplos foram verificados; não são garantia para outras entradas.
O modelo pode errar até esses casos; não é um chatbot para perguntas livres.
O modelo padrão é selecionado pela perda de **validação**, nunca pelo teste.
`default.edge` é uma cópia congelada do modelo desta entrega. O executor grava
novos resultados nos arquivos `seedN-after.edge`, sem substituir automaticamente
essa cópia; para testar um novo resultado, passe seu caminho ao `edgeai_chat`.

A engine também possui calculadora e memória determinísticas; o campo `neural`
mostra a rota utilizada. Os testes de aprendizado v0.7 ignoram essas ferramentas
para não atribuir ao modelo um resultado que foi calculado por código.

## Compilar

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j2
ctest --test-dir build --output-on-failure
./build/edgeai_chat models/instructions_v07/default.edge
```

Runtime sem Python/PyTorch/Internet/GPU. Os binários fornecidos são Linux x86-64;
Windows possui fonte e `build_windows.bat`, mas não foi executado nesta entrega.
Não há `.exe` Windows ou teste em PC antigo. `EDGEAI_DISABLE_SIMD=ON` força kernels
portáveis no host suportado; isso não equivale a testar todas as arquiteturas.

## Pesquisa e executor de metas

As dependências de desenvolvimento estão em `requirements-training.txt`. Treinamento
usa PyTorch CPU e pesos mestres FP32, com quantização simulada INT8 nas projeções.

```bash
python tools/run_goals.py --profile instructions-quick
python tools/run_goals.py --profile instructions
```

O perfil completo executa 12 etapas: compila, testa, verifica os dados, confere
paridade legada, realiza três treinos de instruções, avalia sem ferramentas,
reavalia os 28 prompts antigos, compara logits/geração Python e C++, tenta medir energia e valida os relatórios.
Há 60 segundos adicionais de CPU por seed para SFT; os checkpoints-base já foram
pré-treinados na v0.6. Preparação, validação, exportação e teste são custos adicionais,
registrados à parte. Isso não é treinar uma IA geral do zero em um minuto.

O perfil rápido usa uma seed/2 segundos para testar o fluxo, não para medir qualidade.
Ensaios anteriores só são reutilizados após conferir a identidade e os hashes de
seus quatro artefatos (antes/depois, `.edge`/`.pt`). Logs e `status.json` são gravados
por etapa. Falhas interrompem explicitamente o comando. Não há execução automática
quando nenhum processo local está rodando.

## Dados e avaliação

`data/instructions_v07/` contém dados **sintéticos gerados por regras locais**,
com origem, licença e hashes. Não são respostas de um modelo grande nem conversas
coletadas de usuários. Tarefas: copiar, transformar em maiúsculas, pequenas somas e
expressões restritas. Separação por conteúdo subjacente, templates e faixas.
A tarefa de inversão é reservada como família não ensinada.

Acerto textual, correção funcional restrita e encerramento por EOS são medidos
separadamente. Uma resposta vazia que gera EOS não conta como correta. O limite de
32 tokens não conta como um fim aprendido. Todos os resultados das três seeds,
incluindo falhas, estão em `results/v07/evaluation.json`.

## Arquivos principais

- `BENCHMARK_RESULTS.md`: protocolo, resultados e limitações.
- `METAS.md`: entregas e próximas decisões verificáveis.
- `docs/v07/`: design, contrato binário, plano e registro de execução.
- `tools/sft_model.py`: expansão dos checkpoints, máscara e treino de respostas.
- `tools/instruction_data.py`: dados sintéticos e verificador restrito sem eval/exec.
- `benchmarks/instruction_v07.py`: treinamento antes/depois com orçamento de CPU.
- `benchmarks/instruction_eval_v07.py`: teste nativo sem ferramentas.
- `tools/verify_instructions.py`: paridade de logits, texto e EOS.
- `models/instructions_v07/`: os seis modelos antes/depois e os checkpoints.

Formatos anteriores e experimentos históricos estão preservados. Os relatórios
antigos não são resultados refeitos nesta versão. Não houve teste contra Claude,
nem medida de energia que permita afirmar economia por joule.
