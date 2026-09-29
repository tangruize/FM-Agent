# OpenVMM snapshot restore intent

## Source identity

- Repository: `/home/ruize/argus-improvement/openvmm-restore-onboarding`
- Revision: `62acaa5aebe19853286c056683bb372bd8f8b34a`
- Target: `openvmm/openvmm_core/src/worker/dispatch.rs`
- Function: `LoadedVm::restore_snapshot_state`

## Top-level intent

When snapshot loading succeeds, the returned loaded VM must remain stopped and its snapshot-owned, guest-relevant state must equal the state represented by the accepted snapshot, after applying only restore-time transformations explicitly permitted by the restore request.

The analysis must distinguish:

- state represented in the snapshot from destination or host runtime state that is not snapshot-owned;
- restored active component state from retained pending/deferred component state;
- saved VP state selected by stable VP identity from destination VPs that retain their valid initial/default state;
- snapshot time from the permitted downtime adjustment applied during restore.

Prepared destination memory, compatibility, capacity, external-resource bindings, and host operational details are not values to overwrite merely because a snapshot is loaded. Successful return is a pre-execution boundary: the guest must still be stopped and later resume/readiness behavior is outside this function's success postcondition.

## Analysis questions

1. What caller-facing precondition and postcondition should this function have?
2. Which direct callees must establish each part of the postcondition?
3. Does the implementation order preserve the intended pre-execution boundary?
4. Does any implementation path appear inconsistent with the intent?
5. Which claims require executable tests, component contracts, or Verus proof obligations rather than natural-language reasoning?
6. Are there materially different candidate specifications that should be retained for review?

Treat any natural-language `MATCH` as heuristic evidence, not proof. Preserve assumptions, uncertainty, possible counterexamples, and proof obligations.
