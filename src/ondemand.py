"""On-demand top-down function analysis with explicit callee expansion."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import settings
from src.cli_backend import resolve_model_backend
from src.extract import EXT_TO_LANG, _function_spans
from src.llm_client import _llm_json_call, _llm_provider_client


SCHEMA_VERSION = "ondemand-v1"
DISPOSITIONS = {"supported", "challenged", "unknown"}
OBLIGATION_STATUSES = {"open", "conditional", "discharged", "refuted"}
REINTEGRATION_DISPOSITIONS = {"open", "conditional", "discharged", "refuted"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")
    return value or "function"


def _read_text(path: Path | None) -> str:
    if path is None:
        return ""
    return path.read_text(encoding="utf-8")


def _git_revision(repo: Path) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _language_for(path: Path) -> str:
    extension = path.suffix.lstrip(".").lower()
    language = EXT_TO_LANG.get(extension)
    if not language:
        raise ValueError(f"unsupported source extension: {path.suffix}")
    return language


def _strip_verification_annotations(source: str) -> str:
    markers = ("verus_spec", "verus_verify", "verus_builtin_macros")
    lines = source.splitlines(keepends=True)
    output: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.lstrip().startswith("#["):
            attribute = [line]
            balance = line.count("[") - line.count("]")
            while balance > 0 and index + 1 < len(lines):
                index += 1
                attribute.append(lines[index])
                balance += lines[index].count("[") - lines[index].count("]")
            text = "".join(attribute)
            if not any(marker in text for marker in markers):
                output.extend(attribute)
        else:
            output.append(line)
        index += 1
    return "".join(output)


def _extract_function(
    repo: Path,
    file_rel: str,
    symbol: str,
    line: int | None = None,
    strip_verification_annotations: bool = False,
) -> dict[str, Any]:
    source_path = (repo / file_rel).resolve()
    try:
        source_path.relative_to(repo)
    except ValueError as exc:
        raise ValueError(f"source file escapes repository: {file_rel}") from exc
    if not source_path.is_file():
        raise ValueError(f"source file does not exist: {file_rel}")

    language = _language_for(source_path)
    spans, raw_lines, _ = _function_spans(str(source_path), language)
    requested = symbol.split("::")[-1]
    matches = []
    for extracted_name, start, end in spans:
        leaf = extracted_name.split("::")[-1]
        if extracted_name == symbol or leaf == requested:
            if line is None or start + 1 <= line <= end + 1:
                matches.append((extracted_name, start, end))
    if len(matches) != 1:
        available = sorted(
            extracted_name
            for extracted_name, _, _ in spans
            if requested.lower() in extracted_name.lower()
        )[:20]
        raise ValueError(
            f"expected one match for {symbol!r} in {file_rel}, found {len(matches)}; "
            f"nearby symbols: {available}"
        )
    extracted_name, start, end = matches[0]
    original_source = "".join(raw_lines[start : end + 1])
    source = (
        _strip_verification_annotations(original_source)
        if strip_verification_annotations
        else original_source
    )
    return {
        "requested_symbol": symbol,
        "extracted_symbol": extracted_name,
        "file": file_rel.replace(os.sep, "/"),
        "language": language,
        "start_line": start + 1,
        "end_line": end + 1,
        "sha256": hashlib.sha256(original_source.encode("utf-8")).hexdigest(),
        "analysis_transform": (
            "strip-verification-annotations" if strip_verification_annotations else "none"
        ),
        "source": source,
    }


def _validate_contract(contract: object) -> dict[str, str]:
    if not isinstance(contract, dict):
        raise ValueError("contract must be an object")
    fields = ("pre_condition", "post_condition", "failure_condition")
    for field in fields:
        value = contract.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"contract.{field} must be a non-empty string")
    return contract


def _validate_abstraction(abstraction: object) -> dict[str, Any]:
    if not isinstance(abstraction, dict):
        raise ValueError("abstraction must be an object")
    fields = (
        "name",
        "abstract_state",
        "projection",
        "preserved_state",
        "hidden_representation",
        "observation_boundary",
    )
    for field in fields:
        value = abstraction.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"abstraction.{field} must be a non-empty string")
    return abstraction


def _validate_analysis(data: object) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("analysis must be an object")
    _validate_contract(data.get("contract"))
    _validate_abstraction(data.get("abstraction"))

    assessments = data.get("implementation_assessment")
    if not isinstance(assessments, list):
        raise ValueError("implementation_assessment must be a list")
    for assessment in assessments:
        if not isinstance(assessment, dict):
            raise ValueError("each implementation assessment must be an object")
        if assessment.get("disposition") not in DISPOSITIONS:
            raise ValueError("assessment disposition must be supported, challenged, or unknown")
        for field in ("claim", "evidence"):
            if not isinstance(assessment.get(field), str) or not assessment[field].strip():
                raise ValueError(f"assessment.{field} must be a non-empty string")

    obligations = data.get("obligations")
    if not isinstance(obligations, list):
        raise ValueError("obligations must be a list")
    seen = set()
    for obligation in obligations:
        if not isinstance(obligation, dict):
            raise ValueError("each obligation must be an object")
        obligation_id = obligation.get("id")
        if not isinstance(obligation_id, str) or not obligation_id.strip():
            raise ValueError("obligation.id must be a non-empty string")
        if obligation_id in seen:
            raise ValueError(f"duplicate obligation id: {obligation_id}")
        seen.add(obligation_id)
        for field in ("title", "claim", "why_blocking", "kind"):
            if not isinstance(obligation.get(field), str) or not obligation[field].strip():
                raise ValueError(f"obligation.{field} must be a non-empty string")
        callees = obligation.get("suggested_callees")
        if not isinstance(callees, list):
            raise ValueError("obligation.suggested_callees must be a list")
        for callee in callees:
            if not isinstance(callee, dict):
                raise ValueError("each suggested callee must be an object")
            for field in ("symbol", "reason"):
                if not isinstance(callee.get(field), str) or not callee[field].strip():
                    raise ValueError(f"suggested_callee.{field} must be a non-empty string")
            if not isinstance(callee.get("file_hint", ""), str):
                raise ValueError("suggested_callee.file_hint must be a string")
        obligation.setdefault("status", "open")

    variants = data.get("candidate_variants")
    if not isinstance(variants, list) or len(variants) < 2:
        raise ValueError("candidate_variants must contain at least two alternatives")
    for variant in variants:
        if not isinstance(variant, dict):
            raise ValueError("each candidate variant must be an object")
        for field in ("name", "semantic_difference", "discriminator"):
            if not isinstance(variant.get(field), str) or not variant[field].strip():
                raise ValueError(f"candidate_variant.{field} must be a non-empty string")

    uncertainties = data.get("uncertainties")
    if not isinstance(uncertainties, list) or not all(
        isinstance(item, str) and item.strip() for item in uncertainties
    ):
        raise ValueError("uncertainties must be a list of non-empty strings")
    next_step = data.get("recommended_next_step")
    if not isinstance(next_step, str) or not next_step.strip():
        raise ValueError("recommended_next_step must be a non-empty string")
    return data


def _validate_refinement(data: object) -> dict[str, Any]:
    analysis = _validate_analysis(data)
    changes = analysis.get("refinement_changes")
    if not isinstance(changes, list) or not all(
        isinstance(item, str) and item.strip() for item in changes
    ):
        raise ValueError("refinement_changes must be a list of non-empty strings")
    return analysis


def _validate_reintegration(data: object) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("reintegration must be an object")
    if data.get("disposition") not in REINTEGRATION_DISPOSITIONS:
        raise ValueError("invalid reintegration disposition")
    for field in ("rationale", "caller_effect", "remaining_gap"):
        if not isinstance(data.get(field), str) or not data[field].strip():
            raise ValueError(f"reintegration.{field} must be a non-empty string")
    updates = data.get("proof_map_updates")
    if not isinstance(updates, list) or not all(
        isinstance(item, str) and item.strip() for item in updates
    ):
        raise ValueError("proof_map_updates must be a list of non-empty strings")
    revision = data.get("parent_contract_revision")
    if revision is not None:
        _validate_contract(revision)
    return data


def _schema_description(refinement: bool = False) -> str:
    suffix = (
        ", plus refinement_changes as a list of strings"
        if refinement
        else ""
    )
    return (
        "an object with contract {pre_condition, post_condition, failure_condition}, "
        "abstraction {name, abstract_state, projection, preserved_state, "
        "hidden_representation, observation_boundary}, implementation_assessment "
        "[{claim,evidence,disposition}], obligations "
        "[{id,title,claim,why_blocking,kind,suggested_callees:[{symbol,file_hint,reason}]}], "
        "candidate_variants [{name,semantic_difference,discriminator}], uncertainties "
        f"[string], and recommended_next_step{suffix}"
    )


def _analysis_messages(
    *,
    source: dict[str, Any],
    intent: str,
    caller_context: str,
    parent_obligation: dict[str, Any] | None,
) -> list[dict[str, str]]:
    parent_text = (
        json.dumps(parent_obligation, indent=2, ensure_ascii=False)
        if parent_obligation
        else "(top-level function; no parent obligation)"
    )
    return [
        {
            "role": "system",
            "content": (
                "You are FM-Agent's on-demand top-down specification and proof analyst. "
                "Analyze only the supplied function and context. Do not assume unshown "
                "callee behavior. Generate a caller-facing contract, an explicit abstraction, "
                "and bounded proof obligations. Suggested callees are recommendations only; "
                "do not analyze them. The implementation may be buggy and the supplied intent "
                "may need refinement. Return only valid JSON."
            ),
        },
        {
            "role": "user",
            "content": f"""FUNCTION:
{source['extracted_symbol']} at {source['file']}:{source['start_line']}-{source['end_line']}

INTENT:
{intent}

CALLER CONTEXT:
{caller_context or "(not supplied)"}

PARENT BLOCKING OBLIGATION:
{parent_text}

SOURCE:
```{source['language']}
{source['source']}
```

Return {_schema_description()}.

Requirements:
- Separate what this body establishes from what requires callee contracts.
- Produce at least one stronger and one weaker candidate variant with a concrete discriminator.
- The abstraction must identify observable state, its projection, preserved state, hidden representation, and the exact observation boundary.
- Obligations must be independently selectable for later `expand`; use stable short ids such as O1, O2.
- Include bug hypotheses as challenged assessments, but do not report an unproved hypothesis as a bug.
- Prefer obligations that can be discharged by a callee contract, executable attack, or proof lemma."""
        },
    ]


def _refinement_messages(
    source: dict[str, Any],
    current: dict[str, Any],
    feedback: str,
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You refine a function specification using explicit feedback or new evidence. "
                "Preserve the original intent, state semantic changes, and improve the abstraction "
                "rather than copying implementation details. Return only valid JSON."
            ),
        },
        {
            "role": "user",
            "content": f"""FUNCTION SOURCE:
```{source['language']}
{source['source']}
```

CURRENT ANALYSIS:
{json.dumps(current, indent=2, ensure_ascii=False)}

REFINEMENT FEEDBACK:
{feedback}

Return {_schema_description(refinement=True)}.
Keep obligation ids stable when their meaning is unchanged. Add `refinement_changes`
describing every semantic change to the contract or abstraction."""
        },
    ]


def _reintegration_messages(
    parent: dict[str, Any],
    child: dict[str, Any],
    obligation: dict[str, Any],
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You perform caller reintegration in a top-down proof map. Decide whether the "
                "selected child analysis discharges the exact parent obligation. Do not treat a "
                "plausible child contract as proved. Return only valid JSON."
            ),
        },
        {
            "role": "user",
            "content": f"""PARENT FUNCTION:
{parent['source']['extracted_symbol']}

PARENT ANALYSIS:
{json.dumps(parent['analysis'], indent=2, ensure_ascii=False)}

SELECTED PARENT OBLIGATION:
{json.dumps(obligation, indent=2, ensure_ascii=False)}

CHILD FUNCTION:
{child['source']['extracted_symbol']}

CHILD ANALYSIS:
{json.dumps(child['analysis'], indent=2, ensure_ascii=False)}

Return an object with:
- disposition: open|conditional|discharged|refuted
- rationale: why the child evidence has this effect
- caller_effect: the exact parent claim now supported or challenged
- remaining_gap: what remains before the parent proof can close
- proof_map_updates: list of edges/status changes
- parent_contract_revision: null or a complete revised parent contract."""
        },
    ]


def _call_json(
    messages: list[dict[str, str]],
    validator,
    schema_description: str,
    trace_dir: Path,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    result = _llm_json_call(
        _llm_provider_client,
        settings.llm.name,
        messages,
        validator,
        schema_description,
        trace_dir=str(trace_dir),
        trace_meta=metadata,
    )
    if result is None:
        raise RuntimeError("model did not produce valid structured output")
    return result


def _new_session(repo: Path) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "created_at": _now(),
        "updated_at": _now(),
        "repository": str(repo),
        "repository_revision": _git_revision(repo),
        "backend": {
            "agent": resolve_model_backend(),
            "model": settings.llm.name,
        },
        "root_node_id": None,
        "nodes": {},
        "edges": [],
    }


def _load_session(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"unsupported session schema: {data.get('schema_version')}")
    if not isinstance(data.get("nodes"), dict) or not isinstance(data.get("edges"), list):
        raise ValueError("invalid on-demand session")
    return data


def _write_session(path: Path, session: dict[str, Any]) -> None:
    session["updated_at"] = _now()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(session, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _artifact_root(session_path: Path) -> Path:
    return session_path.with_suffix(session_path.suffix + ".artifacts")


def _next_node_id(session: dict[str, Any], symbol: str) -> str:
    base = _slug(symbol)
    index = 1
    node_id = base
    while node_id in session["nodes"]:
        index += 1
        node_id = f"{base}-{index}"
    return node_id


def _find_obligation(node: dict[str, Any], obligation_id: str) -> dict[str, Any]:
    for obligation in node["analysis"]["obligations"]:
        if obligation.get("id") == obligation_id:
            return obligation
    raise ValueError(f"obligation {obligation_id!r} not found in node {node['id']}")


def _analyze_node(
    *,
    session: dict[str, Any],
    session_path: Path,
    repo: Path,
    file_rel: str,
    symbol: str,
    line: int | None,
    intent: str,
    caller_context: str,
    parent_node_id: str | None,
    parent_obligation_id: str | None,
    strip_verification_annotations: bool,
) -> dict[str, Any]:
    source = _extract_function(
        repo,
        file_rel,
        symbol,
        line,
        strip_verification_annotations=strip_verification_annotations,
    )
    parent_obligation = None
    if parent_node_id:
        parent = session["nodes"].get(parent_node_id)
        if parent is None:
            raise ValueError(f"parent node not found: {parent_node_id}")
        if not parent_obligation_id:
            raise ValueError("--obligation is required when expanding a parent")
        parent_obligation = _find_obligation(parent, parent_obligation_id)

    node_id = _next_node_id(session, source["extracted_symbol"])
    trace_dir = _artifact_root(session_path) / node_id / "trace"
    analysis = _call_json(
        _analysis_messages(
            source=source,
            intent=intent,
            caller_context=caller_context,
            parent_obligation=parent_obligation,
        ),
        _validate_analysis,
        _schema_description(),
        trace_dir,
        {
            "stage": "ondemand_analysis",
            "node_id": node_id,
            "function_id": source["extracted_symbol"],
        },
    )
    node = {
        "id": node_id,
        "created_at": _now(),
        "parent_node_id": parent_node_id,
        "parent_obligation_id": parent_obligation_id,
        "intent": intent,
        "caller_context": caller_context,
        "source": source,
        "analysis": analysis,
        "refinements": [],
    }
    session["nodes"][node_id] = node
    if session["root_node_id"] is None:
        session["root_node_id"] = node_id
    if parent_node_id:
        session["edges"].append(
            {
                "parent": parent_node_id,
                "child": node_id,
                "obligation": parent_obligation_id,
                "status": "open",
                "created_at": _now(),
            }
        )
    return node


def _cmd_analyze(args: argparse.Namespace) -> None:
    repo = args.repo.resolve()
    session_path = args.session.resolve()
    if session_path.exists():
        raise ValueError(f"session already exists: {session_path}")
    session = _new_session(repo)
    node = _analyze_node(
        session=session,
        session_path=session_path,
        repo=repo,
        file_rel=args.file,
        symbol=args.symbol,
        line=args.line,
        intent=_read_text(args.intent),
        caller_context=_read_text(args.caller_context),
        parent_node_id=None,
        parent_obligation_id=None,
        strip_verification_annotations=args.strip_verification_annotations,
    )
    _write_session(session_path, session)
    print(json.dumps({"session": str(session_path), "node": node["id"]}))


def _cmd_expand(args: argparse.Namespace) -> None:
    session_path = args.session.resolve()
    session = _load_session(session_path)
    repo = Path(session["repository"]).resolve()
    parent = session["nodes"].get(args.parent)
    if parent is None:
        raise ValueError(f"parent node not found: {args.parent}")
    obligation = _find_obligation(parent, args.obligation)
    intent = _read_text(args.intent) or (
        "Analyze this callee only to address the parent obligation:\n"
        + json.dumps(obligation, ensure_ascii=False)
    )
    node = _analyze_node(
        session=session,
        session_path=session_path,
        repo=repo,
        file_rel=args.file,
        symbol=args.symbol,
        line=args.line,
        intent=intent,
        caller_context=_read_text(args.caller_context),
        parent_node_id=args.parent,
        parent_obligation_id=args.obligation,
        strip_verification_annotations=args.strip_verification_annotations,
    )
    _write_session(session_path, session)
    print(json.dumps({"session": str(session_path), "node": node["id"]}))


def _cmd_refine(args: argparse.Namespace) -> None:
    session_path = args.session.resolve()
    session = _load_session(session_path)
    node = session["nodes"].get(args.node)
    if node is None:
        raise ValueError(f"node not found: {args.node}")
    feedback = _read_text(args.feedback)
    if not feedback.strip():
        raise ValueError("refinement feedback must not be empty")
    revision_number = len(node["refinements"]) + 1
    trace_dir = _artifact_root(session_path) / node["id"] / f"refine-{revision_number}" / "trace"
    refined = _call_json(
        _refinement_messages(node["source"], node["analysis"], feedback),
        _validate_refinement,
        _schema_description(refinement=True),
        trace_dir,
        {
            "stage": "ondemand_refinement",
            "node_id": node["id"],
            "revision": revision_number,
        },
    )
    node["refinements"].append(
        {
            "revision": revision_number,
            "created_at": _now(),
            "feedback": feedback,
            "previous_analysis": node["analysis"],
        }
    )
    node["analysis"] = refined
    _write_session(session_path, session)
    print(json.dumps({"session": str(session_path), "node": node["id"], "revision": revision_number}))


def _cmd_reintegrate(args: argparse.Namespace) -> None:
    session_path = args.session.resolve()
    session = _load_session(session_path)
    parent = session["nodes"].get(args.parent)
    child = session["nodes"].get(args.child)
    if parent is None or child is None:
        raise ValueError("parent or child node not found")
    if child.get("parent_node_id") != parent["id"]:
        raise ValueError("child is not linked to the selected parent")
    obligation_id = child.get("parent_obligation_id")
    obligation = _find_obligation(parent, obligation_id)
    trace_dir = _artifact_root(session_path) / child["id"] / "reintegrate" / "trace"
    result = _call_json(
        _reintegration_messages(parent, child, obligation),
        _validate_reintegration,
        (
            "an object with disposition, rationale, caller_effect, remaining_gap, "
            "proof_map_updates, and null or complete parent_contract_revision"
        ),
        trace_dir,
        {
            "stage": "ondemand_reintegration",
            "parent_node_id": parent["id"],
            "child_node_id": child["id"],
            "obligation_id": obligation_id,
        },
    )
    obligation["status"] = result["disposition"]
    obligation["reintegration"] = result
    if result.get("parent_contract_revision") is not None:
        parent["analysis"]["contract"] = result["parent_contract_revision"]
    for edge in session["edges"]:
        if edge["parent"] == parent["id"] and edge["child"] == child["id"]:
            edge["status"] = result["disposition"]
            edge["reintegration"] = result
    _write_session(session_path, session)
    print(json.dumps({"session": str(session_path), "disposition": result["disposition"]}))


def _cmd_show(args: argparse.Namespace) -> None:
    session = _load_session(args.session.resolve())
    if args.node:
        node = session["nodes"].get(args.node)
        if node is None:
            raise ValueError(f"node not found: {args.node}")
        print(json.dumps(node, indent=2, ensure_ascii=False))
        return
    summary = {
        "schema_version": session["schema_version"],
        "repository": session["repository"],
        "repository_revision": session["repository_revision"],
        "backend": session["backend"],
        "root_node_id": session["root_node_id"],
        "nodes": [
            {
                "id": node["id"],
                "symbol": node["source"]["extracted_symbol"],
                "file": node["source"]["file"],
                "parent": node["parent_node_id"],
                "parent_obligation": node["parent_obligation_id"],
                "open_obligations": [
                    obligation["id"]
                    for obligation in node["analysis"]["obligations"]
                    if obligation.get("status", "open") in {"open", "conditional"}
                ],
                "refinement_count": len(node["refinements"]),
            }
            for node in session["nodes"].values()
        ],
        "edges": session["edges"],
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))


def _source_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--file", required=True, help="repository-relative source file")
    parser.add_argument("--symbol", required=True, help="function or method name")
    parser.add_argument("--line", type=int, help="optional source line to disambiguate overloads")
    parser.add_argument("--intent", type=Path, help="Markdown intent or focused analysis question")
    parser.add_argument("--caller-context", type=Path, help="optional caller context file")
    parser.add_argument(
        "--strip-verification-annotations",
        action="store_true",
        help="remove inline Verus specification and verification attributes from model input",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="analyze-function",
        description="Analyze one function at a time and expand only selected proof obligations."
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    analyze = subcommands.add_parser("analyze", help="create a session from one explicit function")
    analyze.add_argument("--repo", type=Path, required=True)
    analyze.add_argument("--session", type=Path, required=True)
    _source_arguments(analyze)
    analyze.set_defaults(handler=_cmd_analyze)

    expand = subcommands.add_parser("expand", help="analyze one selected callee obligation")
    expand.add_argument("--session", type=Path, required=True)
    expand.add_argument("--parent", required=True)
    expand.add_argument("--obligation", required=True)
    _source_arguments(expand)
    expand.set_defaults(handler=_cmd_expand)

    refine = subcommands.add_parser("refine", help="refine one node's contract and abstraction")
    refine.add_argument("--session", type=Path, required=True)
    refine.add_argument("--node", required=True)
    refine.add_argument("--feedback", type=Path, required=True)
    refine.set_defaults(handler=_cmd_refine)

    reintegrate = subcommands.add_parser(
        "reintegrate", help="return one child result to its parent obligation"
    )
    reintegrate.add_argument("--session", type=Path, required=True)
    reintegrate.add_argument("--parent", required=True)
    reintegrate.add_argument("--child", required=True)
    reintegrate.set_defaults(handler=_cmd_reintegrate)

    show = subcommands.add_parser("show", help="show a session or one node")
    show.add_argument("--session", type=Path, required=True)
    show.add_argument("--node")
    show.set_defaults(handler=_cmd_show)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    args.handler(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
