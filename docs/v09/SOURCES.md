# Fontes externas consultadas

Consulta em 25/09/2026 para contrato da integração opcional:
- llama.cpp, documentação oficial do servidor:
  https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md
  Endpoint /v1/chat/completions, /v1/models; CPU -ngl 0, host/port e threads.
  Contrato consultado na branch master, mutável; não há binário/commit do servidor
  incluído ou validado. A integração utiliza apenas o subconjunto HTTP testado.
- SmolLM2-135M-Instruct, card oficial considerado como possível referência:
  https://huggingface.co/HuggingFaceTB/SmolLM2-135M-Instruct
  Não baixado, não executado, não incluído e não pontuado.

A busca lexical, fixture e adaptador novos são código deste projeto. O corpus CPython
legado, seus avisos e licenças permanecem com a base. Nenhum código ou modelo externo
foi incorporado por cópia neste ciclo; as URLs não equivalem a execução validada.
