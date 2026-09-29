Refine the abstraction and contract around the distinction between accepted compatibility metadata and restored unit state.

Do not strengthen `LoadedVm::restore` beyond its body. Make explicit that:
- nonempty inventory is validated before mutation, while empty inventory follows a legacy or implicit compatibility path that remains an obligation;
- success of this wrapper composes validation success and `StateUnits::restore` success, but component completeness, frame preservation, active-versus-deferred semantics, and failure atomicity remain callee obligations;
- destination-owned resources and bindings are framed only conditionally on the `StateUnits` contracts;
- the best reusable abstraction is an accepted partial projection indexed by state-unit identity, not equality of the whole `LoadedVm`.

Keep obligations focused so the result can be reintegrated into `restore_snapshot_state`.
