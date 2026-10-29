# EdgeAI: verificacao de fidelidade para HUDs Unity (LITE 7.3)

O novo fluxo e **engenharia reversa deterministica**, nao inferencia visual por inteligencia generativa. Usa apenas Python da biblioteca padrao, com baixo consumo de RAM e sem GPU para a auditoria de codigo/configuracao.

## Ferramentas

- `tools/unity_ui_behavior_audit.py` percorre o C# descompilado, encontra a associacao original entre `ClickListener.Get(btn)` e `OnClick*`, extrai o corpo do metodo com delimitacao por chaves e preserva arquivo, linha e SHA-256. Compara as referencias no cliente C++ e registra funcoes nao implementadas ou comportamentos inventados. **14 controles de construcao** tinham callback confirmado no `BattlePanel.cs` do LITE 7.3; `btn_lantu` nao tinha callback comprovado naquele arquivo.
- `tools/unity_buildpart_decode.py` processa `assets/cfg/cfg.BuildPart.oc`, aplica limites rigorosos aos comprimentos de strings e registros e preserva bytes de extensoes de formato desconhecido com SHA-256. Usa a ordem original `BuildPart.GetAllList()`, `basic && lv == 1` e `BuildManager.GetBasicPartByType()`.
- O resolvedor de sprites exige a referencia exata `BuildPart.icon` (bundle + nome), retornando o PathID original. Arquivos parecidos, nomes duplicados e recursos ausentes nunca recebem associacoes aproximadas.

## Teste real (29/10/2026)

A execucao publica [Actions 40841337262](https://github.com/48348484488/last-Island-of-survival-lite/actions/runs/40841337262) testou a implementacao espelhada do EdgeAI contra um XAPK completo de 17 partes e reconstruiu:
- 638 registros `BuildPart` reais.
- 35 pecas com `basic=true` e `lv=1`: 4 fundacoes, 9 paredes, 3 escadas, 8 janelas/portas, 3 obstaculos, 8 pisos/tetos.
- IDs, ordem de exibicao, PathIDs e sprites de cada uma dessas 35 entradas.
- Angulos de rotacao `OnceAngle`, inclusive 0, 90, 120 e 180 graus; nao assumir 90 graus para todas as pecas.

Os testes de estrutura, corrupcao do arquivo, truncamento e nomes ambiguos passaram. A auditoria de C# rodou em [Actions 40838822697](https://github.com/48348484488/last-Island-of-survival-lite/actions/runs/40838822697).

## Limites e proibicoes de conclusao

A leitura do `BuildPart.oc` detectou diferencas entre o layout binario da versao 7.3 e o C# descompilado, com campos extras. O parser **nao afirma conhecer todos os campos da extensao**: preserva os bytes desconhecidos sem inventar nomes ou significados. O `OnceAngle` e apresentado conforme o campo recuperado nos registros nivel 1, mas outros efeitos de runtime requerem validacao no jogo.

O EdgeAI **nao executou a cena Unity original** nem provou pixel-paridade, shaders, alinhamento de CanvasScaler, fisica de socket, permissao do servidor ou todas as acoes contextuais. `BuildPart.model` e um caminho de prefab, nao prova da extracao de sua malha 3D. O Android usa Raylib e precisa recriar esses comportamentos separadamente.

O GitHub Actions do repositório privado EdgeAI pode ser bloqueado antes das etapas por configuracao da conta. Por isso a execucao com fontes originais e a aprovacao publica estao documentadas no projeto LITE, sem confundir status de runner privado com falha do codigo.
