# FM-Agent + Copilot OpenVMM snapshot-restore experiment

## Bottom line

The experiment provides positive evidence that FM-Agent's analysis method is useful for specification and proof work, but negative evidence for adopting the complete FM-Agent pipeline unchanged.

- The Copilot CLI backend works with `gpt-5.6-sol` for both structured reasoning calls and file-producing agent calls.
- The bounded FM-style analysis generated three materially different contracts, concrete discriminating scenarios, direct-callee expectations, implementation hypotheses, and proof obligations from the real OpenVMM function.
- The reasoner correctly rejected an over-strong full-state-equality candidate with a concrete extra-VP/destination-resource counterexample.
- The reasoner accepted both the intended projection candidate and an intentionally weak orchestration-only candidate. Therefore `MATCH` cannot establish specification adequacy; candidate generation, attacks, completeness checks, proof attempts, and Human review remain necessary.
- The unchanged full entry pipeline did not reach analysis: after a full OpenVMM index/extraction pass, entry selection failed because the requested FQN did not match FM-Agent's extracted/codegraph identity. Direct whole-pipeline use is not yet reliable enough for this workflow.

The recommended use is to keep FM-Agent as a submodule and use a bounded adapter around its caller-driven generation, natural-language reasoner, and counterexample workflow. Do not make its full project orchestration or `MATCH` verdict part of the proof TCB.

## Source and runtime identity

| Item | Value |
| --- | --- |
| OpenVMM worktree | `.worktrees/openvmm-restore-fm` |
| OpenVMM revision | `62acaa5aebe19853286c056683bb372bd8f8b34a` |
| Target file | `openvmm/openvmm_core/src/worker/dispatch.rs` |
| Target lines | 3810-3884 |
| Extracted function SHA-256 | `9aa311b9797dee8cb307c926a30fe45c1cbfb018b81258c704fe6c3ad79bcea5` |
| FM-Agent revision before local changes | `83b89bb9c44e7f3cefa1f8893e1ab99ead0009e6` |
| Agent backend | `copilot-cli` |
| Model | `gpt-5.6-sol` |

The successful bounded run used an isolated Git worktree. It did not modify the historical OpenVMM source tree.

## Copilot integration result

FM-Agent now recognizes:

```toml
[llm]
backend = "copilot-cli"
name = "gpt-5.6-sol"
```

Both FM-Agent execution paths use Copilot:

1. file-oriented agents used for setup, specification generation, and bug validation;
2. direct structured calls used for block postcondition generation and spec implication checking.

Copilot text output visually wraps long JSON strings, producing invalid raw JSON. The backend therefore uses Copilot's JSONL output and extracts the final `assistant.message.data.content` field. This preserves the model's exact JSON string and allows FM-Agent's strict parser and retry policy to remain unchanged.

Validation performed:

- a direct structured call returned valid JSON through `run_agent_for_messages`;
- a file-oriented agent read `input.txt` and created the requested `result.json`;
- the bounded OpenVMM run completed candidate generation and all three reasoner checks.

## Full pipeline result

The first run used FM-Agent's bundled `entry_reasoning` plugin against the existing onboarding tree, as explicitly allowed for this one run.

It completed:

- installation of pinned codegraph `v1.6.0-fmagent.1`;
- full OpenVMM codegraph indexing;
- source extraction.

It then failed before any LLM analysis:

```text
ValueError: entry_func(s)
['openvmm::openvmm_core::src::worker::dispatch-rs::restore_snapshot_state']
not found among extracted functions under proj_dir
```

This is relevant evidence about direct usability. The entry CLI requires an exact internal FQN, but the expected FQN was not discoverable from the user-facing target spelling before paying the full indexing/extraction cost. The run also scanned generated, sysroot, target, and toolchain sources, producing a large warning stream. A production integration needs:

- entry lookup by source file, line, or fuzzy symbol query;
- submodule/source-root restriction compatible with entry mode;
- automatic exclusion of generated toolchains, sysroots, and build outputs;
- a preflight that resolves and prints the canonical FQN before extraction or LLM calls.

## Generated candidate specifications

### Candidate A: snapshot-owned projection equality

This was the recommended candidate. On successful return:

- snapshot-owned guest-relevant state equals the accepted snapshot projection;
- saved VP state is applied by stable identity;
- destination VPs not restored from the snapshot retain valid initial/default state;
- destination compatibility, capacity, memory resources, external-resource bindings, backend identity, and host operational details are preserved;
- active state is distinguished from pending/deferred state;
- permitted downtime is applied to the appropriate clocks;
- the VM remains stopped at the pre-execution boundary;
- resume/readiness behavior remains outside the contract.

Discriminator generated by the agent:

> Restore saved VPs 0 and 2 into a compatible destination containing VPs 0, 1, and 2 with newly bound host devices. VPs 0 and 2 receive saved state, VP 1 remains in its destination default state, host bindings remain destination bindings, pending devices stay pending, clocks advance by downtime, and all VPs remain stopped.

Reasoner result: `MATCH`.

Interpretation: the body is consistent with this candidate only when the generated callee contracts hold. The body alone does not establish projection equality.

### Candidate B: full destination state equality

This candidate treats memory, capacity, every VP, resources, external bindings, pending state, backend details, and host operational state as snapshot-owned.

Reasoner result: `MISMATCH`.

Counterexample:

> Restore into a compatible destination with one additional valid VP and a destination-specific host resource binding. The implementation may preserve the unmatched VP's default state and the destination binding, while full-state equality requires both to match or be replaced by source snapshot state.

This is useful evidence against writing the TOP contract as whole-`LoadedVm` equality. It independently supports the existing decision to define a snapshot projection over a larger runtime View.

### Candidate C: orchestration-only success

This candidate guarantees only that restore and time-adjustment calls returned successfully and that a stop guard was installed. It makes no projection-equality, stable-identity, active/pending, or resource-preservation claim.

Reasoner result: `MATCH`.

This is the most important limitation demonstrated by the experiment. Candidate C is consistent with the implementation but is inadequate for the Human intent. FM-Agent's implementation-vs-spec reasoner cannot reject a weak specification merely because it fails to state required behavior.

## Findings relevant to the current specification

### Confirmed useful structure

The independent analysis recovered the main structure already present in the Human-owned specification:

- full runtime state must be distinct from snapshot-owned state;
- stable VP identity matters;
- unmatched destination VPs need an explicit default-state rule;
- destination resources and compatibility must be preserved;
- time adjustment is a permitted transformation, not ordinary state inequality;
- successful return is a stopped pre-execution boundary;
- resume and readiness are later theorems;
- failure is not automatically transactional.

This is evidence that caller-driven natural-language reasoning can reconstruct a useful contract skeleton from intent, caller context, and implementation.

### Candidate decision: pending and deferred state

The model did not treat pending/deferred state as automatically active snapshot state. It proposed:

```text
pending or deferred state remains pending unless the snapshot format and
component contract explicitly designate it as active
```

This is a useful specification question rather than a confirmed bug. The current Human specification includes `pending_component_state` in the snapshot projection and overlays saved pending state. The FM result suggests making the ownership and lifecycle rule more explicit:

- whether pending payload is snapshot-owned;
- whether restore recreates it as pending rather than active;
- whether absent saved pending state preserves a destination default;
- which later operation is allowed to activate it.

### Proof obligation: stopped throughout restore

The function obtains `restore_start_guard` only after:

1. `self.restore(saved_state)`;
2. `state_units.advance_time`;
3. `partition_unit.advance_tsc`;
4. `partition.advance_snapshot_time`.

The agent correctly refused to infer that guest execution is impossible during these awaits. The existing theorem assumes a prepared stopped pre-state, so the needed proof is not necessarily “move the guard earlier”; it is:

- prove the caller establishes all VPs and state units stopped before entry;
- prove every restore/time callee preserves stoppedness;
- prove replacing any previous guard with the new guard cannot create a resume gap.

This should be represented as an incoming precondition edge plus preserved-invariant edges in the proof map.

### Proof obligation: clock ownership

The same downtime is sent to:

- `StateUnits::advance_time`;
- `PartitionUnit::advance_tsc`;
- `Partition::advance_snapshot_time`.

The top-level body does not prove that these operations refine disjoint clock fields or intentionally coordinated views. The proof needs to establish that each guest-observable clock is advanced exactly once, with documented rounding and overflow behavior.

### Proof obligation: failure state

There are fallible operations after restoration and between time-adjustment stages, with no rollback in this body. A later error can leave earlier mutation in place.

The current scope document already avoids claiming transactional rollback. The FM analysis reinforces that caller proofs should establish non-publication/non-execution on failure, not pre-state equality after failure.

### Additional review questions

The analysis produced several concrete questions worth preserving:

- Why call `set_tsc_frequency_hz` after verifying the destination already reports the same frequency? It may establish hidden backend state, be required for one backend, or be redundant.
- When a snapshot omits APIC frequency, is using the destination APIC frequency the intended compatibility rule?
- On non-x86_64 builds, are the unconditional TSC/APIC compatibility queries meaningful even though VP TSC/APIC advancement is cfg-gated?
- Does assigning a new `restore_start_guard` drop an old guard only after the new stop condition is established?

These are hypotheses for source inspection or proof, not reported bugs.

## Evidence quality

| Evidence | Value | Limitation |
| --- | --- | --- |
| Three semantic candidates | High | Generated from one model and one prompt |
| Concrete candidate discriminators | High | Must become tests or proof witnesses |
| Candidate B `MISMATCH` | Medium-high | Natural-language implication, not formal proof |
| Candidate A `MATCH` | Low as correctness evidence | Depends on assumed callee contracts |
| Candidate C `MATCH` | High as limitation evidence | Demonstrates inability to detect weak specs |
| Proof-obligation list | High for planning | Needs source/proof-map binding |
| Full-pipeline FQN failure | High engineering evidence | Fixable usability issue, not a reasoning failure |
| Source hash and full trace | High reproducibility | Model behavior can vary between runs |

## Adoption decision

### What works

- Copilot can replace OpenCode and direct API model calls in FM-Agent.
- `gpt-5.6-sol` generates useful caller-driven candidate contracts and callee expectations.
- FM-style counterexample reasoning can reject an over-strong candidate.
- The output adds concrete attacks and proof obligations that can feed `argus-spec` and the proof map.

### What does not work as-is

- The complete entry pipeline is too expensive and brittle for one OpenVMM TOP.
- Exact FQN discovery is not user-safe.
- `MATCH` cannot distinguish an adequate specification from a weak one.
- Natural-language callee contracts can make the reasoner appear stronger than the inspected source evidence.
- The result is heuristic evidence, not proof.

### Recommended integration

Keep FM-Agent as a submodule and maintain the Copilot backend, but initially expose only a bounded analysis command:

```text
intent + caller + target source + proof-map cone
→ three candidate contracts
→ concrete discriminators
→ implementation hypotheses
→ per-candidate mismatch analysis
→ proof obligations
→ argus-spec evidence package
```

Use the existing proof-map as the authoritative call graph and source identity layer. Use Verus, executable probes, completeness checking, and Human review to discharge or reject FM-Agent hypotheses.

## Preserved artifacts

Successful evidence:

- `results/run-20260929/evidence.json`
- `results/run-20260929/restore_snapshot_state.rs`
- `results/run-20260929/trace/events.jsonl`
- `results/run-20260929/trace/payloads/`

Compatibility failure evidence:

- `results/run-20260929/candidate-generation.invalid-unescaped-newlines.txt`

The invalid-output artifact documents why the Copilot backend now consumes JSONL and extracts the final assistant message instead of parsing terminal-rendered text.
