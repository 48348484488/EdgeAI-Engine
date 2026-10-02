# EDGEAI7: instruction token contract

Little-endian fields, same tensor layout as EDGEAI6. Magic `EDGEAI7\0`, u32
version=7; u32 dim, hidden, window, max_generate; f32 RoPE base; u32 merge_count;
merge_count pairs of u32 token IDs; u64 embedding float count; embeddings; seven
MixedMatrix payloads (query/key/value/project/up/down/output).

With M merges, IDs 0..255 are bytes, 256..255+M are merged content pieces.
BOS=256+M, RESPONSE=BOS+1, EOS=BOS+2. Total vocabulary=259+M, <=4096.
BOS and RESPONSE condition generation but cannot be predicted outputs. EOS can
be predicted, terminates the response and produces no text bytes. User strings
never encode a special ID; strings such as `<EOS>` remain ordinary text.

Prompt = BOS + encode(user bytes) + RESPONSE.
Training sequence = prompt + encode(answer bytes) + EOS. Targets shift once;
all prompt targets and right padding have -100 labels. The first answer token
is predicted from RESPONSE. EOS is always a target. No silent truncation.

`edgeai_generate` automatically frames EDGEAI7 prompts. It reports generated_tokens
including EOS if present, generated_bytes excluding all specials, stop_reason
(`eos` or `length`) and stopped_on_eos. A length cap is never labeled EOS.
The cap is min(requested max_tokens, model max_generate), both limited to 4096.
`edgeai_token_logits` accepts explicit little-endian u32 token IDs for verification.
Legacy EDGEAI5/6 vocabularies and input framing are preserved. EDGEAI6 has only BOS;
EDGEAI5 has plain bytes. Embeddings/activations are FP32, selected linears W8A32.
