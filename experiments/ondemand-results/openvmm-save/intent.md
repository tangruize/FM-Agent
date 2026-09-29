# OpenVMM snapshot save intent

Analyze `LoadedVm::save` as the state-capture layer used by snapshot and restart workflows.

On success, the returned `SavedState` should represent exactly the snapshot-owned logical state of all participating state units at one quiescent capture boundary, paired with inventory metadata that identifies the compatible unit set. It must not claim equality with the whole destination/runtime object: prepared memory, host resource bindings, worker channels, and other runtime-only state remain outside this projection unless explicitly included by a state-unit contract.

The abstraction should distinguish:
- logical component state from concrete serialization blobs and collection order;
- the inventory/identity domain from the captured values;
- snapshot-owned state from destination- or host-owned state;
- a successful complete capture from partial work performed before an error.

Determine whether the body itself proves a coherent complete snapshot, or only packages the result of `StateUnits::save` with a separately observed inventory. Pay particular attention to whether inventory and saved units are drawn from the same stable generation, whether the caller must already have stopped/quiesced mutation, whether optional/unsaved units have intentional semantics, and what failure permits.

Generate a candidate contract and proof obligations suitable for later composing with restore as a projection round-trip theorem. Do not treat the analysis as proof and do not traverse unrelated callees automatically.
