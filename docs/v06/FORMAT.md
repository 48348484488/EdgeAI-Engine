# EDGEAI6 serialization

Little endian, identical MixedMatrix payloads to EDGEAI4/5.

| Field | Type |
|---|---|
| Magic `EDGEAI6\0` | 8 bytes |
| Version = 6 | uint32 |
| dim, hidden, attention window, max generation tokens | four uint32 |
| RoPE base | float32 |
| merge count M | uint32, 0..3839 |
| left ID, right ID for each ranked merge | M pairs of uint32 |
| embedding element count | uint64, exactly (257+M)*dim |
| embedding | element count float32 |
| query/key/value/project/up/down/output | seven MixedMatrix records |

Bytes are IDs 0..255. Merge i creates ID 256+i; its operands must be lower IDs.
BOS is 256+M, making the vocabulary 257+M. No EOS, padding or unknown token.
Merge output is capped at 64 bytes, duplicate byte spellings and cross-category
merges are invalid. Categories are ASCII letters/underscore, ASCII digits,
space/tab, individual CR/LF, and runs of other bytes. No Unicode normalization.

Tokenization starts with bytes and applies lowest-ranked available pairs within
category runs. Equal repeated pairs merge non-overlapping left to right. The
Python and C++ implementations are checked for ID equality and lossless roundtrip.

BOS is prepended once when starting an EDGEAI6 sequence; it is never a target byte.
It is excluded from greedy generation. The model head still includes BOS in the
training/evaluation softmax denominator. Generation masks it and renormalizes
conditional token scores. Window sizes and generation limits count TOKENS.

EDGEAI5 serialization is unchanged (256 byte-only vocabulary, no BOS/merge data).
The loader detects 5 versus 6 by matching magic and version, rejects malformed
counts/dependencies/tensor dimensions/trailing data, and keeps the scalar fallback.
