# On-Demand Top-Down Analysis Evaluation

## Result

The on-demand workflow works for the intended proof-engineering use case: start from one explicitly selected function, expand exactly one selected blocking callee, refine the child abstraction, and reintegrate the result into the caller without indexing or traversing the repository closure.

It produced useful specification and proof evidence on two repositories, but it did not discharge any selected obligation. That is the correct outcome: the workflow localized the missing contracts and invariants instead of turning plausible natural-language analysis into a proof verdict.

## Implemented workflow

`python -m src.ondemand` provides:

- `analyze`: analyze one repository-relative file and function;
- `expand`: analyze one callee linked to one selected parent obligation;
- `refine`: revise one node while preserving its prior analysis and feedback;
- `reintegrate`: update the selected caller obligation with the child result;
- `show`: inspect the complete session or one node.

Every node records repository revision, source path, exact line range, SHA-256 of the original source span, model input, contract, abstraction, candidate variants, obligations, and traces. Model expansion is never automatic.

`--strip-verification-annotations` removes inline Verus specification and verification attributes from model input while retaining the original source hash and line identity. This permits a cleaner independent-specification experiment without modifying the target repository.

## Experiments

| Experiment | Top function | Explicit child | Result after reintegration |
|---|---|---|---|
| OpenVMM restore | `LoadedVm::restore_snapshot_state` | `LoadedVm::restore` | `open` |
| OpenVMM save | `LoadedVm::save` | `StateUnits::save` | `open` |
| Nanvix unmap, sanitized | `VirtMemoryManager::try_unmap_upage` | `Vmem::unmap` | `open` |

The unsuccessful unsanitized Nanvix run is retained separately to show why removing embedded formal annotations matters for an independent-recovery claim.

## OpenVMM restore

The top analysis recovered the intended `StoppedRestoredGuestProjection` rather than whole-object equality. It separated snapshot-owned active and deferred state, stable VP identity, guest-visible clocks, the stopped pre-execution boundary, and destination-owned preparation or host resources.

Expanding `LoadedVm::restore` weakened the supported claim in a useful way. The wrapper proves only validation-before-restore sequencing for nonempty inventory and successful delegation to `StateUnits::restore`. It does not prove:

- identity-indexed component coverage;
- saved-value equality;
- active-versus-deferred restoration semantics;
- destination-owned frame preservation;
- compatibility of the empty-inventory path;
- failure atomicity.

Reintegration correctly kept the caller's compositional restore obligation open and emitted explicit proof-map dependencies on `StateUnits::restore`, `validate_inventory`, the save path, and the empty-inventory compatibility rule.

## OpenVMM save

The first pass generated a `QuiescentSnapshotProjection` abstraction `(I, V)`, where `I` is the participating state-unit identity domain and `V` is the logical saved value map. It identified a subtle coherence requirement: `state_units.save().await` and the later `state_units.inventory()` observation must describe the same generation.

Expanding `StateUnits::save` found that:

- it delegates to `run_op` and returns extracted saved values;
- `None` values are omitted;
- it returns no inventory or generation token;
- stable membership, name uniqueness, extraction completeness, lifecycle restoration, and alignment with the later inventory remain callee or caller-protocol obligations.

Reintegration therefore rejected a premature "coherent complete snapshot" conclusion. This is direct evidence that bounded top-down expansion can refine a candidate spec instead of merely restating it.

## Nanvix unmap

The sanitized first pass independently produced the requested separation:

1. per-address-space logical user mapping;
2. page-table and page-directory representation;
3. backing-frame ownership and allocator authority;
4. lower-level table cleanup and reclamation;
5. lifecycle and address-space identity.

It also generated three discriminating specification families:

- a strong failure-atomic synchronous-release contract;
- a recommended abstract contract with exact successful behavior and characterized failure;
- a weak option-tag forwarding contract.

Expanding `Vmem::unmap` identified the main proof gap: `pgdir.unmap` is syntactically fallible after the leaf mapping, hardware mapping, and `user_page_tables` entry may already have been removed. The intended total contract can still be valid, but only if representation/readiness invariants prove these late errors and panic paths unreachable.

Targeted refinement with domain feedback improved the abstraction from a raw `VirtualAddress -> FrameAddress` map to:

- lifecycle-scoped per-space page views with backing identity, permissions, and metadata;
- a global backing store with mapped and retained owners;
- separate physical allocator/resource authority;
- hidden software/hardware page-table representation;
- explicit last-owner reclamation.

This aligns closely with the existing Human-written Nanvix targets:

- exact selected mapping removal and preservation of unrelated mappings;
- `Ok(false)` as an absent-page no-op;
- invalid-range error with unchanged state;
- backing reclamation only after the last mapped or retained owner disappears;
- resource conservation specified separately from logical mapping equality;
- internal lookup and cleanup failures treated as proof obligations for unreachability.

The analysis also adds a useful decomposition not stated as one monolithic TOP postcondition: search-to-projection correspondence, leaf-unmap locality, hardware mirror locality, cleanup preservation, last-owner authority transfer, allocator conservation, and lifecycle identity.

## Evidence quality and limitations

- The workflow is useful for candidate contract generation, abstraction discovery, counterexample design, and proof-map decomposition.
- Child expansion changed what could safely be claimed at both OpenVMM targets and Nanvix.
- Reintegration did not discharge obligations merely because a child analysis existed.
- Natural-language contracts remain hypotheses. Verus, executable attacks, tests, or other authoritative evidence must close the obligations.
- Structured-output robustness remains imperfect. Across the four retained sessions, 13 useful stage results required 29 Copilot calls; 16 calls were rejected and retried by strict schema validation. The rejected outputs are preserved in traces rather than silently accepted.
- A source function containing embedded formal attributes contaminates independent-spec recovery unless `--strip-verification-annotations` is used.
- Explicit line disambiguation is revision-sensitive. When a copied worktree had shifted line numbers, the CLI rejected the mismatch and succeeded after selecting the unique symbol without a line.

## Adoption decision

Use this bounded workflow, not FM-Agent's whole-repository entry pipeline, as the integration surface:

```text
proof-map selects target and blocking obligation
  -> analyze one function
  -> Human/agent selects one child
  -> expand and optionally refine
  -> reintegrate into the direct caller
  -> close remaining obligations with proof or executable evidence
```

Keep full FM-Agent available as an upstream submodule for comparison and bug-validation experiments. Do not make its call graph, `MATCH` result, or natural-language contract an authoritative proof artifact.
