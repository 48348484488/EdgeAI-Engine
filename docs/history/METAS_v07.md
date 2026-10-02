# Metas — v0.7.1 (recuperação)

Escopo deste ciclo: entregar novamente uma base funcional com mecanismo de cópia
verificável, sem repetir treinamentos longos nem inventar o conteúdo da v0.8.

- [x] Verificar e preservar o ZIP v0.7 original.
- [x] Recompilar a base e repetir 11 suítes CTest / 69 testes Python.
- [x] Adicionar pack/verify/unpack com manifesto, validação e publicação atômica.
- [x] Testar corrupção, caminhos perigosos, links e proteção da cópia anterior.
- Verificação da distribuição: consulte o relatório externo
  `EdgeAI-Engine-v0.7.1-VERIFICACAO.json`, vinculado ao SHA-256 do ZIP.

Metas de capacidade não foram executadas nesta correção. Permanecem no documento
`docs/history/v0.7-METAS.md`. Um ZIP baixado é a cópia recuperável; um relatório
sozinho não recupera código ou pesos ausentes. Os testes atuais não medem inteligência.
