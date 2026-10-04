# Portuguese v0.17 corpus

The new local templates, enumerated inputs, repository-authored seed pairs,
and separately authored supporting training facts
in sources.json are dedicated under CC0-1.0. There is no external text snapshot,
private/user conversation, scraped data, or external model API teacher.
Repository-authored describes local provenance; it does not assert human
authorship. This is a small synthetic diagnostic corpus, not a general assistant
benchmark or a sample of natural conversations.

Each source records its origin, construction method, license, and the SHA-256
of its canonical JSON content (UTF-8, sorted keys, compact separators, no newline).
Every generated record names its source and license. The manifest binds source
registry bytes, this notice, generator bytes, and all three split files.

The fixed split policy ranks seed groups by SHA-256 within each category:
10 groups go to test, five to valid, and the remaining 25 to train. All prompt
variants of a seed stay together. Train has three deterministic variants per
seed; valid and test each have the base prompt only. Thus test has 40 prompts,
balanced as ten each for greeting, definition, closed_fact, and short_instruction.
Forty separately registered supporting-facts-v017 records are train-only and
cover every calendar, alphabet, and punctuation fact, independently of which
seed questions are held out. They are not copied from test rows or selected
from test answers. Train totals 340 rows; valid remains 20 and test remains 40.
Do not use test records or their answers to train a tokenizer, fit a model,
select checkpoints, or tune templates. Only train is tokenizer/training input;
only valid may select checkpoints. Test is frozen before any training run.

The full source registry exists for reproducibility and must never be supplied
to a tokenizer/trainer: it contains held-out seed pairs. Use training_rows and
training_texts from tools/portuguese_data_v017.py or the verified train split.
Common answers can repeat across splits; prompt and answer-bearing record
overlap is rejected. Cosmetic prompt variants (NFC, case, whitespace, and
punctuation) are rejected across splits. Semantic paraphrase detection beyond
the generator's seed grouping is not claimed. Every closed-fact test answer has
supporting training knowledge under distinct authored prompts. Both training
accessors enforce exact sealed split membership before exposing any input.

CC0 reference: https://creativecommons.org/publicdomain/zero/1.0/
