# FM function analysis for system-proof agents

`analyze-function` exposes the bounded FM-Agent workflow used by `system_proof`. It analyzes one selected function, expands only a selected blocking callee, preserves refinements and returns the child result to the direct caller.

Use it to improve a candidate contract or proof decomposition. Do not use it to decide whether a specification is adequate, whether an implementation is correct, whether a bug is confirmed or whether a proof-map edge is closed.

## When to use it

Use function analysis when the active caller needs a fact such as:

- the exact successful or failing behavior of one function;
- the abstract state projected by a concrete representation;
- the frame condition needed from one callee;
- a stronger and weaker contract with a discriminating example;
- the next lemma, test or source audit needed for a proof obligation.

Use `analyze-protocol` instead when the needed property spans multiple writers or operations, including lifecycle phases, callbacks, concurrency, an interval across `await`, save/restore composition, ownership conservation or failure compensation. A function analysis may discover such a property, but does not establish it.

## Setup

From the `system-proof-agent` checkout:

```sh
git submodule sync -- fm-agent
git submodule update --init -- fm-agent
cd fm-agent
uv sync
cd ..
python -m pip install -r requirements-system-proof.txt
```

The submodule is pinned to the project fork, so a normal clone obtains the exact FM-Agent implementation. `analyze-function` launches `fm-agent/.venv/bin/python` and preserves FM-Agent's backend configuration. Set `FM_AGENT_ROOT` or pass `--fm-root` only when using another checkout; use `--fm-python` only when that checkout has a different prepared interpreter.

For retained experiments, use a fresh target worktree or copy and a new session path. The command rejects an existing session rather than overwriting history.

## Inputs

Prepare two short text files:

- **intent**: the caller-visible behavior being investigated, including what is deliberately outside the claim;
- **caller context**: the direct caller fact, current blocking obligation and any approved assumptions.

Keep the original system goal unchanged. Select one exact repository-relative source file and function symbol. A line number is optional and should be used only to disambiguate repeated symbols; copied revisions can shift line numbers.

Example intent:

```text
On success, the restored snapshot-owned projection equals the accepted snapshot,
while destination-owned resources remain distinct. Success is observed before
execution resumes. Failure atomicity is not assumed.
```

## Commands

Create a session:

```sh
analyze-function analyze \
  --repo /path/to/isolated-project \
  --session /path/to/evidence/restore-session.json \
  --file src/worker.rs \
  --symbol Type::restore_snapshot_state \
  --intent /path/to/intent.txt \
  --caller-context /path/to/caller-context.txt
```

Inspect the session and the root node:

```sh
analyze-function show --session /path/to/evidence/restore-session.json
analyze-function show --session /path/to/evidence/restore-session.json \
  --node restore_snapshot_state
```

Expand one obligation into one explicit callee:

```sh
analyze-function expand \
  --session /path/to/evidence/restore-session.json \
  --parent restore_snapshot_state \
  --obligation O1 \
  --file src/worker.rs \
  --symbol restore
```

The model may suggest several callees. That list is navigation advice, not permission to expand all of them. Select the callee because it blocks the active proof-map obligation.

Refine a node with retained feedback:

```sh
analyze-function refine \
  --session /path/to/evidence/restore-session.json \
  --node restore \
  --feedback /path/to/refinement-feedback.md
```

Feedback should cite concrete source behavior, proof failure, test evidence or an approved domain distinction. Refinement preserves the previous analysis; it is not a reason to erase an inconvenient result.

Return the child result to its direct caller:

```sh
analyze-function reintegrate \
  --session /path/to/evidence/restore-session.json \
  --parent restore_snapshot_state \
  --child restore
```

For an independent Rust/Verus contract experiment, add `--strip-verification-annotations` to `analyze` and `expand`. This removes inline Verus specification and verification attributes from model input while retaining the original source span hash and line identity. It does not hide ordinary comments, adjacent files or facts explicitly supplied in intent and feedback; record the information boundary when claiming independent recovery.

## Evidence produced

A session contains:

- repository revision, source file, line span and original source SHA-256;
- the transform applied to model input;
- caller intent and context;
- proposed precondition, postcondition and failure condition;
- an abstraction: abstract state, projection, preserved state, hidden representation and observation boundary;
- implementation assessments and uncertainties;
- stronger or weaker candidate variants with discriminating scenarios;
- selectable obligations and suggested callees;
- explicit parent-child edges;
- refinement history and prior analyses;
- reintegration rationale, remaining gaps and proposed proof-map updates;
- structured prompts, responses and rejected retries under the adjacent `.artifacts/` directory.

This is **source-bound advisory evidence**: it records exactly which source span and analysis method produced a proposal. It is not implementation proof, specification completeness, executable bug confirmation or Human acceptance.

Before reusing a session after source or contract changes, compare its recorded revision and source hash with the current target. The FM session records these identities but does not currently propagate stale status through the system-proof proof map automatically.

## Reading the result

### Contract

The proposed behavior at the selected observation boundary. A contract can be too strong, too weak or based on an unstated assumption even when it matches the function body.

### Abstraction and projection

An **abstraction** names the logical state relevant to the caller. A **projection** maps concrete fields and representation objects into that logical state. For example, a VM snapshot is normally a projection of snapshot-owned guest state, not equality of the entire runtime object.

### Frame condition

The state that must remain unchanged. Frame conditions are essential when a wrapper delegates mutation to a callee; absence of direct assignments in the wrapper does not prove preservation.

### Blocking obligation

A precise missing fact that prevents the caller claim from being established. It may request a callee contract, representation lemma, failure test, ownership fact or Human intent decision.

### Refinement

A revision of one node using new evidence or an explicit semantic distinction. Refinement should narrow ambiguity or correct an overclaim, not repeatedly ask the model until it agrees.

### Reintegration

The step that explains what a child analysis changes for its direct caller. Reintegration can keep an obligation open; that is useful when it replaces a vague uncertainty with named proof dependencies.

### Global-invariant candidate

A premise that must hold across multiple operations, representations or lifecycle phases. Typical examples are stable membership during snapshot capture, continuous stoppedness during restore, agreement between logical mappings and hardware page tables, and conservation of ownership authority.

Promote such a premise into the system-proof map or investigate it with `analyze-protocol`. Do not duplicate it as unrelated local preconditions under every function.

## What the agent may and may not conclude

The agent may:

- propose candidate contracts and abstractions;
- identify source-supported or challenged claims;
- create proof-map obligations;
- recommend the cheapest discriminating proof, test, source audit or Human-intent check;
- report that child analysis strengthened, weakened or failed to support a caller claim.

The agent may not:

- select the adequate specification solely from FM output;
- interpret `MATCH`, `discharged`, model confidence or lack of a counterexample as proof;
- attach an FM session as evidence that closes a proof-map edge;
- silently turn a global invariant candidate into an assumption;
- confirm a bug without executable or formal evidence;
- change the original system goal to make the local contract easier.

## Returning to the system-proof campaign

Return a compact handoff containing:

```text
goal and direct caller
analyzed source identity
selected obligation and child
supported, challenged and unresolved proposals
global-invariant candidates
cheapest next authoritative check
session and artifact paths
```

Use `map declare` to record genuine remaining obligations, not to certify the FM narrative. Use source audit, native tests, implementation proof, model checking or bounded Human intent judgment to change authoritative status. Continue reintegration toward the top-level caller; a collection of locally plausible contracts is not global proof progress.

## Trust and operational limits

- FM-Agent invokes an authenticated coding-agent CLI with permissive tool flags. The bounded prompt and isolated worktree are not an operating-system sandbox.
- Strict JSON validation rejects malformed or incomplete model output, but retries increase cost and do not improve epistemic authority.
- Suggested callees may be incomplete or wrong; the proof map remains the scope authority.
- Embedded specifications can contaminate independent recovery unless explicitly removed from model input.
- An `open` result is not failure: it is useful when it exposes the exact invariant, callee contract or verification step still required.
