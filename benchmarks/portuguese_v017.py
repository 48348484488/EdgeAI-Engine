#!/usr/bin/env python3
"""Deterministic CPU-only response training for the sealed Portuguese v0.17 data.

The test split is never loaded here. Training uses Task 1 train rows, tokenizer
input is train-only, and checkpoint selection uses validation response NLL.
PyTorch is imported only when a real training run starts so data contracts can
be checked even on systems where its native runtime cannot load.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import random
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "data" / "portuguese_v017"
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from byte_bpe import ByteBPE  # noqa: E402
from portuguese_data_v017 import (FORMAT as DATA_FORMAT, SPLITS as DATA_SPLITS,
                                  SPLIT_POLICY as DATA_SPLIT_POLICY,
                                  _generate_dataset, _sources, validate_sources)  # noqa: E402

IGNORE_INDEX = -100
PROTOCOL = "edge-portuguese-v017-response-only-cpu-1"


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _atomic_json(path: Path, value: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_bytes(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                indent=2, allow_nan=False).encode("utf-8") + b"\n")
    os.replace(temp, path)


@dataclass(frozen=True)
class TrainConfig:
    dim: int = 16
    hidden: int = 24
    blocks: int = 2
    max_vocab: int = 1024
    context_window: int = 64
    optimizer: str = "AdamW"
    learning_rate: float = 0.001
    weight_decay: float = 0.01
    response_only: bool = True
    threads: int = 1
    steps: int = 2
    response_tokens_per_step: int = 128
    seeds: tuple[int, ...] = (11,)
    out: Path = Path("build/v017-quick")

    def __post_init__(self):
        if self.dim < 4 or self.dim % 2 or self.hidden < 4:
            raise ValueError("invalid model dimensions")
        if not 2 <= self.blocks <= 8:
            raise ValueError("blocks must be in [2,8] for EDGEAI8")
        if not 259 <= self.max_vocab <= 4096:
            raise ValueError("invalid tokenizer vocabulary ceiling")
        if not 1 <= self.context_window <= 4096:
            raise ValueError("invalid context window")
        if self.optimizer != "AdamW":
            raise ValueError("optimizer must be AdamW")
        if not math.isfinite(self.learning_rate) or self.learning_rate <= 0:
            raise ValueError("invalid learning rate")
        if not math.isfinite(self.weight_decay) or self.weight_decay < 0:
            raise ValueError("invalid weight decay")
        if self.response_only is not True:
            raise ValueError("response_only must be true")
        if not 1 <= self.threads <= 2:
            raise ValueError("threads must be in [1,2]")
        if self.steps <= 0 or self.response_tokens_per_step <= 0:
            raise ValueError("steps and response_tokens_per_step must be positive")
        if not self.seeds or any(type(seed) is not int for seed in self.seeds):
            raise ValueError("seeds must be nonempty integers")
        if len(set(self.seeds)) != len(self.seeds):
            raise ValueError("seeds must be unique")
        object.__setattr__(self, "out", Path(self.out))

    @property
    def token_budget(self) -> int:
        return self.steps * self.response_tokens_per_step

    @classmethod
    def for_profile(cls, profile: str, out: Path | None = None, **overrides):
        if profile == "quick":
            values = dict(steps=2, response_tokens_per_step=8, seeds=(11,),
                          dim=16, hidden=24, blocks=2, context_window=64,
                          max_vocab=1024, threads=1)
        elif profile == "release":
            values = dict(steps=2048, response_tokens_per_step=128,
                          seeds=(11, 22, 33), threads=1)
        else:
            raise ValueError("profile must be quick or release")
        values.update(overrides)
        if out is not None:
            values["out"] = Path(out)
        return cls(**values)


@dataclass
class CandidateReport:
    seed: int
    deterministic: dict[str, Any]
    timing: dict[str, float]
    artifacts: dict[str, str]
    checkpoint: str


def write_training_report(config: TrainConfig,
                          candidates: list[CandidateReport]) -> dict[str, Any]:
    """Write a report whose artifact keys resolve from the output directory."""
    if not candidates or len({candidate.seed for candidate in candidates}) != len(candidates):
        raise ValueError("training report needs unique candidate seeds")
    versions = candidates[0].deterministic["dependency_versions"]
    data_hashes = candidates[0].deterministic["data_hashes"]
    tokenizer_hash = candidates[0].deterministic["tokenizer_sha256"]
    artifact_hashes = {}
    for candidate in candidates:
        if (candidate.deterministic["dependency_versions"] != versions
                or candidate.deterministic["data_hashes"] != data_hashes
                or candidate.deterministic["tokenizer_sha256"] != tokenizer_hash):
            raise ValueError("candidate reports have incompatible data or dependencies")
        for name, expected_hash in candidate.artifacts.items():
            relative = Path(name)
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("artifact path must be relative to the output directory")
            artifact_path = config.out / relative
            if not artifact_path.is_file() or _sha(artifact_path.read_bytes()) != expected_hash:
                raise ValueError("training artifact is missing or hash-mismatched: " + name)
            artifact_hashes[relative.as_posix()] = expected_hash
    report = {"protocol": PROTOCOL,
              "seeds": [candidate.seed for candidate in candidates],
              "token_budget": config.token_budget,
              "tokens": {"input": sum(x.deterministic["input_tokens"] for x in candidates),
                         "response": sum(x.deterministic["response_tokens"] for x in candidates)},
              "timing": {"cpu_seconds": sum(x.timing["cpu_seconds"] for x in candidates),
                         "wall_seconds": sum(x.timing["wall_seconds"] for x in candidates)},
              "runs": [x.deterministic for x in candidates],
              "dependency_versions": versions,
              "hashes": {"data": data_hashes, "tokenizer": tokenizer_hash,
                         "artifacts": artifact_hashes},
              "platform": platform.platform()}
    _atomic_json(config.out / "training.json", report)
    return report


def load_training_data(root: Path = SOURCE_ROOT) -> dict[str, Any]:
    """Load and hash the sealed train/valid snapshot, excluding test rows."""
    root = Path(root)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("format") != DATA_FORMAT:
        raise ValueError("unknown dataset format")
    policies = {"split_policy": DATA_SPLIT_POLICY, "tokenizer_splits": ["train"],
                "training_splits": ["train"], "selection_splits": ["valid"],
                "sealed_splits": ["test"], "test_prompts": 40}
    if any(manifest.get(key) != value for key, value in policies.items()):
        raise ValueError("sealed dataset policy mismatch")
    generator_path = TOOLS / "portuguese_data_v017.py"
    if manifest.get("generator_sha256") != _sha(generator_path.read_bytes()):
        raise ValueError("sealed dataset generator hash mismatch")
    expected = {split + ".jsonl" for split in DATA_SPLITS} | {"sources.json", "NOTICE.md"}
    records = manifest.get("files", {})
    if set(records) != expected:
        raise ValueError("missing or unknown manifest file")

    # Verify metadata for every declared artifact, including the sealed test
    # entry, but read only train/valid JSONL and provenance support files.
    for name, record in records.items():
        if (not isinstance(record, dict) or type(record.get("bytes")) is not int
                or record["bytes"] < 0 or not isinstance(record.get("sha256"), str)
                or len(record["sha256"]) != 64):
            raise ValueError("invalid manifest file record: " + name)
    for name in ("sources.json", "NOTICE.md"):
        raw = (root / name).read_bytes()
        record = records[name]
        if _sha(raw) != record["sha256"] or len(raw) != record["bytes"]:
            raise ValueError("dataset hash or size mismatch: " + name)
        if name == "sources.json":
            snapshot = json.loads(raw)
            validate_sources(snapshot)
            if snapshot != _sources():
                raise ValueError("source registry differs from the sealed generator")

    data = {}
    raw_splits = {}
    for split in ("train", "valid"):
        name = split + ".jsonl"
        raw = (root / name).read_bytes()
        record = records[name]
        if _sha(raw) != record["sha256"] or len(raw) != record["bytes"]:
            raise ValueError("dataset hash or size mismatch: " + name)
        data[split] = [json.loads(line) for line in raw.splitlines()]
        raw_splits[split] = raw
        if len(data[split]) != record.get("rows"):
            raise ValueError("dataset row count mismatch: " + split)
    generated = _generate_dataset()
    if any(data[split] != generated[split] for split in ("train", "valid")):
        raise ValueError("sealed split assignment or content differs from the generator")
    return {"train": data["train"], "valid": data["valid"],
            "hashes": {"manifest": _sha((root / "manifest.json").read_bytes()),
                       "train": _sha(raw_splits["train"]), "valid": _sha(raw_splits["valid"]),
                       "generator": manifest["generator_sha256"]}}


def train_tokenizer(train_rows: list[dict], vocab_ceiling: int = 1024) -> ByteBPE:
    """Train merges from train prompt/response bytes only."""
    if not train_rows or any(row.get("split") not in (None, "train") for row in train_rows):
        raise ValueError("tokenizer input must contain train rows only")
    # Rows are plain sealed records without a split label. Accept only IDs
    # present in the Task 1 train partition; this rejects both validation and
    # test rows without feeding held-out text into tokenizer training.
    train_ids = {row["id"] for row in load_training_data(SOURCE_ROOT)["train"]}
    if any(row.get("id") not in train_ids for row in train_rows):
        raise ValueError("tokenizer input must contain train rows only")
    if not 259 <= vocab_ceiling <= 4096:
        raise ValueError("invalid tokenizer vocabulary ceiling")
    docs = [row[field].encode("utf-8") for row in train_rows
            for field in ("prompt", "response")]
    base = ByteBPE.train(docs, vocab_size=vocab_ceiling - 2)
    tok = ByteBPE(base.merges, instruction=True)
    if tok.vocab_size > vocab_ceiling:
        raise ValueError("instruction tokenizer exceeds vocabulary ceiling")
    return tok


def encode_row(row: dict, tokenizer: ByteBPE, max_length: int) -> tuple[list[int], list[int]]:
    if not tokenizer.instruction:
        raise ValueError("response-only training needs an instruction tokenizer")
    if max_length < 1:
        raise ValueError("max_length must be positive")
    prompt = tokenizer.encode_prompt(row["prompt"])
    response = tokenizer.encode(row["response"]) + [tokenizer.eos_id]
    full = prompt + response
    if len(full) - 1 > max_length:
        raise ValueError("example exceeds max_length; no silent truncation")
    x = full[:-1]
    y = [IGNORE_INDEX] * (len(prompt) - 1) + response
    return x, y


def batch_order(row_count: int, seed: int, count: int) -> list[int]:
    if row_count <= 0 or count < 0:
        raise ValueError("invalid batch order dimensions")
    order: list[int] = []
    rng = random.Random(seed)
    while len(order) < count:
        epoch = list(range(row_count))
        rng.shuffle(epoch)
        order.extend(epoch)
    return order[:count]


def training_schedule(rows: list[dict], config: TrainConfig, seed: int) -> list[list[dict]]:
    """Build a replayable schedule with the same response-token budget per step."""
    if not rows:
        raise ValueError("training rows are empty")
    encoded = []
    for row in rows:
        if "x" in row and "y" in row:
            x, y = list(row["x"]), list(row["y"])
        else:
            # The real tokenizer is attached by train_candidate before scheduling.
            raise ValueError("training_schedule rows must be encoded x/y examples")
        if not x or len(x) != len(y) or not any(v != IGNORE_INDEX for v in y):
            raise ValueError("invalid encoded training row")
        encoded.append((x, y, row.get("id", "")))
    order = batch_order(len(encoded), seed, config.steps * (len(encoded) + 1))
    cursor = 0
    schedule = []
    for _ in range(config.steps):
        remaining = config.response_tokens_per_step
        batch = []
        while remaining:
            x, y, row_id = encoded[order[cursor % len(order)]]
            cursor += 1
            targets = sum(value != IGNORE_INDEX for value in y)
            take = min(remaining, targets)
            # Keep the prompt/context and only as many response targets as this
            # fixed-budget step still needs.
            selected_y = []
            used = 0
            for value in y:
                if value != IGNORE_INDEX:
                    if used == take:
                        break
                    used += 1
                selected_y.append(value)
            batch.append({"x": x[:len(selected_y)], "y": selected_y,
                          "id": row_id})
            remaining -= take
        schedule.append(batch)
    return schedule


def select_checkpoint(curve: list[dict]) -> dict:
    if not curve:
        raise ValueError("validation curve is empty")
    if any(point.get("split") != "valid" for point in curve):
        raise ValueError("checkpoint selection requires valid metrics only")
    if any(not math.isfinite(float(point.get("response_nll", float("nan"))))
           for point in curve):
        raise ValueError("validation NLL must be finite")
    return min(curve, key=lambda point: (float(point["response_nll"]),
                                        int(point["step"])))


def resume_identity(config: TrainConfig, seed: int, data_hashes: dict,
                    tokenizer_sha256: str) -> dict:
    semantic_config = asdict(config)
    semantic_config.pop("out")
    return {"protocol": PROTOCOL, "config": semantic_config,
            "seed": seed, "data": dict(data_hashes),
            "tokenizer_sha256": tokenizer_sha256}


def validate_resume(saved: dict, expected: dict) -> None:
    if not isinstance(saved, dict) or saved != expected:
        raise ValueError("resume identity does not match seed, tokenizer, data, budget or optimizer")


def validate_resume_progress(payload: dict, identity: dict, versions: dict) -> None:
    try:
        config = identity["config"]
        if (payload["identity"] != identity or payload["versions"] != versions
                or payload["protocol"] != identity["protocol"]
                or payload["config"] != config or payload["seed"] != identity["seed"]):
            raise ValueError
        step = payload["step"]
        response_tokens = payload["response_tokens"]
        input_tokens = payload["input_tokens"]
        max_steps = config["steps"]
        tokens_per_step = config["response_tokens_per_step"]
        if (type(step) is not int or not 1 <= step <= max_steps
                or type(response_tokens) is not int
                or response_tokens != step * tokens_per_step):
            raise ValueError
        if type(input_tokens) is not int or input_tokens < response_tokens:
            raise ValueError
        curve = payload["loss_curve"]
        if not isinstance(curve, list) or len(curve) != step:
            raise ValueError
        previous_input_tokens = 0
        for expected_step, point in enumerate(curve, 1):
            point_input_tokens = point["input_tokens"]
            if (point["step"] != expected_step
                    or point["response_tokens"] != expected_step * tokens_per_step
                    or type(point_input_tokens) is not int
                    or point_input_tokens < point["response_tokens"]
                    or point_input_tokens < previous_input_tokens
                    or not math.isfinite(float(point["train_loss"]))):
                raise ValueError
            previous_input_tokens = point_input_tokens
        if (curve[-1]["step"] != step
                or curve[-1]["response_tokens"] != response_tokens
                or curve[-1]["input_tokens"] != input_tokens):
            raise ValueError
        valid_curve = payload["validation_curve"]
        if not isinstance(valid_curve, list) or len(valid_curve) != step:
            raise ValueError
        if any(point.get("step") != index
               for index, point in enumerate(valid_curve, 1)):
            raise ValueError
        batch_digest = bytes.fromhex(payload["batch_ids_sha256"])
        if len(batch_digest) != 32:
            raise ValueError
        selected = select_checkpoint(valid_curve)
        if (payload["selected_step"] != selected["step"]
                or payload["selected_validation_nll"] != selected["response_nll"]):
            raise ValueError
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise ValueError("resume progress is corrupt or incompatible") from exc


def _torch_runtime():
    try:
        import torch
        from torch.nn import functional as F
        from sft_model import response_loss
        from transformer_model import TinyTransformer
        return torch, F, response_loss, TinyTransformer
    except Exception as exc:
        detail = str(exc).replace("\x00", "")
        raise RuntimeError(f"PyTorch runtime unavailable: {type(exc).__name__}: {detail}") from exc


def train_candidate(config: TrainConfig, seed: int) -> CandidateReport:
    """Train one deterministic candidate and save a real CPU checkpoint."""
    if seed not in config.seeds:
        raise ValueError("seed is not declared in TrainConfig")
    torch, F, response_loss, TinyTransformer = _torch_runtime()
    started_wall, started_cpu = time.perf_counter(), time.process_time()
    data = load_training_data(SOURCE_ROOT)
    tokenizer = train_tokenizer(data["train"], config.max_vocab)
    encoded = []
    for row in data["train"]:
        x, y = encode_row(row, tokenizer, config.context_window)
        encoded.append({"id": row["id"], "x": x, "y": y})
    schedule = training_schedule(encoded, config, seed)

    torch.set_num_threads(config.threads)
    torch.use_deterministic_algorithms(True)
    torch.manual_seed(seed)
    model = TinyTransformer(dim=config.dim, hidden=config.hidden,
                            window=config.context_window, precision="int8",
                            vocab_size=tokenizer.vocab_size, blocks=config.blocks)
    model.cpu()
    optimizer = torch.optim.AdamW(model.parameters(), lr=config.learning_rate,
                                  weight_decay=config.weight_decay)
    valid_encoded = [encode_row(row, tokenizer, config.context_window)
                     for row in data["valid"]]
    validation_curve = []
    loss_curve = []
    response_seen = input_seen = 0
    batch_digest = hashlib.sha256()
    best_state = None
    for step, parts in enumerate(schedule, 1):
        width = max(len(part["x"]) for part in parts)
        xs = torch.full((len(parts), width), tokenizer.eos_id, dtype=torch.long)
        ys = torch.full_like(xs, IGNORE_INDEX)
        for index, part in enumerate(parts):
            xs[index, :len(part["x"])] = torch.tensor(part["x"], dtype=torch.long)
            ys[index, :len(part["y"])] = torch.tensor(part["y"], dtype=torch.long)
            batch_digest.update(part["id"].encode("ascii"))
        target_count = int((ys != IGNORE_INDEX).sum())
        input_count = sum(len(part["x"]) for part in parts)
        if target_count != config.response_tokens_per_step:
            raise RuntimeError("scheduled response token budget changed")
        model.train()
        optimizer.zero_grad(set_to_none=True)
        loss = response_loss(model(xs), ys)
        if not torch.isfinite(loss).item():
            raise RuntimeError("nonfinite training loss")
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
        response_seen += target_count
        input_seen += input_count
        loss_curve.append({"step": step, "train_loss": float(loss.detach()),
                           "response_tokens": response_seen,
                           "input_tokens": input_seen})

        model.eval()
        total_loss = 0.0
        total_targets = 0
        with torch.inference_mode():
            for x, y in valid_encoded:
                tx = torch.tensor([x], dtype=torch.long)
                ty = torch.tensor([y], dtype=torch.long)
                logits = model(tx)
                count = int((ty != IGNORE_INDEX).sum())
                metric = F.cross_entropy(logits.flatten(0, 1), ty.flatten(),
                                         ignore_index=IGNORE_INDEX, reduction="sum")
                total_loss += float(metric)
                total_targets += count
        nll = total_loss / total_targets
        if not math.isfinite(nll):
            raise RuntimeError("nonfinite validation response NLL")
        validation_curve.append({"step": step, "split": "valid",
                                 "response_nll": nll})
        if select_checkpoint(validation_curve) is validation_curve[-1]:
            best_state = {key: value.detach().clone()
                          for key, value in model.state_dict().items()}

    selected = select_checkpoint(validation_curve)
    if best_state is None:
        raise RuntimeError("no validation-selected checkpoint")
    model.load_state_dict(best_state)
    config.out.mkdir(parents=True, exist_ok=True)
    checkpoint_path = config.out / f"checkpoint-seed-{seed}.pt"
    temp_checkpoint = checkpoint_path.with_name(checkpoint_path.name + ".tmp")
    checkpoint = {"protocol": PROTOCOL, "identity": resume_identity(
        config, seed, data["hashes"], tokenizer.fingerprint()),
        "versions": {"torch": str(torch.__version__), "python": platform.python_version()},
        "config": {key: value for key, value in asdict(config).items()
                   if key != "out"},
        "seed": seed, "step": config.steps, "response_tokens": response_seen,
        "input_tokens": input_seen, "tokenizer": tokenizer.payload(),
        "model_config": model.export_config(), "state_dict": best_state,
        "loss_curve": loss_curve, "validation_curve": validation_curve,
        "batch_ids_sha256": batch_digest.hexdigest(),
        "selected_validation_nll": selected["response_nll"],
        "selected_step": selected["step"]}
    torch.save(checkpoint, temp_checkpoint)
    os.replace(temp_checkpoint, checkpoint_path)
    artifact_hash = _sha(checkpoint_path.read_bytes())
    timing = {"cpu_seconds": time.process_time() - started_cpu,
              "wall_seconds": time.perf_counter() - started_wall}
    deterministic = {"protocol": PROTOCOL, "seed": seed,
                     "data_hashes": data["hashes"],
                     "tokenizer_sha256": tokenizer.fingerprint(),
                     "tokenizer_vocab_size": tokenizer.vocab_size,
                     "input_tokens": input_seen, "response_tokens": response_seen,
                     "loss_curve": loss_curve,
                     "validation_curve": validation_curve,
                     "selected_step": selected["step"],
                     "selected_validation_nll": selected["response_nll"],
                     "batch_ids_sha256": batch_digest.hexdigest(),
                     "dependency_versions": {"torch": str(torch.__version__),
                                              "python": platform.python_version()}}
    artifacts = {checkpoint_path.name: artifact_hash}
    candidate = CandidateReport(seed, deterministic, timing, artifacts, checkpoint_path.name)
    write_training_report(config, [candidate])
    return candidate


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("quick", "release"), default="quick")
    parser.add_argument("--threads", type=int, default=None)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    overrides = {} if args.threads is None else {"threads": args.threads}
    config = TrainConfig.for_profile(args.profile, out=args.out, **overrides)
    results = [train_candidate(config, seed) for seed in config.seeds]
    write_training_report(config, results)
    print(json.dumps({"completed": len(results), "seeds": list(config.seeds),
                      "out": str(config.out)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
