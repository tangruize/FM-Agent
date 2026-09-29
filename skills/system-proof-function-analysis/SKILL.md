---
name: system-proof-function-analysis
description: "Use FM-Agent for bounded, source-bound function contract and obligation analysis inside a system-proof campaign. Use when one caller fact is blocked on a selected function or callee; escalate shared-state, lifecycle, concurrency, or cross-operation properties to protocol analysis."
---

# System-proof function analysis

Use `analyze-function` as an advisory specialist. It proposes contracts, abstractions, counterexamples and proof obligations; it does not select an adequate specification, establish an invariant, confirm a bug, discharge a proof-map edge or approve intent.

Read [../../docs/system-proof-function-analysis.md](../../docs/system-proof-function-analysis.md) before the first invocation in a campaign.

## Required inputs

- the unchanged top-level system-proof goal;
- one exact source file and function symbol;
- the direct caller fact currently needed;
- the observation boundary and relevant assumptions;
- one proof-map obligation to investigate;
- a fresh session path and, for retained experiments, an isolated source worktree or copy.

Do not replace the campaign goal with a locally easier helper claim. Do not use model-recommended callees as authority; select an expansion because it blocks the active caller obligation.

## Procedure

1. Run `analyze-function analyze` on one explicit function.
2. Inspect the node with `show`; treat its contract, abstraction, variants and obligations as proposals.
3. Select at most one blocking obligation and one callee for the next expansion.
4. Run `expand`. Use `refine` only with concrete source, proof, test or domain feedback, preserving the earlier revision.
5. Run `reintegrate` to state what the child changes for its direct caller.
6. Return the remaining local obligations to the proof map. If a premise spans multiple writers, lifecycle phases, callbacks, awaits, save/restore sides or ownership domains, record it as a global-invariant candidate and use `analyze-protocol` or authoritative proof work.

Stop when the caller fact is localized to a proof/test/Human-intent check, when scope would expand without a named blocking obligation, or when the next decision is specification adequacy rather than source analysis.

## Evidence boundary

Retain the session JSON and its artifacts. Report source identity, analyzed span, analysis transform, caller obligation, child edge, contract/abstraction revisions, candidate variants, uncertainties and reintegration disposition.

`open`, `conditional`, `discharged` and `refuted` inside an FM session are analysis dispositions only. They never become authoritative system-proof statuses without independent admissible evidence. A source-supported narrative remains advisory; `MATCH`, absence of a counterexample and model confidence are not proof.
