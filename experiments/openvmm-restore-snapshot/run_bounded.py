#!/usr/bin/env python3
"""Run a source-bound FM-style analysis of OpenVMM snapshot restore."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.cli_backend import resolve_model_backend
from src.extract import _function_spans
from src.llm_client import _llm_json_call, _llm_provider_client
from src.parser import _remove_func_comments, format_info_for_reasoner, format_spec_for_reasoner
from src.reasoner import reasoner
from config import settings


TARGET_REL = Path("openvmm/openvmm_core/src/worker/dispatch.rs")
TARGET_NAME = "restore_snapshot_state"


def _target_source(source_path: Path) -> tuple[str, int, int]:
    spans, raw_lines, _ = _function_spans(str(source_path), "rust")
    matches = [(start, end) for name, start, end in spans if name == TARGET_NAME]
    if len(matches) != 1:
        raise RuntimeError(f"expected one {TARGET_NAME} span, found {len(matches)}")
    start, end = matches[0]
    return "".join(raw_lines[start : end + 1]), start + 1, end + 1


def _caller_context(source_text: str) -> str:
    lines = source_text.splitlines()
    matches = [
        index
        for index, line in enumerate(lines)
        if ".restore_snapshot_state(saved_state, restore_time)" in line
    ]
    if len(matches) != 1:
        raise RuntimeError(f"expected one restore call site, found {len(matches)}")
    index = matches[0]
    start = max(0, index - 18)
    end = min(len(lines), index + 12)
    return "\n".join(
        f"Line {line_number + 1}: {lines[line_number]}"
        for line_number in range(start, end)
    )


def _numbered_function(source: str) -> str:
    cleaned = _remove_func_comments(source, "Rust")
    return "\n".join(
        f"Line {index}: {line}"
        for index, line in enumerate(cleaned.splitlines(), start=1)
    )


def _candidate_prompt(intent: str, caller: str, function: str) -> list[dict[str, str]]:
    system = """You are the specification-generation stage of FM-Agent.
Use top-down, caller-driven Hoare-style reasoning. Infer intended behavior from
the supplied system intent and caller, not by merely restating implementation.
The implementation may be buggy. Produce precise, falsifiable contracts and
explicit callee expectations. Distinguish snapshot-owned state from destination
runtime state. Return only one valid JSON object."""
    user = f"""Analyze OpenVMM LoadedVm::restore_snapshot_state.

SYSTEM INTENT:
{intent}

CALLER CONTEXT:
```rust
{caller}
```

TARGET FUNCTION:
```rust
{function}
```

Return exactly this JSON shape:
{{
  "recommended_candidate_id": "candidate-a",
  "candidates": [
    {{
      "id": "candidate-a",
      "name": "short name",
      "pre_condition": "caller obligations",
      "post_condition": "caller-visible guarantees",
      "semantic_difference": "how this differs from the other candidates",
      "discriminator": "a concrete scenario that distinguishes it"
    }}
  ],
  "callees": [
    {{
      "name": "callee name",
      "signature": "informal signature",
      "pre_condition": "what this caller establishes",
      "post_condition": "what this caller needs"
    }}
  ],
  "implementation_hypotheses": [
    {{
      "claim": "possible support or mismatch",
      "code_evidence": "specific statement or ordering",
      "disposition": "supported|challenged|unknown"
    }}
  ],
  "proof_obligations": ["obligation"],
  "uncertainties": ["uncertainty"]
}}

Requirements:
- Produce exactly three materially different candidates: projection equality,
  an intentionally stronger full-state interpretation, and a weaker
  orchestration-only interpretation.
- Do not approve a candidate merely because the body appears to implement it.
- Include time adjustment, stable VP identity, active versus pending component
  state, preserved destination resources, and the stopped pre-execution boundary.
- Identify which facts require callee contracts or proof rather than inspection
  of this function body."""
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _validate_generated(data: object) -> dict:
    if not isinstance(data, dict):
        raise ValueError("candidate analysis must be a JSON object")
    candidates = data.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != 3:
        raise ValueError("candidate analysis must contain exactly three candidates")
    required_candidate_fields = {
        "id",
        "name",
        "pre_condition",
        "post_condition",
        "semantic_difference",
        "discriminator",
    }
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise ValueError("each candidate must be a JSON object")
        missing = required_candidate_fields - set(candidate)
        if missing:
            raise ValueError(
                "candidate is missing fields: " + ", ".join(sorted(missing))
            )
        for field in required_candidate_fields:
            if not isinstance(candidate[field], str) or not candidate[field].strip():
                raise ValueError(f"candidate field {field} must be a non-empty string")
    callees = data.get("callees")
    if not isinstance(callees, list):
        raise ValueError("candidate analysis must contain a callees list")
    return data


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--intent", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    repo = args.repo.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    source_path = repo / TARGET_REL
    source_text = source_path.read_text(encoding="utf-8")
    function_source, start_line, end_line = _target_source(source_path)
    caller_context = _caller_context(source_text)
    intent = args.intent.read_text(encoding="utf-8")

    messages = _candidate_prompt(intent, caller_context, function_source)
    trace_dir = output / "trace"
    generated = _llm_json_call(
        _llm_provider_client,
        settings.llm.name,
        messages,
        _validate_generated,
        "one JSON object with exactly three complete candidates and a callees list",
        trace_dir=str(trace_dir),
        trace_meta={
            "stage": "candidate_generation",
            "function_id": "LoadedVm::restore_snapshot_state",
        },
    )
    candidates = generated.get("candidates")
    callees = generated.get("callees")

    extracted_path = output / "restore_snapshot_state.rs"
    extracted_path.write_text(function_source, encoding="utf-8")
    info = format_info_for_reasoner({"callees": callees})
    numbered = _numbered_function(function_source)
    results = []
    for candidate in candidates:
        spec = format_spec_for_reasoner(
            {
                "signature": (
                    "LoadedVm::restore_snapshot_state(&mut self, saved_state, "
                    "restore_time) -> anyhow::Result<()>"
                ),
                "pre_condition": candidate.get("pre_condition", ""),
                "post_condition": candidate.get("post_condition", ""),
            }
        )
        result = reasoner(
            numbered,
            spec,
            info,
            "Rust",
            trace_context={
                "trace_dir": str(trace_dir),
                "function_id": "LoadedVm::restore_snapshot_state",
                "function_file": str(TARGET_REL),
                "candidate_id": candidate.get("id"),
            },
            all_bugs=True,
        )
        results.append({"candidate": candidate, "reasoner": result})

    revision = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    evidence = {
        "experiment": "openvmm-restore-snapshot-bounded",
        "source": {
            "repository": str(repo),
            "revision": revision,
            "file": str(TARGET_REL),
            "lines": [start_line, end_line],
            "sha256": hashlib.sha256(function_source.encode("utf-8")).hexdigest(),
        },
        "backend": {
            "agent": resolve_model_backend(),
            "model": settings.llm.name,
        },
        "intent_file": str(args.intent.resolve()),
        "generated_analysis": generated,
        "candidate_reasoning": results,
    }
    (output / "evidence.json").write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(output / "evidence.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
