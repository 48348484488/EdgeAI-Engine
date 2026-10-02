# Metas — v0.9

| Meta | Estado |
|---|---|
| Partir de base recuperável e preservar pesos | Executada, baseada em v0.7.1, hashes em preserved_models.json |
| Consulta útil sem depender de modelo | Executada: C++/CLI/chat, caminhos e linhas verificáveis |
| Tratar ausência de resultados honestamente | Executada: escopo/limites/exclusões explícitos |
| Ponte opcional para referência externa | Implementada e testada no protocolo HTTP local |
| Comparar com LLM externo real | Não executada: nenhum llama-server/GGUF instalado; download runtime falhou DNS |
| Teste controlado da busca | Executado, 14 casos positivos e 4 negativos; diagnóstico sintético lexical |
| Testar modelo preservado em prompts práticos | Executado, 2/12 exatos; sem novo treinamento |
| Execução contínua curta | Executada: useful, dez etapas; não trabalha em segundo plano após terminar |
| Recompilar/testar pacote extraído | Verificação externa vinculada ao SHA-256 do ZIP |
| Windows, PC fraco real e energia | Não medidos nesta rodada; não alegar redução em joules |

## Próximas metas (não executadas)
1. Executar a ponte contra llama-server + GGUF identificados por hash e licença;
   registrar desempenho/qualidade, não usar o servidor fixture como evidência neural.
2. Avaliar busca em outro projeto licenciado com perguntas e respostas revisadas;
   medir ambiguidades, ausência e falsos positivos, comparar também com grep/ripgrep.
3. Só então testar ganho de uma explicação neural sobre os trechos, sempre separando
   citação comprovada de interpretação. Não permitir execução de código encontrado.
4. Testar Windows e um PC fraco real. Afinar limites com RSS e latência medidos.
5. Retomar pesquisa um versus dois blocos com ensaio isolado, mantendo modelos base.
