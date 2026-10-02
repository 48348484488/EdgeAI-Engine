# Entrega recuperável — EdgeAI Engine v0.7.1

## O que foi feito neste ciclo

Base: ZIP v0.7 fornecido na conversa, preservado sem alterações. SHA-256:
`de9d28113c2363a800de5e70e78339ff6bd14e4bec26c7ac23107e80d80a926b`.

A base foi extraída separadamente, recompilada e testada. Foram implementados
`tools/release_bundle.py` e seus 14 testes. Eles cobrem roundtrip, corrupção com CRC
válido, truncamento, arquivos adicionais, travessia de diretórios, links simbólicos,
limite de tamanho, cópia anterior preservada quando a verificação falha, recusa de
sobrescrita por padrão, preservação do bit executável e snapshots determinísticos
na mesma plataforma. São testes do empacotador, não da inteligência do modelo.

## Evidência medida novamente

- Baseline: 11 suítes CTest e 69 testes Python, todos passaram.
- Após a mudança: 11 suítes CTest e 83 testes Python, todos passaram.
- 71 modelos `.edge`, 71 checkpoints `.pt` e quatro arquivos JSON em `models/`
  conferidos contra o ZIP original, sem alterações.
- C++ executou `Copie exatamente: aaeb` -> `aaeb` e `Maiusculas: edd` -> `EDD`
  na rota neural. `253 * 719` -> `181907` usou a calculadora determinística.
  Não se atribui esse último resultado à rede neural.
- Os binários Linux incluídos foram recompilados neste ciclo.

Logs em `results/recovery/`. `red-release.log` registra os testes falhando antes
que a ferramenta existisse; `green-release.log` e `python-final.log` registram a
implementação concluída. A mensagem legada sobre TERM no teste Python não é falha
de teste; os resumos e exit codes são verificados.

A conferência do ZIP final (manifesto, extração, recompilação e repetição dos testes)
fica no arquivo externo `EdgeAI-Engine-v0.7.1-VERIFICACAO.json`, que contém o hash do
pacote a que se refere. Isso evita alterar o ZIP para incluir um hash dele próprio.

## Escopo e limites

Não houve novo treinamento, melhoria de raciocínio ou medição de energia.
Os relatórios de pesquisa da v0.7 e versões anteriores continuam históricos.
O código/checkpoints da v0.8 não foram recuperados. Esta versão não tenta recriá-los
com base em percentuais publicados nem apresenta os resultados v0.8 como refeitos.

Plataforma testada: Linux x86-64 nesta máquina virtual, não um PC fraco real.
Windows/ARM não foram testados e não há executável Windows nesta entrega.
Python 3.10+ é necessário só para usar a ferramenta de recuperação; a inferência
C++ continua independente de Python e PyTorch. O treino histórico depende de PyTorch.

O manifesto detecta corrupção, mas não é assinatura digital de autoria. O pacote
precisa ser baixado/guardado: esta ferramenta não garante persistência de arquivos
no serviço de chat nem cria backups em nuvem. Antes de cada ensaio futuro, o comando
`pack` permite fechar uma cópia recuperável sem treinar novamente.
